#!/usr/bin/env python3
"""Example script using djixt2tiff library.

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
import os
from collections.abc import Iterable, Generator, Sequence
from typing import Any, TypeVar
import matplotlib as mp
import matplotlib.pyplot as plt
import numpy as np
from tifffile import TiffFile
from djixt2tiff import pageprops, props2json

# a simple utility function to get a specific item from an iterable
_T = TypeVar('_T')
def iter_nth(iterable :Iterable[_T], n :int) -> _T:
    from itertools import islice
    return next(islice(iterable, n, n+1))

# generator function to access image files (doesn't actually load *all* images unless requested)
def allimgs(files :Sequence[str|os.PathLike]) -> Generator[tuple[np.ndarray, dict[str, Any]]]:
    for fn in files:
        with TiffFile(fn) as tif:
            for idx, page in enumerate(tif.pages):
                yield page.asarray(), pageprops(idx=idx, page=page)

def display_image(*, file :str|os.PathLike, index :int, width_in :float):
    imgs = allimgs([file])
    data, props = iter_nth(imgs, index)

    print(props2json(props))  # print the image properties as JSON

    # Convert pixel values to temperatures
    img :np.ndarray = data.astype(np.float64) * float(props['TlinearGain']) - 273.15

    # calculate some statistics (optional)
    stddev = np.std(img)
    avg = np.mean(img)

    # https://matplotlib.org/stable/api/_as_gen/matplotlib.colors.Normalize.html
    # setting vmin and vmax is optional, we're just doing it to demonstrate the "over" and "under" values in the colormap!
    norm = mp.colors.Normalize(vmin=avg-stddev*2, vmax=avg+stddev*2)

    # https://matplotlib.org/stable/api/_as_gen/matplotlib.colors.Colormap.html
    # https://matplotlib.org/stable/tutorials/colors/colormaps.html
    # this colormap doesn't contain green, but we also don't expect any "bad" pixels
    cmap = mp.cm.get_cmap('plasma').with_extremes(under="white", over="black", bad="green")

    # calculate figure height from width based on aspect ratio
    height_in = (width_in / props['ImageWidth']) * props['ImageLength']
    height_in /= 1.15  # a bit of extra space for the colorbar

    # generate the figure
    plt.figure(figsize=(width_in, height_in), layout='constrained')
    plt.imshow(img, norm=norm, cmap=cmap, interpolation='none')
    plt.colorbar()
    plt.show()

if __name__ == '__main__':
    import sys
    import argparse
    parser = argparse.ArgumentParser(description='Display DJI XT2 Images')
    parser.add_argument('-i', '--index', help='image index (0-based)', type=int, required=True)
    parser.add_argument('-w', '--width', help="figure display width in inches", type=float, default=10)
    parser.add_argument('file', metavar="TIFFFILE", help="input TIFF file")
    args = parser.parse_args()
    display_image(file=args.file, index=args.index, width_in=args.width)
    sys.exit(0)
