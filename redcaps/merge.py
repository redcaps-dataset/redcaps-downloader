# Copyright (c) Karan Desai (https://kdexd.xyz), The University of Michigan.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import glob
import json
import os
import sys
from datetime import datetime
from typing import Dict, List

import click

import redcaps
import redcaps._color_print as cprint


@click.command()
@click.argument("annotation_filepaths", nargs=-1, required=True)
# fmt: off
@click.option(
    "-o", "--save-to", type=click.Path(), required=True,
    help="Path to save merged annotations file.",
)
@click.option(
    "-d", "--delete-old", is_flag=True,
    help="Delete old annotation files after merging."
)
# fmt: on
def merge(annotation_filepaths: List[str], save_to: str, delete_old: bool):
    r"""
    Merge multiple RedCaps annotation files into a single file. The merged
    file will have combined annotations from all files, and the ``info``
    of merged file (start and end dates) will be set accordingly.

    Ideally, this method expects all files to be _un-filtered_ (words, NSFW
    and faces), and generated with the same RedCaps version. If merge is
    attempted on a mix of filtered and un-filtered files, then the individual
    ``info`` will be lost (eg. number of images removed by face detector).

    To prevent unexpected losses, ``--delete-old`` flag is not supported for
    non-uniform merging, and the command will abort.
    """

    # Expand path globs from arguments and gather file paths for merging.
    ALL_ANNOTATION_FILEPATHS: List[str] = []
    for afp in annotation_filepaths:
        ALL_ANNOTATION_FILEPATHS.extend(glob.glob(afp))

    # Return if only only file is provided.
    if len(ALL_ANNOTATION_FILEPATHS) < 2:
        cprint.red("Nothing to merge: provided less than two file paths!")
        return

    # Accumulate annotations in this list.
    MERGED_ANNOTATIONS: List[Dict] = []

    # Gather ``start_date`` and ``end_date`` from each file.
    all_start_dates: List[datetime] = []
    all_end_dates: List[datetime] = []

    for afp in sorted(ALL_ANNOTATION_FILEPATHS):
        annotations = json.load(open(afp))

        # Add "annotations" from this file.
        MERGED_ANNOTATIONS.extend(annotations["annotations"])

        # --------------------------------------------------------------------
        # Handle info while merging.
        # --------------------------------------------------------------------
        all_start_dates.append(
            datetime.strptime(annotations["info"]["start_date"], "%Y-%m-%d")
        )
        all_end_dates.append(
            datetime.strptime(annotations["info"]["end_date"], "%Y-%m-%d")
        )
        # Check whether version is same as current for merging.
        file_version = annotations["info"]["version"]
        if file_version != redcaps.__version__:
            cprint.yellow(
                f"Version mismatch for merge: {afp} has {file_version} and "
                f"package has {redcaps.__version__}!"
            )
            # For version mismatch, `--delete-old` is not allowed.
            if delete_old:
                cprint.red("Please run without '--delete-old' flag. Aborting!")
                sys.exit(0)

        # Check whether the file is already filtered.
        is_filtered = [
            key
            for key in {"word_filter", "nsfw_filter", "face_filter"}
            if key in annotations["info"]
        ]
        if is_filtered:
            cprint.yellow(f"{afp} filter info will not be included in merged file!")

            # For mixed un-filtered/filtered files, `--delete-old` is not allowed.
            if delete_old:
                cprint.red("Please run without '--delete-old' flag. Aborting!")
                sys.exit(0)

        # --------------------------------------------------------------------

    # Take uniques among annotations by ID.
    MERGED_ANNOTATIONS = {ann["image_id"]: ann for ann in MERGED_ANNOTATIONS}
    MERGED_ANNOTATIONS = list(MERGED_ANNOTATIONS.values())

    # Sort annotations by timestamp.
    MERGED_ANNOTATIONS = sorted(MERGED_ANNOTATIONS, key=lambda k: k["created_utc"])

    annotations_to_save = {
        "info": {
            "start_date": min(*all_start_dates).strftime("%Y-%m-%d"),
            "end_date": max(*all_end_dates).strftime("%Y-%m-%d"),
            "url": "https://redcaps.xyz",
            "version": redcaps.__version__,
        },
        "annotations": MERGED_ANNOTATIONS,
    }
    # Save the merged annotations file.
    cprint.green(f"Saving merged file at {save_to}.")

    cprint.white(f"Saving merged annotations at {save_to}...")
    os.makedirs(os.path.dirname(save_to) or os.curdir, exist_ok=True)
    json.dump(annotations_to_save, open(save_to, "w"))
    cprint.green(f"Done!")

    # Optionally delete old files.
    if delete_old:
        cprint.red("Deleting old file paths after merging...")

        for old_afp in ALL_ANNOTATION_FILEPATHS:

            # In case the merged file is saved at the same path as one of the
            # old files, make sure to not delete it!
            if os.path.abspath(old_afp) != os.path.abspath(save_to):
                os.unlink(old_afp)
                cprint.red(f"Deleted {old_afp}!")
