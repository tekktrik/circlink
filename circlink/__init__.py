# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

"""
The main script handling CLI interactions for ``circlink``

Author(s): Alec Delaney (Tekktrik)
"""

import os
import sys
import time
import signal
import pathlib
import shutil
import json
from datetime import datetime, timedelta
from typing import List, Tuple
from typing_extensions import TypeAlias
import psutil
import yaml
from typer import Typer, Option, Argument, Exit
from circup import find_device
from tabulate import tabulate
from circlink.link import (
    LINKS_DIRECTORY,
    APP_DIRECTORY,
    CircuitPythonLink,
    ensure_links_folder,
    ensure_ledger_file,
    iter_ledger_entries,
    remove_from_ledger,
)

__version__ = "0.0.0+auto.0"

# Type aliases
_TableRowEntry: TypeAlias = Tuple[
    int, str, bool, pathlib.Path, pathlib.Path, bool, int, str
]

# Get the location of the settigns file
SETTINGS_FILE = os.path.join(APP_DIRECTORY, "settings.yaml")

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
config_app = Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Change config settings for circlink",
)
app.add_typer(config_app, name="config")


def _ensure_app_folder_setup() -> None:
    """Ensures that the configuration folder exists"""

    if not os.path.exists(APP_DIRECTORY):
        os.mkdir(APP_DIRECTORY)

    ensure_links_folder()
    ensure_ledger_file()
    ensure_settings_file()


def ensure_settings_file() -> None:
    """Ensure the settings file is set up"""

    settings_path = pathlib.Path(SETTINGS_FILE)
    if not settings_path.exists():
        _reset_config_file()


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
    """Start a CircuitPython link"""

    _start(
        read_path,
        write_path,
        os.getcwd(),
        path=path,
        name=name,
        recursive=recursive,
        wipe_dest=wipe_dest,
        skip_presave=skip_presave,
    )


def _start(
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
    """Backend of starting a link"""

    # Only allow recursive setting with glob patterns
    if "*" not in read_path and recursive:
        print("--recursive can only be used with glob patterns!")
        raise Exit(1)

    # Attempt to find the CircuitPython board unless explicitly set otherwise
    if not path:
        device_path = find_device()
        if not device_path:
            print("Cound not auto-detect board path!")
            raise Exit(1)
        write_path = os.path.join(device_path, write_path)

    # Warn if the board (or write path in general) is not write accessible
    if not os.access(write_path, os.W_OK):
        print("Cannot write to the device or specified path")
        print("If using CircuitPython board, please ensure it is nounted")
        raise Exit(1)

    # Set the base directory is current directory if not provided
    base_dir = os.getcwd() if not base_dir else base_dir

    # Create the link object
    link = CircuitPythonLink(
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
        link.read_path.relative_to(base_dir)
    except ValueError as err:
        print(
            "Error occurred, please ensure the read file/pattern "
            "is relative to the current directory"
        )
        raise Exit(1) from err

    # Fork the process to begin start the link
    pid = os.fork()

    if pid:  # Current process, pid is that of spawned process

        # Save the link with the process ID
        link.process_id = pid
        link.save_link()

        # Attempt to wait for spawned process to be confirmed
        start_time = datetime.now()
        error_time = start_time + timedelta(seconds=5)
        while not link.confirmed:
            link = CircuitPythonLink.load_link_by_num(link_id)
            time.sleep(0.5)  # Slight delay
            if datetime.now() >= error_time:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                raise OSError("Could not start link process!")

        print(f"Started link #{link.link_id}")

    else:  # Spawned process, PID is 0

        # Wait for the process ID to be avaiable
        while not link.process_id:
            link = CircuitPythonLink.load_link_by_num(link_id)
            time.sleep(0.3)

        # Mark the link is confirmed and save it
        link.confirmed = True
        link.save_link()

        # Begin monitoring files, exiting successfully when completed or error if needed
        try:
            link.begin_monitoring()
        except FileNotFoundError:
            Exit(1)
        raise Exit()


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
    """Stop a CircuitPython link"""

    # If stopping all links, stop links using the "last" option until done
    if link_id == "all":
        link_entries = _get_links_list("*")
        for link_entry in link_entries:
            _stop_link(link_entry[0], hard_fault=False)
            if clear_flag:
                _clear_link(link_entry[0], hard_fault=False)
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
    _stop_link(link_id)
    if clear_flag:
        _clear_link(link_id)


def _stop_link(link_id: int, *, hard_fault: bool = True) -> bool:
    """The backend of stopping a link"""

    # Attempt to get the link by ID
    try:
        link = CircuitPythonLink.load_link_by_num(link_id)
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
    start_time = datetime.now()
    error_time = start_time + timedelta(seconds=5)
    while not link.stopped:
        link = CircuitPythonLink.load_link_by_num(link_id)
        time.sleep(0.1)  # Slight delay
        if datetime.now() >= error_time:
            print(f"Link #{link.link_id} could not be stopped!")
            if hard_fault:
                raise Exit(1)
            return False

    # Announce the link has stopped
    print(f"Stopped link #{link_id}")
    return True


@app.command()
def clear(
    link_id: str = Argument(..., help="Link ID / 'last' / 'all'"),
    *,
    force: bool = Option(
        False, "--force", "-f", help="Ignore warning and force clear from history"
    ),
) -> None:
    """Clear the link from the history"""

    # If clearing all links, repetitively clear the last link
    if link_id == "all":
        link_entries = _get_links_list("*")
        for link_entry in link_entries:
            _clear_link(link_entry[0], force=force, hard_fault=False)
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
    _clear_link(link_id, force=force)


def _clear_link(link_id: int, *, force: bool = False, hard_fault: bool = False) -> bool:
    """The backend of clearing a link"""

    # Get the link object by link ID
    try:
        link = CircuitPythonLink.load_link_by_num(link_id)
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
    for entry in iter_ledger_entries():
        if entry.link_id == link_id:
            remove_from_ledger(entry, expect_entry=True, use_lock=False)

    return True


def _add_links_header() -> Tuple[str, ...]:
    """Get the header row for the links list"""

    return (
        "ID",
        "Name",
        "Running?",
        "Read Path",
        "Write Path",
        "Recursive?",
        "Process ID",
        "Base Directory",
    )


def _get_links_list(
    pattern: str, *, abs_paths: bool = False, name: str = ""
) -> List[_TableRowEntry]:
    """Get the information about links"""

    # Get the paths of all the exiting links
    link_paths = pathlib.Path(LINKS_DIRECTORY).glob(pattern)

    # Populate the list of links
    link_infos = []
    for link_path in link_paths:

        # Load link and start getting info
        link = CircuitPythonLink.load_link_by_filepath(str(link_path))
        link_id = link.link_id
        link_name = link.name
        link_running = not link.stopped

        # Attempt to use relative paths if possible
        if not abs_paths:
            try:
                link_read = link.read_path.resolve().relative_to(os.getcwd())
            except ValueError:
                abs_paths = True
        if abs_paths:
            link_read = link.read_path.resolve()

        # Get remaining link info
        link_write = link.write_path.resolve()
        link_recursive = link.recursive
        link_proc = link.process_id
        link_base = link.base_dir

        # If not specific named link is requested, append it
        if not name or link_name == name:
            link_infos.append(
                (
                    link_id,
                    link_name,
                    link_running,
                    link_read,
                    link_write,
                    link_recursive,
                    link_proc,
                    link_base,
                )
            )

    # Return a sorted list of links
    return sorted(link_infos, key=lambda x: x[0])


@app.command()
def view(
    link_id: str = Argument("all", help="Link ID / 'last' / 'all' (default)"),
    *,
    abs_paths: bool = Option(
        False, "--abs-path", "-a", help="Show the read path as absolute"
    ),
) -> None:
    """List links in the history"""

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
    link_infos = [x[:-1] for x in _get_links_list(pattern, abs_paths=abs_paths)]

    # Handle if no links available
    if not link_infos:
        if link_id == "all" or last_requested_flag:
            print("No links in the history to view")
            raise Exit()
        print("This link ID is not in the history")
        raise Exit(1)

    # Prepare process ID depending on config settings
    show_list = _add_links_header()
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
    """Restart a link"""

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
    link_list = _get_links_list(pattern)
    if not link_list:
        print("There are no links in the history to restart")
        raise Exit(1)

    # Attempt to restart and clear the link if it's not active
    for link in link_list:
        if link[2]:
            print(f"Link #{link[0]} is active, not restarting this link.")
        else:
            _start(
                str(link[3]),
                str(link[4]),
                link[-1],
                name=link[1],
                recursive=link[5],
                path=True,
            )
            clear(link[0])


@app.command()
def detect() -> None:
    """Attempt to detect a CircuitPython board"""

    device = find_device()
    if device:
        print("CircuitPython device detected:", device)
    else:
        print("No CircuitPython device detected")


def about_cb() -> None:
    """Display information about circlink"""

    print("Originally built with love by Tekktrik")
    print("Happy hackin'!")
    raise Exit()


def version_cb() -> None:
    """Display the current version of circlink"""

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
    """Display the current version of circlink"""

    _ensure_app_folder_setup()

    if version:
        version_cb()
    if about:
        about_cb()
    if reset:
        reset_cb()


def reset_cb() -> None:
    """Reset the app directory, useful if you upgrade circlink and there
    are breaking changes
    """

    shutil.rmtree(APP_DIRECTORY)
    print("Removed circlink app directory, settngs and history deleted!")
    print("These will be created on next use of circlink.")
    print("Please check the integrity of any files handled by circlink.")
    raise Exit()


@app.command()
def ledger() -> None:
    """View the ledger of files controlled by links"""

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


def _reset_config_file() -> None:
    """Reset the config file"""
    settings_file = os.path.join(__file__, "..", "templates", "settings.yaml")
    shutil.copy(os.path.abspath(settings_file), SETTINGS_FILE)


@config_app.callback(invoke_without_command=True)
def config_callback(
    filepath: bool = Option(
        False, "--filepath", "-f", help="Print the settings file location"
    ),
    reset: bool = Option(
        False, "--reset", help="Reset the configuration settings to their defaults"
    ),
) -> None:
    """Callback for the config subcommand"""
    if filepath:
        print(f"Settings file: {os.path.abspath(SETTINGS_FILE)}")
        raise Exit()
    if reset:
        _reset_config_file()


def get_settings():
    """Get the contents of the settings file"""

    with open(SETTINGS_FILE, mode="r", encoding="utf-8") as yamlfile:
        return yaml.safe_load(yamlfile)


@config_app.command(name="view")
def config_view(
    config_path: str = Argument("all", help="The setting to view, using dot notation")
) -> None:
    """View a config setting for circlink"""

    # Get the settings, show all settings if no specific on is specified
    setting = get_settings()
    if config_path == "all":
        print(json.dumps(setting, indent=4))
        raise Exit()

    # Get the specified settings
    config_args = config_path.split(".")
    try:
        for extra_arg in config_args[:-1]:
            setting = setting[extra_arg]
        value = setting[config_args[-1]]
    except KeyError as err:
        print(f"Setting {config_path} does not exist")
        raise Exit(1) from err

    # Show the specified setting
    print(f"{config_path}: {json.dumps(value, indent=4)}")


@config_app.command(name="edit")
def config_edit(
    config_path: str = Argument("all", help="The setting to view, using dot notation"),
    value: str = Argument(..., help="The value to set for the setting"),
) -> None:
    """Edit a config setting for circlink"""

    # Get the settings, use another reference to parse
    orig_setting = get_settings()
    setting = orig_setting
    config_args = config_path.split(".")

    # Handle bool conversions
    if value.lower() == "true":
        value = True
    elif value.lower() == "false":
        value = False

    # Attempt to parse for the specified config setting and set it
    try:
        for extra_arg in config_args[:-1]:
            setting = setting[extra_arg]
        prev_value = setting[config_args[-1]]
        prev_value_type = type(prev_value)
        if prev_value_type == dict:
            raise ValueError
        if prev_value_type == bool and value not in (True, False):
            raise TypeError
        setting[config_args[-1]] = prev_value_type(value)
    except KeyError as err:
        print(f"Setting {config_path} does not exist")
        raise Exit(1) from err
    except TypeError as err:
        print(
            f"Cannot use that value for this setting, must be of type {prev_value_type}"
        )
        raise Exit(1) from err
    except ValueError as err:
        print("Cannot change this setting, please change the sub-settings within it")
        raise Exit(1) from err

    # Write the settings back to the file
    with open(SETTINGS_FILE, mode="w", encoding="utf-8") as yamlfile:
        yaml.safe_dump(orig_setting, yamlfile)
