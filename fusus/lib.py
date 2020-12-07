import os
import io
from itertools import chain, groupby
from tempfile import NamedTemporaryFile

import numpy as np

import PIL.Image
from IPython.display import HTML, Image, display
import cv2

from tf.core.helpers import rangesFromList, specFromRanges


EXTENSIONS = set(
    """
    jpeg
    jpg
    png
    tif
    tiff
""".strip().split()
)
"""Supported image file extensions.
"""

FONT = cv2.FONT_HERSHEY_SIMPLEX


def tempFile():
    """Get a temporary file.
    """

    return NamedTemporaryFile(mode="w", dir=".")


def imgElem(data):
    """Produce an image with its data packaged into a HTML <img> element.
    """

    return f"""<img src="data:image/jpeg;base64,{data}">"""


def PILFromArray(a):
    return PIL.Image.fromarray(a)


def arrayFromPIL(img):
    return np.asarray(img)


def showImage(a, fmt="jpeg", **kwargs):
    """Show one or more images.
    """

    if type(a) in {list, tuple}:
        ads = []
        for ae in a:
            ai = np.uint8(np.clip(ae, 0, 255))
            f = io.BytesIO()
            PIL.Image.fromarray(ae).save(f, fmt)
            ad = Image(data=f.getvalue(), **kwargs)._repr_jpeg_()
            ads.append(ad)
        display(HTML(f"<div>{''.join(imgElem(ad) for ad in ads)}</div>"))
    else:
        ai = np.uint8(np.clip(a, 0, 255))
        f = io.BytesIO()
        PIL.Image.fromarray(ai).save(f, fmt)
        display(Image(data=f.getvalue(), **kwargs))


def overlay(img, left, top, right, bottom, srcColor, dstColor):
    """Colors a region of an image with care.

    A selected region of an image can be given a uniform color,
    where only pixels are changed that have an exact given color.

    In this way you can replace all the white with gray, for example,
    without wiping out existing non-white pixels.

    Parameters
    ----------
    img: np array
        The image to be overlain with a new color
    (left, top, right, bottom): (int, int, int, int)
        The region in the image to be colored
    srcColor: RGB color
        The color of the pixels that may be replaced.
    dstColor:
        The new color of the replaced pixels.
    """
    if right > left and bottom > top:
        roi = img[top:bottom, left:right]
        roi[np.where((roi == list(srcColor)).all(axis=2))] = dstColor


def splitext(f, withDot=True):
    """Splits a file name into its main part and its extension.

    Parameters
    ----------
    f: string
        The file name
    withDot: boolean, optional `False`
        If True, the `.` in the extension is considered part of the extension,
        else the dot is stripped from it.

    Returns
    -------
    tuple
        The main part and the extension
    """

    (bare, ext) = os.path.splitext(f)
    if ext and not withDot:
        ext = ext[1:]
    return (bare, ext)


def imageFileList(imDir):
    """Gets a sorted list of image files from a directory.

    Only files having an image extension (defined in `EXTENSIONS`)
    are listed.

    Parameters
    ----------
    imDir: string
        Path to the image directory

    Returns
    -------
    list
        Alphabetically sorted list of file names (without directory, with extension)
    """

    if not os.path.exists(imDir):
        return []

    imageFiles = []
    with os.scandir(imDir) as it:
        for entry in it:
            name = entry.name
            (bare, ext) = splitext(name, withDot=False)

            if not name.startswith(".") and entry.is_file() and ext in EXTENSIONS:
                imageFiles.append(name)
    return sorted(imageFiles)


def imageFileListSub(imDir):
    """Gets sorted lisst of image files from the subdirectories of a directory.

    Only files having an image extension (defined in `fusus.parameters.EXTENSIONS`)
    are listed.

    Parameters
    ----------
    imDir: string
        Path to the image directory

    Returns
    -------
    dict
        Keyed by subdirectory names, valued by
        alphabetically sorted list of file names (without directory, with extension)
    """

    if not os.path.exists(imDir):
        return {}
    imageFiles = {}
    with os.scandir(imDir) as it:
        for entry in it:
            name = entry.name
            if not name.startswith(".") and entry.is_dir():
                imageFiles[name] = imageFileList(f"{imDir}/{name}")
    return imageFiles


def pagesRep(source, asList=False):
    """Represents a set of pages as a string in a compact way or as a list.

    Parameters
    ----------
    source: list
        A list of file names, without directory, with extension
    asList: boolean, optional `False`
        Whether to return the result as a list of integers or as a compact string.

    Returns
    -------
    list or string
        Depending on `asList` a list of page numbers (integers) or a string
        mentioning the page numbers, using intervals where possible.
    """
    pages = [int(splitext(f)[0].lstrip("0")) for f in source]
    return pages if asList else specFromRanges(rangesFromList(pages))


def select(source, selection):
    """Choose items from a bunch of integers.

    Parameters
    ----------
    source: iterable of int
        The items to choose from
    selection: iterable of int or string or `None`
        If None, selects all items, otherwise specifies what numbers to select.
        If a number is in the selection, but not in the source, it will not be selected.
        The selection can be an integer or a compact string that specifies integers,
        using ranges and commas.

    Returns
    -------
    list
        Sorted list of selected items
    """

    if selection is None:
        return sorted(source)

    index = {int(splitext(f)[0].lstrip("0")): f for f in source}
    universe = set(index)
    if type(selection) is int:
        return sorted(index[n] for n in {selection} & universe)

    minu = min(universe, default=0)
    maxu = max(universe, default=0)
    selected = set()
    for rng in selection.split(","):
        parts = rng.split("-")
        if len(parts) == 2:
            (lower, upper) = parts
            lower = minu if lower == "" else int(lower)
            upper = maxu if upper == "" else int(upper)
        else:
            lower = int(parts[0])
            upper = lower
        selected |= set(range(lower, upper + 1)) & universe
    return sorted(index[n] for n in selected)


def removeSkewStripes(img, skewBorder, skewColor):
    """Remove black triangles resulting from unskewing images.

    When an image is unskewed, it is rotated slightly and that introduces
    stroke like triangles in the corners.
    This function removes them by coloring all image borders with white.

    Parameters
    ----------
    img: image as np array
        the image to operate on
    skewBorder: int
        the width of the border that is whitened
    skewColor: color
        the exact white color with which we color the borders.

    Returns
    -------
    None
        The source image receives a modification.
    """

    (imH, imW) = img.shape[0:2]
    if min((imH, imW)) < skewBorder * 10:
        return
    for rect in (
        ((0, 0), (skewBorder, imH)),
        ((0, 0), (imW, skewBorder)),
        ((imW, imH), (imW - skewBorder, 0)),
        ((imW, imH), (0, imH - skewBorder)),
    ):
        cv2.rectangle(img, *rect, skewColor, -1)


def parseStages(stage, allStages, sortedStages, error):
    """Parses a string that specifies stages.

    Stages are steps in the image processing.
    Each stage has an intermediate processing result.

    Parameters
    ----------
    stage: string or None or iterable
        If None: it means all stages.
        If a string: the name of a stage.
        If an iterable: the items must be names of stages.
    allStages: tuple
        Names of all stages.
    sortedStages:
        Sorted list of all stages.
    error: function
        Method to write error messages.

    Returns
    -------
    tuple
        The stages as parsed.
    """

    doStages = (
        allStages
        if stage is None
        else set()
        if not stage
        else set(stage.split(","))
        if type(stage) is str
        else set(stage)
    )
    illegalStages = doStages - allStages
    if illegalStages:
        error(f"Will skip illegal stages: {', '.join(sorted(illegalStages))}")

    doStages = doStages - illegalStages

    return tuple(s for s in sortedStages if s in doStages)


def parseBands(band, allBands, error):
    """Parses a string that specifies bands.

    Bands are horizontal rectangles defined with respect to lines.
    They correspond with regions of interest where we try to find specific
    marks, such as commas and accents.

    Parameters
    ----------
    band: string or None or iterable
        If None: it means all bands.
        If a string: the name of a band.
        If an iterable: the items must be names of bands.
    allBands: tuple
        Names of all bands.
    error: function
        Method to write error messages.

    Returns
    -------
    tuple
        The bands as parsed.
    """

    sortedBands = sorted(allBands)
    doBands = (
        allBands
        if band is None
        else set(band.split(","))
        if type(band) is str
        else set(band)
    )
    illegalBands = doBands - allBands
    if illegalBands:
        error(f"Will skip illegal bands: {', '.join(sorted(illegalBands))}")

    doBands -= illegalBands
    return tuple(b for b in sortedBands if b in doBands)


def parseMarks(mark, allMarks, bands, error):
    """Parses a string that specifies Marks.

    Marks are strokes that we need to find on the page in order to remove them.
    They are organized in bands: the regions of interest with respect to the lines
    where we expect them to occur.

    Parameters
    ----------
    mark: string or None or iterable
        If None: it means all marks.
        If a string: the name of a mark.
        If an iterable: the items must be names of marks.
    allMarks: tuple
        Names of all marks.
    error: function
        Method to write error messages.

    Returns
    -------
    tuple
        The marks as parsed.
    """

    markIndex = {}
    for (band, bandMarks) in allMarks.items():
        for m in bandMarks:
            markIndex.setdefault(m, set()).add(band)

    doMarks = (
        set()
        if mark is None
        else set(chain.from_iterable(allMarks.get(band, ()) for band in bands))
        if mark == ""
        else set(mark.split(","))
        if type(mark) is str
        else set(mark)
    )
    illegalMarks = doMarks - set(markIndex)
    if illegalMarks:
        error(f"Will skip illegal marks: {', '.join(sorted(illegalMarks))}")

    doMarks -= illegalMarks
    return doMarks


def findRuns(x):
    """Find runs of consecutive items in an array.

    Credits:
    [Alistair Miles](https://gist.github.com/alimanfoo/c5977e87111abe8127453b21204c1065)
    """

    # ensure array
    x = np.asanyarray(x)
    if x.ndim != 1:
        raise ValueError("only 1D array supported")
    n = x.shape[0]

    # handle empty array
    if n == 0:
        return np.array([]), np.array([]), np.array([])

    else:
        # find run starts
        loc_run_start = np.empty(n, dtype=bool)
        loc_run_start[0] = True
        np.not_equal(x[:-1], x[1:], out=loc_run_start[1:])
        run_starts = np.nonzero(loc_run_start)[0]

        # find run values
        run_values = x[loc_run_start]

        # find run lengths
        run_lengths = np.diff(np.append(run_starts, n))

        return run_values, run_starts, run_lengths


def applyBandOffset(C, height, bandName, lines, inter=False):
    """Produce bands from a list of lines.

    Bands are defined relative to lines by means of offsets of the top
    and bottom heights of the lines.

    Bands may also be interlinear: defined between the bottom of one line and the top
    of the next line.

    Parameters
    ----------
    C: object
        Configuration settings
    height:
        The height of the page or block
    bandName: string
        The name of the bands
    lines: tuple
        The lines relative to which the bands have to be determined.
        Lines are given as a tuple of tuples of top and bottom heights.
    inter: boolean, optional `False`
        Whether the bands are relative the lines, or relative the interlinear spaces.

    Returns
    -------
    tuple
        For each line the band named bandName specified by top and bottom heights.
    """

    offsetBand = C.offsetBand

    (top, bottom) = offsetBand[bandName]

    def offset(x, off):
        x += off
        return 0 if x < 0 else height if x > height else x

    return tuple(
        (offset(up, top), offset(lo, bottom))
        for (up, lo) in (
            zip((x[1] for x in lines), (x[0] for x in lines[1:])) if inter else lines
        )
    )


def getMargins(hist, width, threshold):
    """Get margins from a histogram.

    The margins of a histogram are the coordinates where the histogram reaches a
    threshold for the first time and for the last time.

    We deliver the pairs (0, xFirst) and (xLast, maxWidth) if there are points
    above the threshold, and (0, maxW) otherwise.


    Parameters
    ----------
    hist: [int]
        Source array of pixel values
    width: int
        Maximum index of the source array
    threshold: int
        Value below which pixels count as zero
    """
    chunks = [
        [i for (i, value) in it]
        for (key, it) in groupby(enumerate(hist), key=lambda x: x[1] >= threshold)
        if key >= threshold
    ]
    w = len(hist)
    return ((0, chunks[0][0]), (chunks[-1][-1], w)) if chunks else ((0, w),)


def pureAverage(data, supplied):
    """Get the average of a list of values after removing the outliers.

    It is used for calcaluting lineheights from a sequence of distances between
    histogram peaks.
    In practice, some peaks are missing due to short line lengths, and that
    causes some abnormal peak distances which we want to remove.

    Parameters
    ----------
    data: np array
        The list of values whose average we compute.
    """

    if data.size == 0:
        return supplied
    elif data.size == 1:
        return int(round(data[0]))

    # remove outliers
    m = 2.0
    d = np.abs(data - np.median(data))
    mdev = np.median(d)
    s = d / mdev if mdev else 0.0
    pure = data[s < m]
    if len(pure) == 0:
        return supplied
    elif pure.size == 1:
        return int(round(pure[0]))
    return int(round(np.average(pure)))