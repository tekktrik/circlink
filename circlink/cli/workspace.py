# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

"""
The sub-script for handling the workspace options for ``circlink``.

Author(s): Alec Delaney (Tekktrik)
"""

from typer import Argument, Exit, Option, Typer

from circlink import CURRENT_WORKSPACE_FILE
from circlink.backend import get_links_list

workspace_app = Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Save and load workspace settings.",
)


def get_cws_name(name: str = "") -> str:
    """Get the current workspace name."""
    with open(CURRENT_WORKSPACE_FILE, encoding="utf-8") as cwsfile:
        name = cwsfile.read()
    if not name:
        print("Current workspace is not named")
        raise Exit()
    return name


@workspace_app.command()
def current() -> None:
    """Get the current workspace name."""
    print(get_cws_name())


@workspace_app.command(name="list")
def workspace_list() -> None:
    """List all existing workspaces."""

    # TODO: List the workspaces
    # TODO: Mark current workspace with asterisk


@workspace_app.command()
def delete(name: str) -> None:
    """Delete a workspace."""

    # TODO: Delete the workspace
    # TODO: Delete from current if it's there too


@workspace_app.command()
def save(
    name: str = Argument(..., help="The name of the new workspace"),
    *,
    overwrite: bool = Option(
        False,
        "--overwrite",
        "-o",
        help="Whether to overwrite an existing workspace with the same name",
    )
) -> None:
    """Save a workspace."""
    if not get_links_list("*"):
        print("No links are in the history, nothing to save")
        raise Exit(1)

    # TODO: Check for duplicate workspaces
    # TODO: Save workspace


@workspace_app.command()
def load(name: str) -> None:
    """Load a workspace."""

    # TODO: Load workspace


@workspace_app.command()
def export(
    name: str = Argument(..., help="Name of the workspace to export"),
    filepath: str = Argument(
        ..., help="The folder where the workspace will be exported to"
    ),
) -> None:
    """Export a workspace."""

    # TODO: Export the workspace


@workspace_app.command(name="import")
def workspace_import(
    filepath: str,
    *,
    load: bool = Option(
        False, "--load", "-l", help="Immediately load the workspace after importing"
    )
) -> None:
    """Import a workspace."""

    # TODO: Import the workspace
