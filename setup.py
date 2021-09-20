# Copyright (c) Karan Desai (https://kdexd.xyz), The University of Michigan.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import codecs
import os

from setuptools import setup


def get_version(rel_path: str):

    here = os.path.abspath(os.path.dirname(__file__))
    with codecs.open(os.path.join(here, rel_path), "r") as fp:
        for line in fp.read().splitlines():
            if line.startswith("__version__"):
                delim = '"' if '"' in line else "'"
                return line.split(delim)[1]


setup(
    name="redcaps",
    version=get_version("redcaps/__init__.py"),
    author="Karan Desai",
    python_requires=">=3.6",
    entry_points={"console_scripts": ["redcaps=redcaps.main:main"]},
    license="MIT",
    zip_safe=True,
)
