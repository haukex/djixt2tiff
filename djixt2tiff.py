#!/usr/bin/env python3
"""DJI XT2 TIFF Library.

Author, Copyright and License
-----------------------------
Copyright (c) 2022 Hauke Daempfling (haukex@zero-g.net)
at the Leibniz Institute of Freshwater Ecology and Inland Fisheries (IGB),
Berlin, Germany, https://www.igb-berlin.de/

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see https://www.gnu.org/licenses/
"""
import datetime
import json
import xml.etree.ElementTree as XmlEt
from collections.abc import Generator
from enum import Enum
from itertools import chain
from typing import NamedTuple, Any
import regex
import tifffile

class WGS84Coords(NamedTuple):
    lat: float
    lon: float
    alt: float
    def __str__(self):
        # note KML requires Lon,Lat while many others (like Google Maps) require Lat,Lon
        # also, KML requires EGM96 orthometric height instead of WGS84 ellipsoid height
        return f"{self.lat:.9f},{self.lon:.9f},{self.alt:.2f}"

def convert_gpstag(tag :tifffile.TiffTag) -> WGS84Coords:
    if not tag.name=='GPSTag': raise ValueError()
    gps = tag.value
    if gps['GPSMapDatum'] != 'WGS-84':
        raise RuntimeError(f"GPSMapDatum {gps['GPSMapDatum']!r}")
    # ### lat ###
    y = gps['GPSLatitude']
    if len(y) != 6: raise RuntimeError(f"GPSLatitude {y!r}")
    lat = y[0]/y[1] + (y[2]/y[3])/60.0 + (y[4]/y[5])/3600.0
    if lat>90 or lat<0: raise RuntimeError(f"GPSLatitude {y!r}")
    if gps['GPSLatitudeRef'] == 'N': pass
    elif gps['GPSLatitudeRef'] == 'S': lat = -lat
    else: raise RuntimeError(f"GPSLatitudeRef {gps['GPSLatitudeRef']!r}")
    # ### lon ###
    x = gps['GPSLongitude']
    if len(x) != 6: raise RuntimeError(f"GPSLongitude {x!r}")
    lon = x[0]/x[1] + (x[2]/x[3])/60.0 + (x[4]/x[5])/3600.0
    if lon>180 or lon<0: raise RuntimeError(f"GPSLongitude {x!r}")
    if gps['GPSLongitudeRef'] == 'E': pass
    elif gps['GPSLongitudeRef'] == 'W': lon = -lon
    else: raise RuntimeError(f"GPSLongitudeRef {gps['GPSLongitudeRef']!r}")
    # ### alti ###
    if gps['GPSAltitudeRef'] != 0:
        raise RuntimeError(f"GPSAltitudeRef {gps['GPSAltitudeRef']!r}")
    z = gps['GPSAltitude']
    alt = z[0]/z[1]
    # ###
    return WGS84Coords(lon=lon, lat=lat, alt=alt)

# note the "id" appears to be fixed, at least in all the data I have available
_xmp_re = regex.compile(r'''
    \A\s* <\?xpacket \s+ begin=(?:'[^'>]*'|"[^">]*") \s+ id=(?P<q>["'])W5M0MpCehiHzreSzNTczkc9d\g<q> \?>
        (?P<content>.*)
    <\?xpacket \s+ end=(?:'[^'>]*'|"[^">]*") \?> [\s\x00]*\Z''', regex.DOTALL|regex.X )
_tagname_re = regex.compile(r'''\A\{[^\}]+\}(?P<name>\w+)\Z''')
def _page_tagconv_it(page :tifffile.TiffPage) -> Generator[tuple[str, Any]]:
    if page.tags['Make'].value != 'DJI' or page.tags['Model'].value != 'XT2':
        raise RuntimeError(f"This is not a DJI XT2, it is a {page.tags['Make'].value!r} {page.tags['Model'].value!r}")
    for tag in page.tags:
        if tag.name == 'XMP':
            m = _xmp_re.fullmatch( tag.value.decode(encoding='ASCII') )
            if not m: raise RuntimeError(f"Failed to parse XMP {tag.value!r}")
            x = XmlEt.fromstring(m.group('content'))
            for e in chain( x.findall('.//{http://www.dji.com/drone-dji/1.0/}*'), x.findall('.//{http://www.dji.com/FLIR/1.0/}*') ):
                m = _tagname_re.fullmatch(e.tag)
                if not m: raise RuntimeError(f"Failed to parse tag name {e.tag!r}")
                yield m.group('name'), ' '.join(e.itertext()).strip()
        elif isinstance(tag.value, dict):
            for k, v in tag.value.items():
                yield k, v.decode(encoding='ASCII') if isinstance(v, bytes) else v
        elif isinstance(tag.value, Enum):
            yield tag.name, tag.value.name
        else:
            yield tag.name, tag.value
    if 'GPSTag' in page.tags:
        yield 'Coords', convert_gpstag(page.tags['GPSTag'])

def pageprops(*, idx :int, page :tifffile.TiffPage) -> dict[str, Any]:
    atts :dict[str, Any] = {}
    for k, v in _page_tagconv_it(page):
        if k in atts: raise KeyError(f"Key {k!r} already exists with value {atts[k]!r}, can't set it to {v!r}.")
        atts[k] = v
    # fixup page number - no, don't place this restriction on the page number
    #if len(atts['PageNumber'])!=2 or atts['PageNumber'][0]!=idx or atts['PageNumber'][1]!=0:
    #    raise RuntimeError(f"bad PageNumber, expected {(idx,0)}, got {atts['PageNumber']!r}")
    #atts['PageNumber'] = atts['PageNumber'][0]
    # fixup date/time
    if 'DateTimeOriginal' in atts:
        dt = datetime.datetime.strptime(atts['DateTimeOriginal'], '%Y:%m:%d %H:%M:%S')
        if 'SubsecTimeOriginal' in atts:
            # from inspection, I have inferred that 1 SubsecTimeOriginal is 10 milliseconds
            dt = dt.replace( microsecond = int(atts['SubsecTimeOriginal'])*10000 )
        atts['DateTimeOriginal'] = dt
    return atts

def props2json(atts :dict[str, Any]) -> str:
    atts2 = atts.copy()
    if 'DateTimeOriginal' in atts2:
        atts2['DateTimeOriginal'] = atts2['DateTimeOriginal'].isoformat(sep=' ',timespec='milliseconds')
    if 'Coords' in atts2: atts2['Coords'] = str(atts2['Coords'])
    return json.dumps(atts2, indent=2)
