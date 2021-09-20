# Copyright (c) Karan Desai (https://kdexd.xyz), The University of Michigan.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import json
import os
import sys
import urllib
from typing import Dict, List

import click
from tqdm import tqdm

import redcaps._color_print as cprint

# fmt: off
# Two common options for all commands in this module.
annotation_option = click.option(
    "-a", "--annotations", "annotations_filepath", type=click.Path(exists=True),
    help="""Path to RedCaps annotations that need to be filtered. NOTE: this
    file will be modified inplace: some annotations will be removed! Make a
    backup if you wish to.""",
)
image_option = click.option(
    "-i", "--images", "images_dirpath", type=click.Path(exists=True),
    default="./datasets/redcaps/images",
    help="""Path to RedCaps image directory. This directory is expected to have
    subreddit specific sub-directories containing images.""",
)
# fmt: on


# Github repositories for filtering sources, to be added in annotations info.
WORDS_REPO: str = "LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words"
NSFW_REPO: str = "gantman/nsfw_model"
FACES_REPO: str = "redcaps-dataset/pytorch-retinaface"


@click.command()
@annotation_option
@image_option
def filter_words(annotations_filepath: str, images_dirpath: str):
    r"""Remove annotations (and their images) which contain bad words."""
    # Argument docstring is provided by click `help`.

    # Read annotations, keys: {"info", "annotations"}
    ANNOTATIONS: Dict = json.load(open(annotations_filepath))

    # Exit if this file has already been filtered, check via `info`.
    if "word_filter" in ANNOTATIONS["info"]:
        cprint.red(f"{annotations_filepath} has already been word-filtered.")
        sys.exit(0)

    # Read the blocklist of 'bad' words from the Github repo.
    blockwords_file = urllib.request.urlopen(
        f"https://raw.githubusercontent.com/{WORDS_REPO}/master/en"
    )
    blockwords: List[str] = [
        line.decode("utf-8").replace("\n", "") for line in blockwords_file
    ]
    # Gather a list of image IDs to remove.
    ids_to_remove: List[str] = []

    for ann in tqdm(ANNOTATIONS["annotations"], desc="Filtering"):
        for bad in blockwords:

            # Pad the word and caption with whitespaces, and do exact match.
            if f" {bad} " in f" {ann['caption']} ":
                cprint.yellow(f"'{bad}' in {ann['image_id']}: {ann['caption']}.")
                ids_to_remove.append(ann["image_id"])
                break

    cprint.white(f"Annotations with any blocklist words: {len(ids_to_remove)}")

    # Delete images and remove their annotations.
    ANNOTATIONS["annotations"] = _remove_images_and_annotations(
        ANNOTATIONS["annotations"], ids_to_remove, images_dirpath
    )
    ANNOTATIONS["info"]["word_filter"] = {
        "num_removed": len(ids_to_remove),
        "model": WORDS_REPO,
    }
    cprint.white(f"Saving updated annotations...")
    json.dump(ANNOTATIONS, open(annotations_filepath, "w"))
    cprint.green(f"Saved updated annotations at {annotations_filepath}!")


@click.command()
@annotation_option
@image_option
# fmt: off
@click.option(
    "-m", "--model", "model_path", type=click.Path(exists=True),
    default="./datasets/redcaps/models/nsfw.299x299.h5",
    help=f"Path to an H5 file containing Keras model weights.",
)
@click.option(
    "-t", "--confidence-threshold", type=float, default=0.9,
    help="""Minimum confidence value to flag NSFW images. The sum of softmax
    probabilities of "porn" and "hentai" must be higher than this to flag an
    image as NSFW.""",
)
# fmt: on
def filter_nsfw(
    annotations_filepath: str,
    images_dirpath: str,
    model_path: str,
    confidence_threshold: float,
):
    r"""
    Remove images (and their annotations) that are flagged as NSFW. The NSFW
    model weights are Keras Inception-v3 [299x299] weights provided by
    https://github.com/gantman/nsfw_model - need to be downloaded locally.
    """
    # Argument docstring is provided by click `help`.

    # Lazy import model.
    from redcaps.detectors.nsfw import NsfwDetector

    # Read annotations, keys: {"info", "annotations"}
    ANNOTATIONS: Dict = json.load(open(annotations_filepath))

    # Exit if this file has already been filtered.
    if "nsfw_filter" in ANNOTATIONS["info"]:
        cprint.red(f"{annotations_filepath} has already been NSFW-filtered.")
        sys.exit(0)

    # Get a list of all image paths from the annotations.
    image_paths: List[str] = [
        os.path.join(images_dirpath, ann["subreddit"], f"{ann['image_id']}.jpg")
        for ann in ANNOTATIONS["annotations"]
    ]
    image_paths = [_path for _path in image_paths if os.path.exists(_path)]

    predictions = NsfwDetector(model_path=model_path, verbose=True)(image_paths)

    # Gather a list of image IDs to remove - where sum(porn, hentai) > 0.9
    ids_to_remove: List[str] = [
        os.path.basename(_path).replace(".jpg", "")
        for _path, _pred in zip(image_paths, predictions)
        if _pred["porn"] + _pred["hentai"] > confidence_threshold
    ]
    cprint.white(f"Annotations (images) flagged as NSFW: {len(ids_to_remove)}")

    # Delete images and remove their annotations.
    ANNOTATIONS["annotations"] = _remove_images_and_annotations(
        ANNOTATIONS["annotations"], ids_to_remove, images_dirpath
    )
    # Add filtering info in annotations.
    ANNOTATIONS["info"]["nsfw_filter"] = {
        "num_removed": len(ids_to_remove),
        "model": NSFW_REPO,
        "confidence_threshold": confidence_threshold,
    }
    cprint.white(f"Saving updated annotations...")
    json.dump(ANNOTATIONS, open(annotations_filepath, "w"))
    cprint.green(f"Saved updated annotations at {annotations_filepath}!")


@click.command()
@annotation_option
@image_option
# fmt: off
@click.option(
    "-t", "--confidence-threshold", type=float, default=0.9,
    help="Minimum confidence value for face detections.",
)
# fmt: on
def filter_faces(
    annotations_filepath: str, images_dirpath: str, confidence_threshold: float
):
    r"""
    Remove images (and their annotations) that contain any detected faces. Face
    detector weights are from https://github.com/redcaps-dataset/pytorch-retinaface
    which is an easy-to-use fork of https://github.com/biubug6/pytorch-retinaface
    """
    # Argument docstring is provided by click `help`.

    # Lazy import model.
    from redcaps.detectors.faces import FaceDetector

    # Read annotations, keys: {"info", "annotations"}
    ANNOTATIONS: Dict = json.load(open(annotations_filepath))

    # Exit if this file has already been filtered.
    if "face_filter" in ANNOTATIONS["info"]:
        cprint.red(f"{annotations_filepath} has already been face-filtered.")
        sys.exit(0)

    # Get a list of all image paths from the annotations.
    image_paths: List[str] = [
        os.path.join(images_dirpath, ann["subreddit"], f"{ann['image_id']}.jpg")
        for ann in ANNOTATIONS["annotations"]
    ]
    image_paths = [_path for _path in image_paths if os.path.exists(_path)]

    model = FaceDetector(verbose=True)
    predictions = model(image_paths, conf_threshold=confidence_threshold)

    ids_to_remove: List[str] = [
        os.path.basename(_path).replace(".jpg", "")
        for _path, _pred in zip(image_paths, predictions)
        if len(_pred["boxes"]) > 0
    ]
    cprint.white(f"Annotations (images) with faces: {len(ids_to_remove)}")

    # Delete images and remove their annotations.
    ANNOTATIONS["annotations"] = _remove_images_and_annotations(
        ANNOTATIONS["annotations"], ids_to_remove, images_dirpath
    )
    # Add filtering info in annotations.
    ANNOTATIONS["info"]["face_filter"] = {
        "num_removed": len(ids_to_remove),
        "model": FACES_REPO,
        "confidence_threshold": confidence_threshold,
    }
    cprint.white(f"Saving updated annotations...")
    json.dump(ANNOTATIONS, open(annotations_filepath, "w"))
    cprint.green(f"Saved updated annotations at {annotations_filepath}!")


def _remove_images_and_annotations(
    annotations: List[Dict], ids_to_remove: List[str], images_dirpath: str
):
    r"""
    Given a list of annotations and image IDs, remove corresponding annotations
    and delete images from disk.
    """
    annotations_map = {ann["image_id"]: ann for ann in annotations}

    for _id in ids_to_remove:
        ann = annotations_map.pop(_id)

        # Remove image if it exists.
        image_path = os.path.join(images_dirpath, ann["subreddit"], f"{_id}.jpg")
        if os.path.exists(image_path):
            os.unlink(image_path)

    # Sort annotations by timestamp in case they got messed up.
    annotations = sorted(list(annotations_map.values()), key=lambda k: k["created_utc"])
    return annotations
