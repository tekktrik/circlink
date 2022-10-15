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
from typer import Typer
from circup import find_device
from tabulate import tabulate
from circlink.link import LINKS_DIRECTORY, CircuitPythonLink

_TableRowEntry: TypeAlias = Tuple[int, str, bool, pathlib.Path, pathlib.Path, bool, int]

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
    """Start a CiruitPython link"""

    if "*" not in read_path and recursive:
        print("--recursive can only be used with glob patterns!")
        sys.exit(1)

    if not path:
        device_path = find_device()
        if not device_path:
            print("Cound not auto-detect board path!")
            sys.exit(1)
        write_path = os.path.join(device_path, write_path)

    link = CircuitPythonLink(
        read_path,
        write_path,
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


def _stop_link(link_id: int) -> Literal[True]:

    try:
        link = CircuitPythonLink.load_link_by_num(link_id)
    except FileNotFoundError:
        print(f"Link #{link_id} does not exist!")
        sys.exit(1)

    if link.stopped:
        print(f"Link #{link.link_id} is already stopped")
        sys.exit(0)

    link.end_flag = True
    link.save_link()

    start_time = datetime.now()
    error_time = start_time + timedelta(seconds=5)

    while not link.stopped:
        link = CircuitPythonLink.load_link_by_num(link_id)
        time.sleep(0.1)  # Slight delay
        if datetime.now() >= error_time:
            print(f"Link #{link.link_id} could not be stopped!")
            sys.exit(1)

    print(f"Stopped link #{link_id}")
    return True


@app.command()
def stop(link_id: str) -> bool:
    """Stop a CircuitPython link"""

    if link_id == "all":
        while stop("last"):
            pass
        return True
    if link_id == "last":
        link_id = str(CircuitPythonLink.get_next_link_id() - 1)
        if link_id == "0":
            return False

    try:
        link_id = int(link_id)
    except ValueError:
        print('Link ID must be the ID, "last", or "all"')
        sys.exit(1)

    return _stop_link(link_id)


def _clear_link(link_id: int, *, force: bool = False) -> bool:

    try:
        link = CircuitPythonLink.load_link_by_num(link_id)
    except FileNotFoundError:
        print(f"Link #{link_id} does not exist!")
        sys.exit(1)

    if not link.stopped and not force:
        print("Can only clear links marked as inactive.")
        print("To force clear this link, use the --force option.")
        sys.exit(1)

    os.remove(link.link_id_to_filename(link_id))
    print(f"Removed link #{link_id} from history")

    return True


@app.command()
def clear(link_id: str, *, force: bool = False) -> None:
    """Clear the link from the history"""

    if link_id == "all":
        while clear("last", force=force):
            pass
        return True
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


def _get_links_list(
    pattern: str, *, abs_paths: bool = False, name: str = ""
) -> List[_TableRowEntry]:

    link_paths = pathlib.Path(LINKS_DIRECTORY).glob(pattern)

    link_infos = [
        (
            "ID",
            "Name",
            "Running?",
            "Read Path",
            "Write Path",
            "Recursive?",
            "Process ID",
        )
    ]
    for link_path in link_paths:
        link = CircuitPythonLink.load_link_by_filepath(str(link_path))
        link_id = link.link_id
        link_name = "---" if not link.name else link.name
        link_running = not link.stopped
        if not abs_paths:
            try:
                link_read = link.read_path.resolve().relative_to(os.getcwd())
            except ValueError:
                abs_paths = True
        if abs_paths:
            link_read = link.read_path.resolve().absolute()
        link_write = link.write_path.absolute().resolve()
        link_recursive = link.recursive
        link_proc = link.process_id
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
                )
            )

    return link_infos


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

    link_infos = _get_links_list(pattern, abs_paths=abs_paths)

    if len(link_infos) == 1:
        if link_id == "all" or last_requested_flag:
            print("No links in the history to view")
            sys.exit(0)
        print("This link ID is not in the history")
        sys.exit(1)

    print(tabulate(link_infos, headers="firstrow"))


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
    if len(link_list) == 1:
        print("There are no links in the history to restart")
        sys.exit(1)

    for index, link in enumerate(link_list):
        if not index:
            continue
        if link[2]:
            print(f"Link #{link[0]} is active, not restarting this link.")
        else:
            start(
                str(link[3]), str(link[4]), name=link[1], recursive=link[5], path=True
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
    sys.exit(0)


@app.command()
def about() -> None:
    """Display information about ``circlink``"""

    print("Originally built with love by Tekktrik")
    print("Happy hackin'!")
    sys.exit(0)


@app.command()
def version() -> None:
    """Display the current version of circlink"""

    print(__version__)
    sys.exit(0)


def main() -> None:
    """Main function that runs when ``circlink`` is called as a CLI"""

    _ensure_links_folder()
    app()


if __name__ == "__main__":
    main()
