# Copyright (c) Karan Desai (https://kdexd.xyz), The University of Michigan.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import List

import numpy as np
import tensorflow_hub as hub
from tensorflow import keras
from tqdm import tqdm


class NsfwDetector(object):
    r"""
    This class provides a simple wrapper on an off-the-shelf NSFW detector used
    to detect potentially NSFW images in RedCaps (which are then removed).

    - Pre-trained weights from: https://github.com/gantman/nsfw_model

    Args:
        model_path: Path to HDF file containing pre-trained Inception v3 weights.
        verbose: Whether to display detection progress on multiple images.
    """

    def __init__(self, model_path: str, verbose: bool = True):

        # Initialize NSFW detection model using keras and pre-trained weights.
        self.model = keras.models.load_model(
            model_path, custom_objects={"KerasLayer": hub.KerasLayer}
        )
        self.verbose = verbose

    def __call__(self, image_paths: List[str]):
        r"""
        Perform NSFW detection on a given list of image paths. This code processes
        batches of 32 images and operates only on CPU.

        Args:
            image_paths: List of image paths to perform NSFW detection.
        """

        # Define a range iterator, either silent or verbose (with progress bar).
        # Process images in batches of 32.
        range_iter = range(0, len(image_paths), 32)
        if self.verbose:
            range_iter = tqdm(range_iter, desc="NSFW detection")

        # Gather predictions for each image in this list. It will have same length
        # as `image_paths`. keys: {"drawing", "hentai", "neutral", "porn", "sexy"}
        predictions = []

        for idx in range_iter:
            # Prepare a batch of 32 images with 299x299 size.
            batch = [
                keras.preprocessing.image.load_img(_path, target_size=(299, 299))
                for _path in image_paths[idx : idx + 32]
            ]
            batch = [keras.preprocessing.image.img_to_array(img) / 255 for img in batch]

            # Make predictions and extend batch.
            predictions.extend(self.model.predict(np.asarray(batch)))

        # Convert predictions to dicts with readable keys.
        for idx, pred in enumerate(predictions):
            predictions[idx] = {
                "drawing": pred[0],
                "hentai": pred[1],
                "neutral": pred[2],
                "porn": pred[3],
                "sexy": pred[4],
            }

        return predictions
