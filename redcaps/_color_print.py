# Copyright (c) Karan Desai (https://kdexd.xyz), The University of Michigan.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

r"""Simple module to print colorful text to terminal."""

from click import echo, style


def red(text: str):
    echo(style(text, fg="red", bold=True))


def green(text: str):
    echo(style(text, fg="green", bold=True))


def yellow(text: str):
    echo(style(text, fg="yellow", bold=True))


def white(text: str):
    echo(style(text, fg="white", bold=True))
