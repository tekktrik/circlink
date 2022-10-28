# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

"""
The sub-script for handling the workspace options for ``circlink``.

Author(s): Alec Delaney (Tekktrik)
"""

import os
import pathlib
import shutil
import zipfile
from typing import Dict, Optional

from typer import Argument, Exit, Option, Typer

from circlink import (
    CURRENT_WORKSPACE_FILE,
    LINKS_DIRECTORY,
    WORKSPACE_LIST_DIRECTORY,
)
from circlink.link import CircuitPythonLink, get_links_list

workspace_app = Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Save and load workspace settings.",
)


def get_cws_name() -> str:
    """Get the current workspace name."""
    with open(CURRENT_WORKSPACE_FILE, encoding="utf-8") as cwsfile:
        name = cwsfile.read()
    return None if not name else name


def set_cws_name(name: str) -> None:
    """Set the current workspace name."""
    with open(CURRENT_WORKSPACE_FILE, mode="w", encoding="utf-8") as cwsfile:
        cwsfile.write(name)


def get_workspaces() -> Dict[str, pathlib.Path]:
    """Iterate through the workspace names and folder filepaths."""
    workspaces = [
        path
        for path in pathlib.Path(WORKSPACE_LIST_DIRECTORY).glob("*")
        if path.is_dir()
    ]
    return {path.name: path for path in workspaces}


def _remove_workspace(name: str) -> None:
    """Remove a saved workspace (if it exists)."""
    for ws_name, ws_path in get_workspaces().items():
        if name == ws_name:
            shutil.rmtree(str(ws_path.resolve()))

    set_cws_name("")


def _ensure_new_workspace(name: str, raise_error: bool = True) -> bool:
    """Save a workspace (backend)."""
    if name in get_workspaces():
        if raise_error:
            print(f"Cannot use name {name} - workspace already saved with this name.")
            raise Exit(1)
        return False
    return True


def _get_ws_path(name: str) -> str:
    """Get the for a workspace directory name."""
    return os.path.join(WORKSPACE_LIST_DIRECTORY, name)


@workspace_app.command()
def current() -> None:
    """Get the current workspace name."""
    name = get_cws_name()
    if not name:
        print("Current workspace is not named")
        raise Exit()
    print(name)


@workspace_app.command(name="list")
def workspace_list() -> None:
    """List all existing workspaces."""
    workspaces = get_workspaces()
    if workspaces:
        for workspace in get_workspaces():
            print_text = "* " + workspace if workspace == get_cws_name() else workspace
            print(print_text)
    else:
        print("No workspaces saved")


@workspace_app.command()
def delete(name: str = Argument(..., help="Name of the workspace to delete")) -> None:
    """Delete a workspace."""
    if name not in get_workspaces():
        print(f"Workspace '{name}' does not exist")
        raise Exit(1)

    _remove_workspace(name)
    print(f"Workspace '{name}' deleted")


@workspace_app.command()
def rename(
    old_name: str = Argument(..., help="Name of the workspace to rename"),
    new_name: str = Argument(..., help="New name for the workspace"),
) -> None:
    """Rename a workspace."""
    _ensure_new_workspace(new_name)

    old_path = _get_ws_path(old_name)

    parent = os.path.dirname(old_path)
    new_path = os.path.join(parent, new_name)

    os.rename(old_path, new_path)

    if get_cws_name() == old_name:
        set_cws_name(new_name)

    print(f"Workspace '{old_name}' renamed to '{new_name}'")


@workspace_app.command()
def save(
    name: str = Argument(..., help="The name of the new workspace"),
    *,
    overwrite: bool = Option(
        False,
        "--overwrite",
        "-o",
        help="Whether to overwrite an existing workspace with the same name",
    ),
) -> None:
    """Save the current link state as a workspace."""
    if not get_links_list("*"):
        print("No links are in the history, nothing to save")
        raise Exit(1)

    _ = not overwrite and _ensure_new_workspace(name)

    _remove_workspace(name)

    new_ws_folder = _get_ws_path(name)
    os.mkdir(new_ws_folder)
    links_path = pathlib.Path(LINKS_DIRECTORY)

    for link_index, link_path in enumerate(links_path.glob("*")):
        link = CircuitPythonLink.load_link_by_filepath(str(link_path))
        link._link_id = link_index + 1  # pylint: disable=protected-access
        link.process_id = 0
        link.end_flag = True
        link.confirmed = True
        link._stopped = True  # pylint: disable=protected-access
        link.save_link(save_directory=new_ws_folder)

    set_cws_name(name)

    print(f"New workspace saved as '{name}'")


@workspace_app.command()
def load(name: str = Argument(..., help="Name of the workspace to load")) -> None:
    """Load a workspace."""
    links_folder = os.path.join(LINKS_DIRECTORY)
    links_path = pathlib.Path(links_folder)
    ws_path = pathlib.Path(WORKSPACE_LIST_DIRECTORY) / name

    if list(links_path.glob("*")):
        print("Cannot load workspace with files in the history.")
        print("Please clear the history with the clear command.")
        raise Exit(1)

    if _ensure_new_workspace(name, raise_error=False):
        print("This workspace does not exist!")
        raise Exit(1)

    for link_path in ws_path.glob("*"):
        link = CircuitPythonLink.load_link_by_filepath(str(link_path))
        link.save_link()

    set_cws_name(name)

    print(f"Loaded workspace '{name}'")


@workspace_app.command()
def export(
    name: str = Argument(..., help="Name of the workspace to export"),
    path: str = Argument(
        ..., help="The folder where the workspace will be exported to"
    ),
) -> None:
    """Export a workspace."""
    export_folder = _get_ws_path(name)
    export_paths = [path.resolve() for path in pathlib.Path(export_folder).glob("*")]
    exported_path = os.path.join(path, name + ".zip")

    with zipfile.ZipFile(
        exported_path, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as zip_file:
        for export_path in export_paths:
            zip_file.write(str(export_path), arcname=export_path.name)


@workspace_app.command(name="import")
def workspace_import(
    filepath: str = Argument(..., help="Filepath of the packaged workspace"),
    name: Optional[str] = Option(
        None, "--name", "-n", help="A name to give to the imported workspace"
    ),
) -> None:
    """Import a workspace."""
    package_name = os.path.basename(filepath)[:-4] if not name else name
    package_ext = os.path.splitext(filepath)[1]

    if package_ext.lower() != ".zip":
        print("Imported workspaces must be ZIP files")
        raise Exit(1)

    _ensure_new_workspace(package_name)
    new_ws_path = _get_ws_path(package_name)
    os.mkdir(new_ws_path)

    with zipfile.ZipFile(filepath) as zip_file:
        zip_file.extractall(new_ws_path)
