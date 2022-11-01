# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

"""
Backend operations for circlink.

Author(s): Alec Delaney (Tekktrik)
"""

import datetime
import os
import signal
from typing import Iterable, List

import circup
import psutil
import tabulate
from typer import Exit

import circlink
import circlink.ledger
import circlink.link


# pylint: disable=too-many-locals,too-many-branches
def start_backend(
    read_path: str,
    write_path: str,
    base_dir: str,
    *,
    path: bool = False,
    name: str = "",
    recursive: bool = False,
    wipe_dest: bool = False,
    skip_presave: bool = False,
) -> None:
    """Start a link (backend)."""
    # Only allow recursive setting with glob patterns
    if "*" not in read_path and recursive:
        print("--recursive can only be used with glob patterns!")
        raise Exit(1)

    # Attempt to find the CircuitPython board unless explicitly set otherwise
    if not path:
        device_path = circup.find_device()
        if not device_path:
            print("Cound not auto-detect board path!")
            raise Exit(1)
        write_path = os.path.join(device_path, write_path)

    # Warn if the board (or write path in general) is not write accessible
    if not os.access(write_path, os.W_OK):
        print("Cannot write to the device or specified path")
        print("If using CircuitPython board, please ensure it is mounted")
        raise Exit(1)

    # Set the base directory is current directory if not provided
    base_dir = os.getcwd() if not base_dir else base_dir

    # Create the link object
    link = circlink.link.CircuitPythonLink(
        read_path,
        write_path,
        base_dir,
        name=name,
        recursive=recursive,
        wipe_dest=wipe_dest,
        skip_presave=skip_presave,
    )

    # Get the link ID and save the link
    link_id = link.link_id
    link.save_link()

    # Detect whether bad read path/pattern provided
    try:
        link.read_path.resolve().relative_to(base_dir)
    except ValueError as err:
        print(
            "Error occurred, please ensure the read file/pattern "
            "is relative to the current directory"
        )
        raise Exit(1) from err

    # Fork the process to begin start the link
    pid = os.fork()  # pylint: disable=no-member

    if pid:  # Current process, pid is that of spawned process

        # Save the link with the process ID
        link.process_id = pid
        link.save_link()

        # Attempt to wait for spawned process to be confirmed
        start_time = datetime.datetime.now()
        error_time = start_time + datetime.timedelta(seconds=5)
        while not link or not link.confirmed:
            link = circlink.link.CircuitPythonLink.load_link_by_num(link_id)
            if datetime.datetime.now() >= error_time:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                raise OSError("Could not start link process!")

        print(f"Started link #{link.link_id}")

    else:  # Spawned process, PID is 0

        # Wait for the process ID to be avaiable
        while not link or not link.process_id:
            link = circlink.link.CircuitPythonLink.load_link_by_num(link_id)

        # Mark the link is confirmed and save it
        link.confirmed = True
        link.save_link()

        # Begin monitoring files, exiting successfully when completed or error if needed
        try:
            link.begin_monitoring()
        except FileNotFoundError:
            for file in link.get_files_monitored():
                ledger_entry = circlink.ledger.LedgerEntry(
                    str(file.resolve()), link.link_id, link.process_id
                )
                circlink.ledger.remove_from_ledger(ledger_entry)
            Exit(1)
        raise Exit()


def stop_backend(link_id: int, *, hard_fault: bool = True) -> bool:
    """Stop a link (backend)."""
    # Attempt to get the link by ID
    try:
        link = circlink.link.CircuitPythonLink.load_link_by_num(link_id)
    except FileNotFoundError as err:
        print(f"Link #{link_id} does not exist!")
        raise Exit(1) from err

    # Announce if the link is already stopped
    if link.stopped:
        print(f"Link #{link.link_id} is already stopped")
        if hard_fault:
            raise Exit()
        return False

    # Detect whether the link exists and is circlink
    try:
        circlink_process = psutil.Process(link.process_id)
        maybe_process = circlink_process.name() == "circlink"
    except psutil.NoSuchProcess:
        maybe_process = False

    if not maybe_process:
        print(
            f"Problem encountered stopping link #{link_id}!\n"
            "Asscoiated proess either does not exist, was already "
            "stopped, or isn't circlink.\n"
            "Consider using the clear command with the --force flag to "
            "clear it from the history."
        )
        raise Exit(1)

    # Mark the link for termination
    link.end_flag = True
    link.save_link()

    # Wait for confirmation that the link has stopped
    start_time = datetime.datetime.now()
    error_time = start_time + datetime.timedelta(seconds=5)
    while not link or not link.stopped:
        link = circlink.link.CircuitPythonLink.load_link_by_num(link_id)
        if datetime.datetime.now() >= error_time:
            print(f"Link #{link.link_id} could not be stopped!")
            if hard_fault:
                raise Exit(1)
            return False

    # Announce the link has stopped
    print(f"Stopped link #{link_id}")
    return True


def clear_backend(
    link_id: int, *, force: bool = False, hard_fault: bool = False
) -> bool:
    """Clear a link (backend)."""
    # Get the link object by link ID
    try:
        link = circlink.link.CircuitPythonLink.load_link_by_num(link_id)
    except FileNotFoundError as err:
        print(f"Link #{link_id} does not exist!")
        raise Exit(1) from err

    # If the link is not marked as stop, announce "--force" is needed
    if not link.stopped and not force:
        print("Can only clear links marked as inactive.")
        print(f"To force clear link #{link.link_id}, use the --force option.")
        if hard_fault:
            raise Exit(1)
        return False

    # Remove the file associated with the link
    os.remove(link.link_id_to_filename(link_id))
    print(f"Removed link #{link_id} from history")

    # Remove file from ledger, just in case
    for entry in circlink.ledger.iter_ledger_entries():
        if entry.link_id == link_id:
            circlink.ledger.remove_from_ledger(entry, expect_entry=True, use_lock=False)

    set_cws_name("")

    return True


def retrieve_links_info(
    pattern: str = "*",
    *,
    abs_paths: bool = False,
    folder: str = circlink.LINKS_DIRECTORY,
    exclude: Iterable[str] = ("Base Directory",),
) -> List[tuple]:
    """Retrieve information about a collection of links."""
    # Discard the link base directory for printing purposes
    show_list = list(circlink.link.get_links_header())
    link_infos = list(
        circlink.link.get_links_list(pattern, abs_paths=abs_paths, folder=folder)
    )

    # Remove unwanted columns
    new_link_infos = []
    for entry in link_infos:
        new_entry = ()
        for exculde_index, exclude_col in enumerate(show_list):
            if exclude_col not in exclude:
                new_entry: tuple = new_entry + (entry[exculde_index],)
        new_link_infos.append(new_entry)

    return new_link_infos


def view_backend(
    pattern: str = "*",
    *,
    abs_paths: bool = False,
    folder: str = circlink.LINKS_DIRECTORY,
    exclude: Iterable[str] = ("Base Directory",),
) -> None:
    """View a collection of links (backend)."""
    show_list = list(circlink.link.get_links_header())
    for exclude_header in exclude:
        show_list.remove(exclude_header)
    show_list = tuple(show_list)
    if (
        not circlink.get_settings()["display"]["info"]["process-id"]
        and "Process ID" not in exclude
    ):
        exclude = exclude + ("Process ID",)
        show_list = list(show_list)
        show_list.remove("Process ID")
        show_list = tuple(show_list)

    # Discard the link base directory for printing purposes
    link_infos = retrieve_links_info(
        pattern, abs_paths=abs_paths, folder=folder, exclude=exclude
    )

    # Print the table with the format based on config settings
    if link_infos:
        print(
            tabulate.tabulate(
                link_infos,
                headers=show_list,
                tablefmt=circlink.get_settings()["display"]["table"]["format"],
            )
        )

    return link_infos


def get_cws_name() -> str:
    """Get the current workspace name."""
    with open(circlink.CURRENT_WORKSPACE_FILE, encoding="utf-8") as cwsfile:
        name = cwsfile.read()
    return None if not name else name


def set_cws_name(name: str) -> None:
    """Set the current workspace name."""
    with open(circlink.CURRENT_WORKSPACE_FILE, mode="w", encoding="utf-8") as cwsfile:
        cwsfile.write(name)
