# Copyright (c) Karan Desai (https://kdexd.xyz), The University of Michigan.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict

import click
from tqdm import tqdm

import redcaps._color_print as cprint


@click.command()
# fmt: off
@click.option(
    "-a", "--annotations", "annotations_filepath", type=click.Path(exists=True),
    help="Path to RedCaps annotations that need to be validated.",
)
# fmt: on
def validate(annotations_filepath: str):
    r"""
    Validate a RedCaps annotation file for release. This command performs basic
    checks on the file - whether it contain relevant ``info`` and whether it has
    been filtered to remove captions with _bad_ words (``redcaps filter-words``)
    and NSFW-flagged images (``redcaps filter-nsfw``) as well as images with
    detected faces (``redcaps filter-faces``). The file is not modified at all.
    """

    # Read annotations, keys: {"info", "annotations"}
    cprint.white(f"Validating {annotations_filepath}...")
    ANNOTATIONS: Dict = json.load(open(annotations_filepath))

    # Annotations file must not have any missing keys.
    for key in {"info", "annotations"}:
        if key not in ANNOTATIONS:
            cprint.red(f"'{key}' not found! Invalid file, aborting!")
            sys.exit(0)

    # If `info` is present, check all the relevant keys in `info`.
    if "info" in ANNOTATIONS:
        for key in {"start_date", "end_date", "url", "version"}:
            if key not in ANNOTATIONS["info"]:
                cprint.red(f"Info key '{key}' not found, invalid file!")

        # Check whether this file is filtered.
        if "word_filter" not in ANNOTATIONS["info"]:
            cprint.yellow(f"Word-filtering pending, run 'redcaps filter-words'")

        if "nsfw_filter" not in ANNOTATIONS["info"]:
            cprint.yellow(f"NSFW-filtering pending, run 'redcaps filter-nsfw'")

        if "face_filter" not in ANNOTATIONS["info"]:
            cprint.yellow(f"Face-filtering pending, run 'redcaps filter-faces'")

        # Check if all annotations are within time limits of info.
        start_utc = datetime.strptime(ANNOTATIONS["info"]["start_date"], "%Y-%m-%d")
        start_utc = start_utc.replace(tzinfo=timezone.utc)

        end_utc = datetime.strptime(ANNOTATIONS["info"]["end_date"], "%Y-%m-%d")
        end_utc = end_utc + timedelta(hours=24, seconds=-1)
        end_utc = end_utc.replace(tzinfo=timezone.utc)

        if "annotations" in ANNOTATIONS["annotations"]:
            for ann in tqdm(ANNOTATIONS["annotations"], desc="Check timestamps"):
                if not (start_utc <= ann["created_utc"] <= end_utc):
                    cprint.yellow(f"Found ID {ann['id']} outside time limits!")

    cprint.white("Done. If nothing was printed above then file is valid!")
