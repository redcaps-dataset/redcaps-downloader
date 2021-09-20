# Copyright (c) Karan Desai (https://kdexd.xyz), The University of Michigan.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from itertools import product
from math import ceil
from typing import Dict, List

import numpy as np
import torch
from PIL import Image
from tqdm import tqdm


class FaceDetector(object):
    r"""
    This class provides a simple wrapper on an off-the-shelf face detector used
    to detect images with faces in RedCaps (which are then removed).

    The model used is RetinaFace with ResNet-50 backbone, as introduced by
    `Deng et al. CVPR 2020 <https://arxiv.org/abs/1905.00641>`_. We use the
    pre-trained weights from a public implementation, but host them separately
    with renamed modules for better ease-of-use.

    - Original weights from: https://github.com/biubug6/pytorch_retinaface
    - Public fork used here: https://github.com/redcaps-dataset/pytorch-retinaface

    Args:
        verbose: Whether to display detection progress on multiple images.
    """

    def __init__(self, verbose: bool = True):

        # Initialize face detection model using torch hub. This does not require
        # cloning or set up redcaps-dataset/pytorch-retinaface repo.
        self.model = torch.hub.load(
            "redcaps-dataset/pytorch-retinaface",
            model="retinaface_resnet50",
            pretrained=True,
        )
        self.verbose = verbose

        # Hyperparameters speciic to RetinaFace. These are hard-coded as private
        # class variables so it is difficult to accidentally change them.
        self.__min_sizes = [[16, 32], [64, 128], [256, 512]]
        self.__steps = [8, 16, 32]

        # NMS threshold for intersection-over-union to suppress low confidence
        # or small boxes.
        self.__nms_threshold = 0.4

        # Number of boxes with highest confidence to retain before performing NMS.
        # Setting small value speeds up NMS.
        self.__pre_nms_topk = 500

    def __call__(self, image_paths: List[str], conf_threshold: float = 0.9):
        r"""
        Perform face detection on a given list of image paths. This code processes
        a single image individually without batching, and operates only on CPU.

        Args:
            image_paths: List of image paths to perform face detection.
            conf_threshold: Confidence threshold of box predictions. Predictions
                with a lower confidence score will be removed _before NMS_. Lower
                threshold generates more predictions, but they will be noisy
                with lot of false positives. Defaults to 0.9 (recommended).
        """

        # Define a range iterator, either silent or verbose (with progress bar).
        range_iter = range(len(image_paths))
        if self.verbose:
            range_iter = tqdm(range_iter, desc="Face detection")

        # Gather predictions for each image in this list. It will have same length
        # as `image_paths`. keys: {"boxes", "scores"}
        predictions: List[Dict] = []

        for idx in range_iter:
            image_path = image_paths[idx]

            # Read image.
            image = np.array(Image.open(image_path).convert("RGB"))
            image_h, image_w, _ = image.shape

            # Convert RGB to BGR and subtract ImageNet color mean.
            image = image[:, :, ::-1] - (104, 117, 123)

            # Convert to a BCHW torch tensor.
            image = torch.from_numpy(image).permute(2, 0, 1).unsqueeze(0)
            image = image.to(dtype=torch.float32)

            # Get bounding box locations and confidence scores.
            with torch.no_grad():
                loc, conf, _ = self.model(image)

            # Remove batch dimension since only one image was processed.
            loc, conf = loc[0], conf[0]

            # Move on to next image if no detections were found.
            scores = conf.numpy()[:, 1]
            confident_box_indices = np.where(scores > conf_threshold)[0]

            if len(confident_box_indices) == 0:
                predictions.append({"boxes": [], "scores": []})
                continue

            # Get box co-ordinates xxyy in [0, 1] normalized range.
            priors = self._get_anchors(image_h, image_w)
            centers = priors[:, :2] + loc[:, :2] * 0.1 * priors[:, 2:]
            sizes = priors[:, 2:] * torch.exp(loc[:, 2:] * 0.2)

            # Ignore boxes with low confidence scores.
            boxes = torch.cat((centers, sizes), 1)
            boxes = boxes[confident_box_indices]
            scores = scores[confident_box_indices]

            # Convert centers and sizes to xxyy co-ordinates.
            boxes[:, :2] -= boxes[:, 2:] / 2
            boxes[:, 2:] += boxes[:, :2]

            # Un-normalize xxyy box co-ordinates to image dimensions.
            scale = torch.tensor([image_w, image_h, image_w, image_h])
            boxes = (boxes * scale).numpy()

            # Keep top-K boxes before non-maximal suppression.
            order = scores.argsort()[::-1][: self.__pre_nms_topk]
            boxes = boxes[order]
            scores = scores[order]

            # ----------------------------------------------------------------
            # Perform non-maximal suppression of boxes.
            x1 = boxes[:, 0]
            y1 = boxes[:, 1]
            x2 = boxes[:, 2]
            y2 = boxes[:, 3]

            areas = (x2 - x1 + 1) * (y2 - y1 + 1)
            order = scores.argsort()[::-1]

            keep = []
            while order.size > 0:
                i = order[0]
                keep.append(i)
                xx1 = np.maximum(x1[i], x1[order[1:]])
                yy1 = np.maximum(y1[i], y1[order[1:]])
                xx2 = np.minimum(x2[i], x2[order[1:]])
                yy2 = np.minimum(y2[i], y2[order[1:]])

                w = np.maximum(0.0, xx2 - xx1 + 1)
                h = np.maximum(0.0, yy2 - yy1 + 1)
                inter = w * h
                ovr = inter / (areas[i] + areas[order[1:]] - inter)

                inds = np.where(ovr <= self.__nms_threshold)[0]
                order = order[inds + 1]

            boxes = boxes[keep].tolist()
            scores = scores[keep].tolist()
            # ----------------------------------------------------------------

            predictions.append({"boxes": boxes, "scores": scores})

        return predictions

    def _get_anchors(self, image_h: int, image_w: int):
        r"""
        Get fixed anchors of different sizes per pixel.

        Args:
            image_w: Image height.
            image_w: Image width.
        """

        feat_maps = [[ceil(image_h / s), ceil(image_w / s)] for s in self.__steps]
        anchors = []

        for k, f in enumerate(feat_maps):
            min_size = self.__min_sizes[k]
            for i, j in product(range(f[0]), range(f[1])):
                for _ms in min_size:
                    s_kx = _ms / image_w
                    s_ky = _ms / image_h
                    dense_cx = [x * self.__steps[k] / image_w for x in [j + 0.5]]
                    dense_cy = [y * self.__steps[k] / image_h for y in [i + 0.5]]
                    for cy, cx in product(dense_cy, dense_cx):
                        anchors += [cx, cy, s_kx, s_ky]

        # back to torch land
        output = torch.Tensor(anchors).view(-1, 4)
        return output
