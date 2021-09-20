# Copyright (c) Karan Desai (https://kdexd.xyz), The University of Michigan.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import json
import re
import sys
import time
from typing import Any, Dict, List

import ftfy
import praw
import requests
from tqdm import tqdm

import redcaps._color_print as cprint


class RedditInfoDownloader(object):
    r"""
    Download Reddit Info of a submission that is specified by its ID. This
    downloader internally uses the official Reddit API to retrieve information
    such as image URL, title (caption), score, permalink etc.

    Additionally, it deals with Imgur image URLs - converting gallery URLs to
    direct download links through the official Imgur API.

    Args:
        credentials: OAuth credentials for Reddit and Imgur APIs.
    """

    def __init__(self, credentials: Dict):
        self.reddit = praw.Reddit(
            client_id=credentials["reddit"]["client_id"],
            client_secret=credentials["reddit"]["client_secret"],
            user_agent=credentials["reddit"]["user_agent"],
        )
        self.imgur_client_id = credentials["imgur"]["client_id"]
        self.imgur_client_secret = credentials["imgur"]["client_secret"]

    def download(self, ids: List[str]) -> List[Dict[str, Any]]:

        # Convert to list if only a single ID is provided.
        if isinstance(ids, str):
            ids = [ids]

        # Add "t3_" prefix to IDs according to Reddit API instructions.
        ids = [f"t3_{id}" for id in ids]

        # Gather annotations in this list.
        ANNOTATIONS: List[Dict[str, Any]] = []

        for _info in tqdm(self.reddit.info(ids), "Downloading", total=len(ids)):

            # IMPORTANT: do not download any image posts that were deleted
            # from Reddit - either by the author, moderator, Reddit bots, etc.
            if _info.removed_by_category is not None:
                continue

            # Do not download NSFW-marked posts, and posts having score < 2.
            if _info.over_18 or _info.score < 2:
                continue

            # Cast the PRAW object to a native Python types.
            _info = vars(_info)
            _info["author"] = str(_info["author"])
            _info["subreddit"] = str(_info["subreddit"])

            # If this submission is a Reddit gallery ("reddit.com/gallery/..."),
            # then replace URL with static URL of first gallery image.
            if "reddit.com" in _info["url"] and "gallery" in _info["url"]:
                gallery_data = _info.get("gallery_data", None)

                if gallery_data is not None and len(gallery_data.get("items", [])) > 0:
                    img_id = _info["gallery_data"]["items"][0]["media_id"]
                    _info["url"] = f"https://i.redd.it/{img_id}.jpg"
                else:
                    # This submission does not contain an image, skip altogether.
                    continue
            elif "imgur" in _info["url"]:
                _info["url"] = self._fix_image_url(_info["url"])

            ANNOTATIONS.append(
                {
                    "image_id": _info["id"],
                    "subreddit": _info["subreddit"].lower(),
                    "url": _info["url"],
                    "caption": self._sanitize_caption(_info["title"]),
                    "raw_caption": _info["title"],
                    "score": _info["score"],
                    "author": _info["author"],
                    "created_utc": int(_info["created_utc"]),
                    "permalink": _info["permalink"],
                }
            )

        return ANNOTATIONS

    def _fix_image_url(self, image_url: str) -> str:
        r"""
        Get a static image URL from an Imgur URL. This method must be called in
        :meth:`download` method for every post info object that has ``imgur.com``
        image URL:

            1. Imgur direct download links (``i.imgur.com``): left unchanged.
            2. Imgur post URLs (``imgur.com``): simple string manipulation,
               for example ``imgur.com/aBcDeF`` becomes ``i.imgur.com/aBcDeF.jpg``.
            3. Imgur album/gallery URLs (``imgur.com/a/``, ``imgur.com/gallery/``):
               Use Imgur API to get direct link of the first image.
            4. Imgur mobile URLs (``m.imgur.com``): handles this case same as (2).

        Args:
            image_url: Imge URL from Imgur (must contain ``imgur.com``).

        Returns:
            Imgur static URL starting as ``i.imgur.com/...``.
        """

        if "i.imgur.com" in image_url:
            return image_url

        # Convert mobile URL to normal URL.
        image_url = image_url.replace("m.imgur.com", "imgur.com")

        # First, handle ``imgur.com`` post URLs.
        if "/a/" not in image_url and "gallery" not in image_url:
            direct_link = image_url.replace("imgur", "i.imgur")

            # Add ``.jpg`` suffix, avoiding duplication.
            return direct_link.replace(".jpg", "") + ".jpg"
        else:
            # For Imgur albums and galleries, get static URL of first image.
            # If posted to a subreddit, the post titles may be most relevant to
            # the displayed image in Reddit (first image).

            # "album" and "gallery" are jointly referred as "album" henceforth.
            album_id = image_url.split("/")[-1]

            # GET request to download static URL of image from Imgur link.
            try:
                response = requests.get(
                    f"https://api.imgur.com/3/album/{album_id}",
                    headers={"Authorization": f"Client-ID {self.imgur_client_id}"},
                )
                content = json.loads(response.content)
                direct_link = content["data"]["images"][0]["link"]

                # Imgur allows 12500 client requests per day, and 500 user requests
                # per hour. If client requests exceed limit, Imgur will block the
                # IP for 1 month!
                if int(response.headers["X-RateLimit-UserRemaining"]) <= 3:
                    # Check the timestamp when Imgur will reset the user limit.
                    reset_utc = int(response.headers["X-RateLimit-UserReset"])
                    sleepdiff = reset_utc - int(time.time()) + 1

                    cprint.yellow(
                        "Exceeded Imgur UserLimit, sleeping till reset: "
                        f"{sleepdiff} seconds."
                    )
                    time.sleep(sleepdiff)

                if int(response.headers["X-RateLimit-ClientRemaining"]) <= 500:
                    cprint.red(
                        "!! Exceeded Imgur ClientLimit, pause script for 1 day !!"
                    )
                    sys.exit(0)
            except Exception:
                direct_link = "https://i.imgur.com/removed.png"

        return direct_link

    @staticmethod
    def _sanitize_caption(caption: str) -> str:
        r"""
        Sanitize a caption: lowercase, strip whitespaces, and remove non-unicode
        characters. Then remove all sub-strings enclosed in brackets ``[]()``
        and replace usernames (starting with ``@``) with ``<usr>`` token.

        Args:
            caption: Caption of a single Reddit post, to be sanitized.

        Returns:
            _Sanitized_ caption with the appropriate sub-strings removed.
        """

        # Remove caption sub-strings matching these patterns. Match will not be
        # case-sensitive. Specifically, remove things in brackets, and remove
        # image resolutions.
        regex_candidates = [r"[\[\(].*?[\]\)]", r"\s*\d+\s*[x×\*\,]\s*\d+\s*"]

        # First remove all accents and widetexts from caption.
        caption = ftfy.fix_text(caption, normalization="NFKD").lower()

        # Remove all above regex candidates.
        for regexc in regex_candidates:
            caption = re.sub(regexc, "", caption, flags=re.IGNORECASE)

            # Remove multiple whitespaces, and leading or trailing whitespaces.
            # We have to do it every time we remove a regex candidate as it may
            # combine surrounding whitespaces.
            caption = re.sub(r"\s+", " ", caption).strip()

        # In this end, replace all usernames with `<usr>` token.
        caption = re.sub(r"\@[_\d\w\.]+", "<usr>", caption, flags=re.IGNORECASE)

        # Remove all emojis and non-latin characters.
        caption = caption.encode("ascii", "ignore").decode("utf-8")
        return caption
