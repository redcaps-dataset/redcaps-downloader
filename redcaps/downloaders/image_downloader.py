# Copyright (c) Karan Desai (https://kdexd.xyz), The University of Michigan.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import io
import os

import requests
from PIL import Image


class ImageDownloader(object):
    r"""
    Download an image from a URL and save it on disk. This downloader handles
    multiple edge-cases, and is specifcially suited for RedCaps images, all of
    which are sourced from Reddit (``i.redd.it``), Imgur (``i.imgur.com``) or
    Flickr (``farm.static.flickr.com``).

    Args:
        longer_resize: Resize the longer edge of image to this size before
            saving to disk (preserve aspect ratio). Set to -1 to avoid any
            resizing. Defaults to 512.
    """

    def __init__(self, longer_resize: int = 512):
        self.longer_resize = longer_resize

    def download(self, url: str, save_to: str) -> bool:
        r"""
        Download image from ``url`` and save it to ``save_to``.

        Args:
            url: Image URL to download from.
            save_to: Local path to save the downloaded image.

        Returns:
            Boolean variable indicating whether the download was successful
            (``True``) or not (``False``).
        """

        try:
            # 'response.content' will have our image (as bytes) if successful.
            response = requests.get(url)

            # Check if image was downloaded (response must be 200). One exception:
            # Imgur gives response 200 with "removed.png" image if not found.
            if response.status_code != 200 or "removed.png" in response.url:
                return False

            # Write image to disk if it was downloaded successfully.
            pil_image = Image.open(io.BytesIO(response.content)).convert("RGB")

            # Resize image to longest max size while preserving aspect ratio if
            # longest max size is provided (not -1), and image is bigger.
            if self.longer_resize > 0:
                image_width, image_height = pil_image.size

                scale = self.longer_resize / float(max(image_width, image_height))

                if scale != 1.0:
                    new_width, new_height = tuple(
                        int(round(d * scale)) for d in (image_width, image_height)
                    )
                    pil_image = pil_image.resize((new_width, new_height))

            # Save the downloaded image to disk.
            os.makedirs(os.path.dirname(save_to), exist_ok=True)
            pil_image.save(save_to)

            return True

        except Exception:
            return False
