# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

import os
import time
import signal
from datetime import datetime, timedelta
from typing_extensions import Literal
from typer import Typer
from circlink.link import LINKS_DIRECTORY, CircuitPythonLink


app = Typer()


def _ensure_links_folder() -> None:
    """Ensures that the ``links`` folder exists"""

    if not os.path.exists(LINKS_DIRECTORY):
        os.mkdir(LINKS_DIRECTORY)


@app.command()
def start(
    read_path: str,
    write_path: str,
    *,
    name: str = "",
    recursive: bool = False,
    wipe_dest: bool = False,
    skip_presave: bool = False,
) -> None:
    """Start a CiruitPython link"""

    if "*" not in read_path and recursive:
        print("--recursive can only be used with glob patterns!")
        exit(1)

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


def _stop_link(link_id: int) -> Literal[True]:

    try:
        link = CircuitPythonLink.load_link_by_num(link_id)
    except FileNotFoundError:
        print("A link with this ID does not exist!")
        exit(1)

    link.end_flag = True
    link.save_link()

    start_time = datetime.now()
    error_time = start_time + timedelta(seconds=5)

    while not link.stopped:
        link = CircuitPythonLink.load_link_by_num(link_id)
        time.sleep(0.5)  # Slight delay
        if datetime.now() >= error_time:
            print("Link could not be stopped!")
            exit(1)

    print(f"Stopped link #{link_id}")
    clear(link_id)
    return True


@app.command()
def stop(link_id: str) -> bool:

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

    return _stop_link(link_id)


def _clear_link(link_id: int, *, force: bool = False) -> bool:

    try:
        link = CircuitPythonLink.load_link_by_num(link_id)
    except FileNotFoundError:
        print("A link with this ID does not exist!")
        exit(1)

    if not link.stopped and not force:
        print("Can only clear links marked as inactive.")
        print("To force clear this link, use the --force option.")
        exit(1)

    os.remove(link.link_num_to_filename(link_id))
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

    return _clear_link(link_id, force=force)


@app.command(name="list")
def list_links() -> None:
    raise NotImplementedError()


@app.command()
def about(link_id: int = 0) -> None:
    raise NotImplementedError()


def main() -> None:
    _ensure_links_folder()
    app()


if __name__ == "__main__":
    main()
