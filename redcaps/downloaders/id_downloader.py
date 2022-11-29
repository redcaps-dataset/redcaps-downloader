# Copyright (c) Karan Desai (https://kdexd.xyz), The University of Michigan.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import datetime
import json
import time
from typing import Dict, List, Union

import requests

import redcaps._color_print as cprint


class RedditIdDownloader(object):
    r"""
    Download IDs of image posts made to a particular subreddit on a single date.
    This downloader internally uses the `Pushshift API <pushshift.io>`_.

    Args:
        subreddit: Name of subreddit to download Reddit post IDs.
        date: Date of creation of the posts to be downloaded (in UTC).
    """

    def __init__(self, subreddit: str, date: Union[datetime.datetime, datetime.date]):
        self.subreddit = subreddit
        self.date = date

        # Convert date object to datetime object if necessary.
        if isinstance(self.date, datetime.date):
            # Initialized time to midnight (local time).
            self.date = datetime.datetime(date.year, date.month, date.day)

        self.date = self.date.replace(tzinfo=datetime.timezone.utc)

        # List of permissible domains. Pushshift v1 API allowed passing them in API
        # request, but beta API does not. So we keep them here to filter API response
        # and have backward compatibility with previous version of this downloader
        # that uses v1 API.
        self._allow_domains = [
            "reddit.com", "i.redd.it", "i.imgur.com", "imgur.com", "m.imgur.com"
        ]
        self._allow_domains.extend([f"farm{i}.static.flickr.com" for i in range(9)])
        self._allow_domains.extend([f"farm{i}.staticflickr.com" for i in range(9)])

    def download(self, time_window: float = 24.0) -> List[str]:
        r"""
        Download the list of Reddit post IDs from a single subreddit made on a
        single day. Pushshift API returns 100 IDs at a time. So for subreddits
        with heavy post volume (> 100 per day), IDs may need to be downloaded
        in smaller time windows.

        Args:
            time_window: Download posts in small time windows of these many hours.
                Must not be more than 24 (1 day). Defaults to 24.

        Returns:
            Submission IDs, base36 strings (e.g. ``["4qdg3x", "a2b4e6", ...]``).
        """

        # Gather Reddit post IDs in this list.
        REDDIT_IDS: List[str] = []

        # Set start time as YYYY-MM-DD 12:00:00 am UTC.
        # Set end time as YYYY-MM-DD 11:59:59 pm UTC.
        start = self.date
        end = start + datetime.timedelta(hours=24, seconds=-1)

        while start < end:
            REDDIT_IDS.extend(self._download_worker(start, time_window))

            # Advance the time window and sleep to stay within API rate limit.
            start += datetime.timedelta(hours=time_window)
            time.sleep(1)

        # De-duplicate IDs, just in case a post was retrieved twice.
        return list(set(REDDIT_IDS))

    def _download_worker(
        self, start_time: datetime, time_window: float = 24.0
    ) -> List[str]:
        r"""
        Helper method to download Reddit post IDs between ``start_time`` and
        ``start_time + time_window``. This method is used internally by
        :meth:`download`, and it handles two edge cases:

            1. If the Pushshift request fails, it attempts a retry.
            2. Pushshift can return 100 IDs per request. If 100 IDs are received,
               then it retries smaller time windows recursively.
        """

        # We download Reddit Reddit post IDs for a single day using Pushshift API.
        REDDIT_IDS: List[str] = []
        end_time = start_time + datetime.timedelta(hours=time_window, seconds=-1)

        # Gather all necessary params for Pushshift GET request payload.
        payload: Dict[str, str] = {
            "subreddit": self.subreddit,
            "after": str(int(start_time.timestamp())),
            "before": str(int(end_time.timestamp())),
            "size": "100",
            # Only get IDs, nothing else. We use official Reddit API for rest.
            "fields": "id",
            # Domain must be an image hosting service (for direct image links).
            # Exception: imgur.com and reddit.com (galleries) - handled separately.
            "domain": (
                "reddit.com,i.redd.it,i.imgur.com,imgur.com,m.imgur.com,"
                + ",".join([f"farm{i}.static.flickr.com" for i in range(9)])
                + ","
                + ",".join([f"farm{i}.staticflickr.com" for i in range(9)])
            ),
        }
        # GET request to download metadata for Reddit posts in this time window.
        # Keep retrying till we get OK response (200).
        status_code = 404
        while status_code != 200:
            response = requests.get(
                "https://api.pushshift.io/reddit/submission/search", params=payload
            )
            status_code = response.status_code
            time.sleep(1)

        response = json.loads(response.content)["data"]
        _ids = [r["id"] for r in response]

        if len(_ids) >= 100:
            # If we received 100 Reddit post IDs, then perhaps there are more
            # in this time window (due to high subreddit activity). So we
            # download IDs recursively with smaller time windows.
            mid_time = start_time + datetime.timedelta(hours=time_window / 2)
            _ids = self._download_worker(
                start_time, time_window / 2
            ) + self._download_worker(mid_time, time_window / 2)
        else:
            start_dtstr = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_dtstr = end_time.strftime("%Y-%m-%d %H:%M:%S")
            cprint.white(
                f"[{start_dtstr} - {end_dtstr}] Downloaded {len(_ids)} Reddit post IDs."
            )

        REDDIT_IDS.extend(_ids)
        return REDDIT_IDS
