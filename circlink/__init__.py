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
from datetime import datetime, timedelta
from typing import List, Tuple, Literal
from typing_extensions import TypeAlias
from typer import Typer, Option
from circup import find_device
from tabulate import tabulate
from circlink.link import LINKS_DIRECTORY, CircuitPythonLink

_TableRowEntry: TypeAlias = Tuple[
    int, str, bool, pathlib.Path, pathlib.Path, bool, int, str
]

__version__ = "0.0.0+auto.0"

# Prevent running on non-POSIX systems that don't have os.fork()
if os.name != "posix":
    print("circlink is currently only available for Linux and macOS")
    sys.exit(1)

app = Typer(add_completion=False)


def _ensure_links_folder() -> None:
    """Ensures that the ``links`` folder exists"""

    if not os.path.exists(LINKS_DIRECTORY):
        os.mkdir(LINKS_DIRECTORY)


@app.command()
def start(
    read_path: str,
    write_path: str,
    *,
    path: bool = False,
    name: str = "",
    recursive: bool = False,
    wipe_dest: bool = False,
    skip_presave: bool = False,
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
    """Backend of starting a CiruitPython link"""

    if "*" not in read_path and recursive:
        print("--recursive can only be used with glob patterns!")
        sys.exit(1)

    if not path:
        device_path = find_device()
        if not device_path:
            print("Cound not auto-detect board path!")
            sys.exit(1)
        write_path = os.path.join(device_path, write_path)

    base_dir = os.getcwd() if not base_dir else base_dir

    link = CircuitPythonLink(
        read_path,
        write_path,
        base_dir,
        name=name,
        recursive=recursive,
        wipe_dest=wipe_dest,
        skip_presave=skip_presave,
    )

    link_id = link.link_id
    link.save_link()

    pid = os.fork()

    if pid:  # PID is a real process number

        link.process_id = pid
        link.save_link()

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

    else:  # PID is 0
        while not link.process_id:
            link = CircuitPythonLink.load_link_by_num(link_id)
            time.sleep(0.3)
        link.confirmed = True
        link.save_link()
        link.begin_monitoring()
        sys.exit(0)


def _stop_link(link_id: int, *, hard_fault: bool = True) -> Literal[True]:

    try:
        link = CircuitPythonLink.load_link_by_num(link_id)
    except FileNotFoundError:
        print(f"Link #{link_id} does not exist!")
        sys.exit(1)

    if link.stopped:
        print(f"Link #{link.link_id} is already stopped")
        if hard_fault:
            sys.exit(0)
        else:
            return False

    link.end_flag = True
    link.save_link()

    start_time = datetime.now()
    error_time = start_time + timedelta(seconds=5)

    while not link.stopped:
        link = CircuitPythonLink.load_link_by_num(link_id)
        time.sleep(0.1)  # Slight delay
        if datetime.now() >= error_time:
            print(f"Link #{link.link_id} could not be stopped!")
            if hard_fault:
                sys.exit(1)
            else:
                return False

    print(f"Stopped link #{link_id}")
    return True


@app.command()
def stop(link_id: str) -> bool:
    """Stop a CircuitPython link"""

    if link_id == "all":
        link_entries = _get_links_list("*")
        for link_entry in link_entries:
            _stop_link(link_entry[0], hard_fault=False)
        sys.exit(0)
    if link_id == "last":
        link_id = str(CircuitPythonLink.get_next_link_id() - 1)
        if link_id == "0":
            print("There are no links in the history")
            sys.exit(1)

    try:
        link_id = int(link_id)
    except ValueError:
        print('Link ID must be the ID, "last", or "all"')
        sys.exit(1)

    return _stop_link(link_id)


def _clear_link(link_id: int, *, force: bool = False, hard_fault: bool = False) -> bool:

    try:
        link = CircuitPythonLink.load_link_by_num(link_id)
    except FileNotFoundError:
        print(f"Link #{link_id} does not exist!")
        sys.exit(1)

    if not link.stopped and not force:
        print("Can only clear links marked as inactive.")
        print(f"To force clear link #{link.link_id}, use the --force option.")
        if hard_fault:
            sys.exit(1)
        else:
            return False

    os.remove(link.link_id_to_filename(link_id))
    print(f"Removed link #{link_id} from history")

    return True


@app.command()
def clear(link_id: str, *, force: bool = False) -> None:
    """Clear the link from the history"""

    if link_id == "all":
        link_entries = _get_links_list("*")
        for link_entry in link_entries:
            _clear_link(link_entry[0], force=force, hard_fault=False)
        sys.exit(0)
        # while clear("last", force=force):
        #    pass
        # return True
    if link_id == "last":
        link_id = str(CircuitPythonLink.get_next_link_id() - 1)
        if link_id == "0":
            return False

    try:
        link_id = int(link_id)
    except ValueError:
        print('Link ID must be the ID, "last", or "all"')
        sys.exit(1)

    return _clear_link(link_id, force=force)


def _add_links_header() -> List[Tuple[str, ...]]:
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

    link_paths = pathlib.Path(LINKS_DIRECTORY).glob(pattern)

    link_infos = []
    for link_path in link_paths:
        link = CircuitPythonLink.load_link_by_filepath(str(link_path))
        link_id = link.link_id
        link_name = link.name
        link_running = not link.stopped
        if not abs_paths:
            try:
                link_read = link.read_path.resolve().relative_to(os.getcwd())
            except ValueError:
                abs_paths = True
        if abs_paths:
            link_read = link.read_path.resolve()
        link_write = link.write_path.resolve()
        link_recursive = link.recursive
        link_proc = link.process_id
        link_base = link.base_dir
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

    return sorted(link_infos, key=lambda x: x[0])


@app.command()
def view(link_id: str, *, abs_paths: bool = False) -> None:
    """List links in the history"""

    last_requested_flag = False

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

    link_infos = [x[:-1] for x in _get_links_list(pattern, abs_paths=abs_paths)]

    if not link_infos:
        if link_id == "all" or last_requested_flag:
            print("No links in the history to view")
            sys.exit(0)
        print("This link ID is not in the history")
        sys.exit(1)

    # link_infos.insert(0, _add_links_header())
    show_list = _add_links_header()
    print(tabulate(link_infos, headers=show_list))


@app.command()
def restart(link_id: str) -> None:
    """Restart a link"""

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
        except ValueError:
            print('Please use a valid link ID, "last", or "all" (default)')
            sys.exit(1)

    link_list = _get_links_list(pattern)
    if not link_list:
        print("There are no links in the history to restart")
        sys.exit(1)

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


@app.command()
def about() -> None:
    """Display information about ``circlink``"""

    print("Originally built with love by Tekktrik")
    print("Happy hackin'!")


@app.command()
def version() -> None:
    """Display the current version of circlink"""

    print(__version__)


def main() -> None:
    """Main function that runs when ``circlink`` is called as a CLI"""

    _ensure_links_folder()
    app()


if __name__ == "__main__":
    main()
