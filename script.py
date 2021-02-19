"""
Module to take screenshots of vitalsource books.
"""

#%%
from pathlib import Path
from typing import Dict
from PIL import Image
from fpdf import FPDF
import pyautogui as pa
import numpy as np
import pandas as pd
import datetime as dt
import time
import cv2
import ocrmypdf

pa.PAUSE = 0.1
pa.FAILSAFE = True

#%% Setting up and calibrating.

# Positions on screen.

preset = "laptop"

presets = {
    "homesetup": {
        "page": np.array([225, 1175]),
        "screen": np.array([320, 85, 1437, 1050]),
    },
    "laptop": {"page": np.array([219, 1060]), "screen": np.array([321, 85, 1441, 930])},
}

if preset in presets:
    pos = presets[preset]
else:  # do interactive
    pa.alert(
        text='Move mouse to position of textbox containing page number, and press "Enter".',
        title="Calibration",
        button="OK",
    )
    pos["page"] = np.array(pa.position())
    pa.alert(
        text='Move mouse to top-left position of content area, and press "Enter".',
        title="Calibration",
        button="OK",
    )
    topleft = np.array(pa.position())
    pa.alert(
        text='Move mouse to bottom-right position of content area, and press "Enter".',
        title="Calibration",
        button="OK",
    )
    bottomright = np.array(pa.position())
    pos["screen"] = np.array([*topleft, *(bottomright - topleft)])
    pa.alert(f'Variable "pos":\n{pos}', "Calibration complete")
    print(f'setup, variable "pos":\n{pos}')
pos["middle"] = pos["screen"][:2] + 0.5 * pos["screen"][2:]


# Path to save to.
basepath = Path("output4/")
subs = [
    ("0_screenshots", ".png"),
    ("1_png", ".png"),
    ("2_jpg", ".jpg"),
    ("3_pdf", ".pdf"),
    ("4_pdf_searchable", ".pdf"),
]


def path(phase: int = 0, pagenum=None, ab=None):
    """Returns path to folder or file."""
    subpath, suffix = subs[phase]
    p = basepath / subpath
    if pagenum is None:  # return path to folder
        return p
    else:  # return path to file
        if phase == 3 or phase == 4:
            return p / "result.pdf"
        filename = f"{pagenum:04d}"
        if ab is not None:
            filename += ab
        suffix = ".jpg" if phase == 2 else ".png"
        return p / (filename + suffix)


for phase in range(len(subs)):
    p = path(phase)
    if not p.exists():
        p.mkdir(parents=False)
    assert p.is_dir()


# Sleep time to load page.

sleep_time = 2  # seconds


# How many screenshots per page.
# . True to take one screenshot per page.
# . False to take screenshot, scroll down, and take another one.
#   Each screen must show >= 55% of page so there is overlap for stitching.
singleshot = False


# Pages to screenshot.

pages = {"first": 1, "last": 235}


# Quality of stitched jpg.

jpg_quality = 70


# %% Take screenshots.


print(f"{dt.datetime.now()}: screenshots: start.")
print("Will start in 5 seconds. Make sure Bookshelf app is visible and behind it!")

time.sleep(5)

for page in range(pages["first"], pages["last"] + 1):
    # move to page and wait for it to load
    pa.click(*pos["page"])
    pa.hotkey("ctrl", "a")
    pa.write(str(page))
    pa.press("enter")
    time.sleep(sleep_time)
    # make screenshot
    pa.click(*pos["middle"])
    pa.scroll(2000)
    time.sleep(0.1)
    pa.screenshot(path(0, page, "a"), region=pos["screen"])

    if not singleshot:
        pa.click(*pos["middle"])
        pa.scroll(-2000)
        time.sleep(0.1)
        pa.screenshot(path(0, page, "b"), region=pos["screen"])

print(f"{dt.datetime.now()}: screenshots: finished.")

# %% Stitch.

if singleshot:
    raise ValueError("No stitching required.")

print(f"{dt.datetime.now()}: stitching: start.")

# Find overlapping part.

page_stitchtemplate = (
    4  #  should be a good page to do the stitching; not too much white space.
)


def mse(imageA, imageB):
    # the 'Mean Squared Error' between the two images is the
    # sum of the squared difference between the two images;
    # NOTE: the two images must have the same dimension
    err = np.sum((imageA.astype("float") - imageB.astype("float")) ** 2)
    err /= float(imageA.shape[0] * imageA.shape[1])

    # return the MSE, the lower the error, the more "similar"
    # the two images are
    return err


imga, imgb = [
    cv2.imread(str(path(0, page_stitchtemplate, part))) for part in ["a", "b"]
]
h = imga.shape[0]
find = imga[-10:, 20:-20, :]  # 10 pix tall strip at end
besterror, besty = np.inf, None
for y in range(0, h - 10):
    test = imgb[y : y + 10, 20:-20, :]
    if (error := mse(test, find)) < besterror:
        besterror, besty = error, y


print(f"{dt.datetime.now()}: stitching: found optimal overlap point.")

# Do stitching.

for page in range(pages["first"], pages["last"] + 1):
    imga, imgb = [cv2.imread(str(path(0, page, part))) for part in ["a", "b"]]
    img = np.vstack((imga[:-10, :, :], imgb[besty:, :, :]))
    cv2.imwrite(str(path(1, page)), img)

print(f"{dt.datetime.now()}: stitching: finished.")


# %%  Save as jpg.

print(f"{dt.datetime.now()}: jpg: start.")

if singleshot:
    sourcepath = path(0)
else:
    sourcepath = path(1)

for file in sourcepath.iterdir():
    if file.is_dir():
        continue

    im = Image.open(file)
    h, w = im.height, im.width
    h, w = h - h % 2, w - w % 2  # make even to reduce jpg artefacts
    im = im.crop((0, 0, w, h))
    im.save(path(2) / f"{file.stem}.jpg", "JPEG", quality=jpg_quality)

print(f"{dt.datetime.now()}: jpg: finished.")

# %% Save as pdf.

print(f"{dt.datetime.now()}: pdf: start.")

page_sizetemplate = 4

im = Image.open(path(2, page_sizetemplate))
pdf = FPDF(unit="pt", format=[im.width, im.height])
for file in path(2).iterdir():
    if file.is_dir():
        continue
    pdf.add_page()
    pdf.image(str(file), 0, 0)
pdf.output(path(3, -1), "F")

print(f"{dt.datetime.now()}: pdf: finished.")

# %% Do OCR to make searchable.

print(f"{dt.datetime.now()}: ocr: start.")

ocrmypdf.ocr(path(3, -1), path(4, -1))

print(f"{dt.datetime.now()}: ocr: finished.")

# %%