# RedCaps Downloader

This repository provides the official command-line tool for downloading and extending the [RedCaps dataset](https://openreview.net/forum?id=VjJxBi1p9zh).
Users can seamlessly download images of officially released annotations as well as download more image-text data from any subreddit over an arbitrary time-span.

## Installation

This tool requires Python 3.8 or higher. We recommend using conda for setup.
Download [Anaconda or Miniconda](https://conda.io/docs/user-guide/install/download.html) first.
Then follow these steps:

```bash
# Clone the repository.
git clone https://github.com/redcaps-dataset/redcaps-downloader
cd redcaps-downloader

# Create a new conda environment.
conda create -n redcaps python=3.8
conda activate redcaps

# Install dependencies along with this code.
pip install -r requirements.txt
python setup.py develop
```

## Basic usage: Download official RedCaps dataset

We expect most users will only require this functionality.
Follow these steps to download the official RedCaps annotations and images
and arrange all the data in recommended directory structure:

```text
/path/to/redcaps/
├── annotations/
│   ├── abandoned_2017.json
│   ├── abandoned_2017.json
│   ├── ...
│   ├── itookapicture_2019.json
│   ├── itookapicture_2020.json
│   ├── <subreddit>_<year>.json
│   └── ...
│
└── images/
    ├── abandoned/
    │   ├── guli1.jpg
    |   └── ...
    │
    ├── itookapicture/
    │   ├── 1bd79.jpg
    |   └── ...
    │
    ├── <subreddit>/
    │   ├── <image_id>.jpg
    │   ├── ...
    └── ...
```

1. Create an empty directory and symlink it relative to this code directory:
    ```bash
    cd redcaps-downloader

    # Edit path here:
    mkdir -p /path/to/redcaps
    ln -s /path/to/redcaps ./datasets/redcaps
    ```

2. Download official RedCaps annotations from Dropbox and unzip them.
    ```bash
    cd datasets/redcaps
    wget https://www.dropbox.com/s/cqtdpsl4hewlli1/redcaps_v1.0_annotations.zip?dl=1
    unzip redcaps_v1.0_annotations.zip
    ```

3. Download images by using `redcaps download-imgs` command (for a single annotation file).
    ```bash
    for ann_file in ./datasets/redcaps/annotations/*.json; do
        redcaps download-imgs -a $ann_file --save-to path/to/images --resize 512 -j 4
        # Set --resize -1 to turn off resizing shorter edge (saves disk space).
    done
    ```
    Parallelize download by changing `-j`. RedCaps images are sourced from Reddit,
    Imgur and Flickr, each have their own request limits. This code contains
    approximate sleep intervals to manage them. Use multiple machines (= different
    IP addresses) or a cluster to massively parallelize downloading.

That's it, you are all set to use RedCaps!

### Organizing the dataset as TAR files

We also provide a lightweight and standalone script to organize the dataset as TAR files
of images and JSON annotations (subreddit name and caption),
in a format compatible with [PyTorch Webdataset](https://github.com/webdataset/webdataset).
See `scripts/make_tarfiles.py` for usage instructions.


## Advanced usage: Create your own RedCaps-like dataset

Apart from downloading the officially released dataset, this tool supports
downloading image-text data from any subreddit – you can reproduce the entire
collection pipeline as well as create your own _variant_ of RedCaps! Here,
we show how to collect annotations from [`r/roses`](https://reddit.com/r/roses)
(2020) as an example. Follow these steps for any subreddit and years.

### Additional one-time setup instructions

RedCaps annotations are extracted from image post metadata, which are served by
the Pushshift API and official Reddit API. These APIs are authentication-based,
and one must sign up for developer access to obtain API keys (one-time setup):

1. Copy `./credentials.template.json` to `./credentials.json`. Its contents are
   as follows:
    ```json
    {
        "reddit": {
            "client_id": "Your client ID here",
            "client_secret": "Your client secret here",
            "username": "Your Reddit username here",
            "password": "Your Reddit password here",
            "user_agent": "<username>: <device name>"
        },
        "imgur": {
            "client_id": "Your client ID here",
            "client_secret": "Your client secret here"
        }
    }
    ```

2. Register a [new Reddit app here](https://www.reddit.com/prefs/apps). Reddit
   will provide a _Client ID_ and _Client Secret_ tokens - fill them in
   `./credentials.json`. For more details, refer to the
   [Reddit OAuth2 wiki](https://github.com/reddit-archive/reddit/wiki/OAuth2).
   Enter your Reddit account name and password in `./credentials.json`. Set
    _User Agent_ to anything and keep it unchanged (e.g. your name).

3. Register a new Imgur App [by following instructions here](https://apidocs.imgur.com/).
   Fill the provided _Client ID_ and _Client Secret_ in `./credentials.json`.

4. Download pre-trained weights of an [NSFW detection model](https://github.com/gantman/nsfw_model).
    ```bash
    wget https://s3.amazonaws.com/nsfwdetector/nsfw.299x299.h5 -P ./datasets/redcaps/models
    ```

### Data collection from [`r/roses`](https://reddit.com/r/roses) (2020)

1. **`download-anns`:** Dowload annotations of image posts made in a single month
   (e.g. January).
    ```bash
    redcaps download-anns --subreddit roses --month 2020-01 -o ./datasets/redcaps/annotations

    # Similarly, download annotations for all months of 2020:
    for ((month = 1; month <= 12; month += 1)); do
        redcaps download-anns --subreddit roses --month 2020-$month -o ./datasets/redcaps/annotations
    done
    ```
    - **NOTE:** You may not get _all_ the annotations present in official release
      as some of them may have disappeared (deleted) over time. After this step,
      the dataset directory would contain 12 annotation files:
    ```text
        ./datasets/redcaps/
        └── annotations/
            ├── roses_2020-01.json
            ├── roses_2020-02.json
            ├── ...
            └── roses_2020-12.json
    ```

2. **`merge`:** Merge all the monthly annotation files into a single file.
    ```bash
    redcaps merge ./datasets/redcaps/annotations/roses_2020-* \
        -o ./datasets/redcaps/annotations/roses_2020.json --delete-old
    ```
    - `--delete-old` will remove individual files after merging. After this
      step, the merged file will replace individual monthly files:
    ```text
        ./datasets/redcaps/
        └── annotations/
            └── roses_2020.json
    ```

3. **`download-imgs`:** Download all images for this annotation file. This step
   is same as (3) in basic usage.
    ```bash
    redcaps download-imgs --annotations ./datasets/redcaps/annotations/roses_2020.json \
        --resize 512 -j 4 -o ./datasets/redcaps/images --update-annotations
    ```
   - `--update-annotations` removes annotations whose images were not downloaded.

4. **`filter-words`:** Filter all instances whose captions contain potentially
   harmful language. Any caption containing one of the
   [400 blocklisted words](https://github.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words)
   will be removed. This command modifies the annotation file in-place and
   deletes the corresponding images from disk.
    ```bash
    redcaps filter-words --annotations ./datasets/redcaps/annotations/roses_2020.json \
        --images ./datasets/redcaps/images
    ```

5. **`filter-nsfw`:** Remove all instances having images that are flagged by an
   [off-the-shelf NSFW detector](https://github.com/gantman/nsfw-model). This
   command also modifies the annotation file in-place and deletes the corresponding
   images from disk.
    ```bash
    redcaps filter-nsfw --annotations ./datasets/redcaps/annotations/roses_2020.json \
        --images ./datasets/redcaps/images \
        --model ./datasets/redcaps/models/nsfw.299x299.h5
    ```

5. **`filter-faces`:** Remove all instances having images with faces detected by an
   [off-the-shelf face detector](https://github.com/redcaps-dataset/pytorch-retinaface).
   This command also modifies the annotation file in-place and deletes the
   corresponding images from disk.
    ```bash
    redcaps filter-faces --annotations ./datasets/redcaps/annotations/roses_2020.json \
        --images ./datasets/redcaps/images  # Model weights auto-downloaded
    ```

6. **`validate`:** All the above steps create a single annotation file (and downloads
   images) similar to official RedCaps annotations. To double-check this, run the
   following command and expect no errors to be printed.
    ```bash
    redcaps validate --annotations ./datasets/redcaps/annotations/roses_2020.json
    ```


## Citation

If you find this code useful, please consider citing:

```text
@inproceedings{desai2021redcaps,
    title={{RedCaps: Web-curated image-text data created by the people, for the people}},
    author={Karan Desai and Gaurav Kaul and Zubin Aysola and Justin Johnson},
    booktitle={NeurIPS Datasets and Benchmarks},
    year={2021}
}
```
