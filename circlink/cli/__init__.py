# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

"""
The main script handling CLI interactions for ``circlink``.

Author(s): Alec Delaney (Tekktrik)
"""

import os
import shutil
import sys

from circup import find_device
from tabulate import tabulate
from typer import Argument, Exit, Option, Typer

from circlink import (
    APP_DIRECTORY,
    __version__,
    ensure_app_folder_setup,
    get_settings,
)
from circlink.backend import clear_backend, start_backend, stop_backend
from circlink.cli import config, workspace
from circlink.ledger import iter_ledger_entries
from circlink.link import CircuitPythonLink, get_links_header, get_links_list

# Prevent running on non-POSIX systems that don't have os.fork()
if os.name != "posix":
    print("circlink is currently only available for Linux and macOS")
    sys.exit(1)

# Create the Typer apps
app = Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Autosave local files to your CircuitPython board",
)
app.add_typer(config.config_app, name="config")
app.add_typer(workspace.workspace_app, name="workspace")


@app.command()
def start(
    read_path: str = Argument(..., help="The read path/pattern of file(s) to save"),
    write_path: str = Argument(
        ...,
        help="The write path of the directory to write files, relative to the CircuitPython board",
    ),
    *,
    path: bool = Option(
        False,
        "--path",
        "-p",
        help="Designate the write path as absolute or relative to the current directory",
    ),
    name: str = Option("", "--name", "-n", help="A name for the new link"),
    recursive: bool = Option(
        False, "--recursive", "-r", help="Whether the link glob pattern is recursive"
    ),
    wipe_dest: bool = Option(
        False,
        "--wipe-dest",
        "-w",
        help="Wipe the write destination recursively before starting the link",
    ),
    skip_presave: bool = Option(
        False,
        "--skip-presave",
        "-s",
        help="Skip the inital save and write performed when opening a link",
    ),
) -> None:
    """Start a CircuitPython link."""
    start_backend(
        read_path,
        write_path,
        os.getcwd(),
        path=path,
        name=name,
        recursive=recursive,
        wipe_dest=wipe_dest,
        skip_presave=skip_presave,
    )
    workspace.set_cws_name("")


@app.command()
def stop(
    link_id: str = Argument(..., help="Link ID / 'last' / 'all'"),
    clear_flag: bool = Option(
        False,
        "--clear",
        "-c",
        help="Clear the history of the specified link(s) as well",
    ),
) -> bool:
    """Stop a CircuitPython link."""
    # If stopping all links, stop links using the "last" option until done
    if link_id == "all":
        link_entries = get_links_list("*")
        for link_entry in link_entries:
            stop_backend(link_entry[0], hard_fault=False)
            if clear_flag:
                clear_backend(link_entry[0], hard_fault=False)
        raise Exit()

    # If stopping the last link, calculate its link ID
    if link_id == "last":
        link_id = str(CircuitPythonLink.get_next_link_id() - 1)
        if link_id == "0":
            print("There are no links in the history")
            raise Exit(1)

    # Detect if the link ID is not valid
    try:
        link_id = int(link_id)
    except ValueError as err:
        print('Link ID must be the ID, "last", or "all"')
        raise Exit(1) from err

    # Stop the link, clear as well if requested
    stop_backend(link_id)
    if clear_flag:
        clear_backend(link_id)


@app.command()
def clear(
    link_id: str = Argument(..., help="Link ID / 'last' / 'all'"),
    *,
    force: bool = Option(
        False, "--force", "-f", help="Ignore warning and force clear from history"
    ),
) -> None:
    """Clear the link from the history."""
    # If clearing all links, repetitively clear the last link
    if link_id == "all":
        link_entries = get_links_list("*")
        for link_entry in link_entries:
            clear_backend(link_entry[0], force=force, hard_fault=False)
        raise Exit()

    # If clearing the last link link, calculate its link ID
    if link_id == "last":
        link_id = str(CircuitPythonLink.get_next_link_id() - 1)
        if link_id == "0":
            return

    # Detect if the link ID is not valid
    try:
        link_id = int(link_id)
    except ValueError as err:
        print('Link ID must be the ID, "last", or "all"')
        raise Exit(1) from err

    # Clear the link
    clear_backend(link_id, force=force)


@app.command()
def view(
    link_id: str = Argument("all", help="Link ID / 'last' / 'all' (default)"),
    *,
    abs_paths: bool = Option(
        False, "--abs-path", "-a", help="Show the read path as absolute"
    ),
) -> None:
    """List links in the history."""
    # For recursion purposes, note whether link ID is "last"
    last_requested_flag = False

    # Handle cases of link ID being "all" or "last", or just parse link ID
    if link_id == "all":
        pattern = "*"
    elif link_id == "last":
        last_requested_flag = True
        link_id = str(CircuitPythonLink.get_next_link_id() - 1)
        pattern = "link" + link_id + ".json"
        if link_id == "0":
            pattern = "*"
    else:
        try:
            int(link_id)
            pattern = "link" + link_id + ".json"
        except ValueError:
            print('Please use a valid link ID, "last", or "all" (default)')

    # Discard the link base directory for printing purposes
    link_infos = [x[:-1] for x in get_links_list(pattern, abs_paths=abs_paths)]

    # Handle if no links available
    if not link_infos:
        if link_id == "all" or last_requested_flag:
            print("No links in the history to view")
            raise Exit()
        print("This link ID is not in the history")
        raise Exit(1)

    # Prepare process ID depending on config settings
    show_list = get_links_header()
    if not get_settings()["display"]["info"]["process-id"]:
        show_list = list(show_list)
        show_list.remove("Process ID")
        link_infos = [entry[:-1] for entry in link_infos]

    # Print the table with the format based on config settings
    print(
        tabulate(
            link_infos,
            headers=show_list,
            tablefmt=get_settings()["display"]["table"]["format"],
        )
    )


@app.command()
def restart(link_id: str = Argument(..., help="Link ID / 'last' / 'all'")) -> None:
    """Restart a link."""
    # Handle cases of "all" or "last", or parse link ID
    if link_id == "all":
        pattern = "*"
    elif link_id == "last":
        link_id = str(CircuitPythonLink.get_next_link_id() - 1)
        pattern = "link" + link_id + ".json"
        if link_id == "0":
            pattern = "*"
    else:
        try:
            int(link_id)
            pattern = "link" + link_id + ".json"
        except ValueError as err:
            print('Please use a valid link ID, "last", or "all"')
            raise Exit(1) from err

    # Get the list of links in history if possible
    link_list = get_links_list(pattern)
    if not link_list:
        print("There are no links in the history to restart")
        raise Exit(1)

    # Attempt to restart and clear the link if it's not active
    for link in link_list:
        if link[2]:
            print(f"Link #{link[0]} is active, not restarting this link.")
        else:
            start_backend(
                str(link[3]),
                str(link[4]),
                link[-1],
                name=link[1],
                recursive=link[5],
                path=True,
            )
            clear_backend(link[0])


@app.command()
def detect() -> None:
    """Attempt to detect a CircuitPython board."""
    device = find_device()
    if device:
        print("CircuitPython device detected:", device)
    else:
        print("No CircuitPython device detected")


def about_cb() -> None:
    """Display information about circlink."""
    print("Originally built with love by Tekktrik")
    print("Happy hackin'!")
    raise Exit()


def version_cb() -> None:
    """Display the current version of circlink."""
    print(__version__)
    raise Exit()


@app.callback(invoke_without_command=True)
def callback(
    version: bool = Option(
        False, "--version", "-v", help="Display the version of circlink"
    ),
    about: bool = Option(False, "--about", "-a", help="A bit about circlink"),
    reset: bool = Option(
        False, "--reset", help="Reset the circlink configuration settings"
    ),
) -> None:
    """Display the current version of circlink."""
    ensure_app_folder_setup()

    if version:
        version_cb()
    if about:
        about_cb()
    if reset:
        reset_cb()


def reset_cb() -> None:
    """
    Reset the app directory.

    Useful if you upgrade circlink and there are breaking changes.
    """
    shutil.rmtree(APP_DIRECTORY)
    print("Removed circlink app directory, settngs and history deleted!")
    print("These will be created on next use of circlink.")
    print("Please check the integrity of any files handled by circlink.")
    raise Exit()


@app.command()
def ledger() -> None:
    """View the ledger of files controlled by links."""
    # Get the list of ledger entries if possible
    ledger_entries = list(iter_ledger_entries())
    if not ledger_entries:
        print("No files being tracked by circlink")
        raise Exit()

    # Display the process ID of links depending on settings
    table_headers = ("Write Path", "Link")
    if get_settings()["display"]["info"]["process-id"]:
        table_headers = table_headers + ("Process ID",)
    else:
        ledger_entries = [entry[:-1] for entry in ledger_entries]

    # Print the table with the format specified in config settings
    print(
        tabulate(
            ledger_entries,
            headers=table_headers,
            tablefmt=get_settings()["display"]["table"]["format"],
        )
    )
