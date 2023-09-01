# Copyright (c) Karan Desai (https://kdexd.xyz), The University of Michigan.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import json
import multiprocessing as mp
import os
import time
from calendar import Calendar
from datetime import datetime
from typing import Any, Dict, List, Tuple

import click
from tqdm import tqdm

import redcaps
import redcaps._color_print as cprint
from redcaps.downloaders import (
    ImageDownloader,
    RedditIdDownloader,
    RedditInfoDownloader,
)


@click.command()
@click.option("-s", "--subreddit", help="Name of subreddit to download posts.")
# fmt: off
@click.option(
    "-m", "--yyyy-mm", type=click.DateTime(["%Y-%m"]),
    help="""Download posts from this month from Day 1 (00:00:00 UTC) to Day
    28-31 (23:59:59 UTC).""",
)
@click.option(
    "-c", "--credentials", type=click.Path(exists=True),
    help="API key and user credentials for Reddit and Imgur."
)
@click.option(
    "-o", "--save-to", type=click.Path(), default="./datasets/redcaps/annotations",
    help="Path to save annotations. This can be a JSON path or directory path.",
)
@click.option(
    "-t", "--time-window", type=float, default=24,
    help="Download iteratively in small time window (in hours). Must be <= 24.",
)
# fmt: on
def download_anns(
    subreddit: str,
    yyyy_mm: datetime,
    credentials: str,
    save_to: str,
    time_window: float,
):
    r"""
    Download image posts from one subreddit, submitted in a particular month.

    This is done in two steps: first we retrieve Reddit post IDs using Pushshift
    API, and then we get post info for those IDs using official Reddit API. This
    two-step approach is necessary because Pushshift does not have accurate upvote
    counts, whereas Reddit API does not allow time-based search filtering.
    """

    # Load Reddit and Imgur API credentials.
    credentials = json.load(open(credentials))
    cprint.white(f"Downloading posts from {subreddit}, {yyyy_mm.strftime('%Y-%m')}")

    # Iterate over all days of the month. Calendar module returns extra dates
    # from preceeding and succeeding months as per weeks, so filter them.
    cal = Calendar()
    dates_per_month = [
        _date
        for _date in cal.itermonthdates(yyyy_mm.year, yyyy_mm.month)
        if _date.month == yyyy_mm.month
    ]
    # Download IDs of Reddit posts for all dates (uses Pushshift API internally).
    REDDIT_POST_IDS: List[str] = []
    for _date in dates_per_month:
        id_downloader = RedditIdDownloader(subreddit, _date)
        REDDIT_POST_IDS.extend(id_downloader.download(time_window))

    # De-duplicate and sort IDs.
    REDDIT_POST_IDS = sorted(set(REDDIT_POST_IDS))

    # Download post info for all the downloaded post IDs.
    info_downloader = RedditInfoDownloader(credentials=credentials)
    ANNOTATIONS: List[Dict] = info_downloader.download(REDDIT_POST_IDS)

    _ignored = len(REDDIT_POST_IDS) - len(ANNOTATIONS)
    cprint.yellow(
        f"Ignored {_ignored} posts: either removed, NSFW, or with (score < 2)."
    )
    # Save annotations with a format as similar as COCO annotations.
    ANNOTATIONS_TO_SAVE = {
        "info": {
            "start_date": dates_per_month[0].strftime("%Y-%m-%d"),
            "end_date": dates_per_month[-1].strftime("%Y-%m-%d"),
            "url": "https://redcaps.xyz",
            "version": redcaps.__version__,
        },
        "annotations": ANNOTATIONS,
    }
    if not save_to.endswith(".json"):
        # `output` is provided as a directory path. Save annotations inside.
        monthstr = yyyy_mm.strftime("%Y-%m")
        output = os.path.join(save_to, f"{subreddit}_{monthstr}.json")

    os.makedirs(os.path.dirname(output) or os.curdir, exist_ok=True)
    json.dump(ANNOTATIONS_TO_SAVE, open(output, "w"))
    cprint.green(f"[{monthstr}] Saved annotations at {output}.\n")


@click.command()
# fmt: off
@click.option(
    "-a", "--annotations", "annotations_filepath", type=click.Path(exists=True),
    help="Path to annotations for downloading images.",
)
@click.option(
    "-o", "--save-to", type=click.Path(), default="./datasets/redcaps/images",
    help="""Path to a directory to save images. Images will be saved in sub-
    directories - a different one per subreddit.""",
)
@click.option(
    "-z", "--resize", type=int, default=512,
    help="""Resize longer edge of image, preserving aspect ratio. Set to -1 to
    prevent resizing.""",
)
@click.option(
    "-u", "--update-annotations", is_flag=True,
    help="""Whether to update annotations (in-place) - remove annotations for
    which the images failed to download.""",
)
@click.option(
    "-j", "--workers", type=int, default=4,
    help="Number of workers to download images in parallel.",
)
def download_imgs(
    annotations_filepath: str,
    save_to: str,
    resize: int,
    update_annotations: bool,
    workers: int,
):
    # Load annotations to download images. Image URL available as "url".
    ANNOTATIONS: Dict[str, Any] = json.load(open(annotations_filepath))
    image_downloader = ImageDownloader(longer_resize=resize)

    # Parallelize image downloads.
    with mp.Pool(processes=workers) as p:

        worker_args: List[Tuple] = []
        for ann in ANNOTATIONS["annotations"]:
            image_savepath = os.path.join(
                save_to, ann["subreddit"], f"{ann['image_id']}.jpg"
            )
            if not os.path.exists(image_savepath):
                worker_args.append((ann["url"], image_savepath, image_downloader))

        # Collect download status of images in these annotations (True/False).
        download_status: List[bool] = []

        with tqdm(total=len(worker_args), desc="Downloading Images") as pbar:
            for _status in p.imap(_image_worker, worker_args):
                download_status.append(_status)
                pbar.update()

    # How many images were downloaded?
    num_downloaded = sum(download_status)
    cprint.green(
        f"Downloaded {num_downloaded}/{len(worker_args)} images "
        f"from {annotations_filepath}!"
    )
    # Optionally remove annotations for which images were unavailable.
    if update_annotations:
        ANNOTATIONS["annotations"] = [
            ann
            for ann, downloaded in zip(ANNOTATIONS["annotations"], download_status)
            if downloaded
        ]

        cprint.white(f"Saving updated annotations...")
        json.dump(ANNOTATIONS, open(annotations_filepath, "w"))
        cprint.green(f"Saved updated annotations at {annotations_filepath}!")


def _image_worker(args):
    r"""Helper method for parallelizing image downloads."""
    image_url, image_savepath, image_downloader = args

    download_status = image_downloader.download(image_url, save_to=image_savepath)

    # Sleep for 2 seconds for Imgur, and 0.1 seconds for Reddit and Flickr.
    # This takes care of all request rate limits.
    if "imgur" in image_url:
        time.sleep(2.0)
    else:
        time.sleep(0.1)

    return download_status
