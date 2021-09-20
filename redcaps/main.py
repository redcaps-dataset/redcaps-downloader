# Copyright (c) Karan Desai (https://kdexd.xyz), The University of Michigan.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import click

import redcaps._color_print as cp
from redcaps.download import download_anns, download_imgs
from redcaps.filter import filter_faces, filter_nsfw, filter_words
from redcaps.merge import merge
from redcaps.validate import validate


@click.version_option()
@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):

    # Using `redcaps` command by itself is not allowed.
    if ctx.invoked_subcommand is None:
        cp.yellow("RedCaps: Use redcaps --help for usage instructions.")


# Add subcommands to `redcaps` group. Here, they are added in the recommended
# order of their usage, to prepare a single annotation file for release.
main.add_command(download_anns)
main.add_command(download_imgs)
main.add_command(merge)

main.add_command(filter_words)
main.add_command(filter_nsfw)
main.add_command(filter_faces)

main.add_command(validate)
