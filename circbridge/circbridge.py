# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

import os
import time
import signal
from datetime import datetime, timedelta
from typer import Typer
from circbridge.bridge import BRIDGES_DIRECTORY, BridgeRecord


app = Typer()


def _ensure_bridges_folder() -> None:
    """Ensures that the ``bridges`` folder exists"""

    if not os.path.exists(BRIDGES_DIRECTORY):
        os.mkdir(BRIDGES_DIRECTORY)


@app.command()
def start(
    read_path: str,
    write_path: str,
    *,
    name: str = "",
    contents_only: bool = False,
    clean_folder: bool = False,
    wipe_dest: bool = False,
    skip_presave: bool = False
) -> None:
    """Start a CiruitPython bridge"""

    bridge = BridgeRecord(
        read_path,
        write_path,
        name=name,
        contents_only=contents_only,
        clean_folder=clean_folder,
        wipe_dest=wipe_dest,
        skip_presave=skip_presave,
    )

    bridge_id = bridge.bridge_id
    bridge.save_bridge()

    pid = os.fork()

    if pid:  # PID is a real process number

        bridge.process_id = pid
        bridge.save_bridge()

        start_time = datetime.now()
        error_time = start_time + timedelta(seconds=5)

        while not bridge.confirmed:
            bridge = BridgeRecord.load_bridge_by_num(bridge_id)
            time.sleep(0.5)  # Slight delay
            if datetime.now() >= error_time:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                raise OSError("Could not start bridge process!")

    else:  # PID is 0
        while not bridge.process_id:
            bridge = BridgeRecord.load_bridge_by_num(bridge_id)
            time.sleep(0.3)
        bridge.confirmed = True
        bridge.save_bridge()
        bridge.begin_monitoring()


@app.command()
def stop(bridge_id: int) -> None:
    bridge = BridgeRecord.load_bridge_by_num(bridge_id)
    bridge.end_flag = True
    bridge.save_bridge()

    start_time = datetime.now()
    error_time = start_time + timedelta(seconds=5)

    while not bridge.stopped:
        bridge = BridgeRecord.load_bridge_by_num(bridge_id)
        time.sleep(0.5)  # Slight delay
        if datetime.now() >= error_time:
            print("Bridge could not be stopped!")
            exit(1)

    clear(bridge_id)


@app.command()
def clear(bridge_id: int = 0, *, force: bool = False) -> None:
    """Clear the bridge from the history"""

    bridge = BridgeRecord.load_bridge_by_num(bridge_id)
    if not bridge.stopped and not force:
        print("Can only clear bridges marked as inactive.")
        print("To force clear this bridge, use the --force option.")
        exit(1)

    os.remove(bridge.bridge_num_to_filename(bridge_id))


@app.command(name="list")
def list_bridges() -> None:
    raise NotImplementedError()


@app.command()
def about(bridge_id: int = 0) -> None:
    raise NotImplementedError()


def main() -> None:
    _ensure_bridges_folder()
    app()


if __name__ == "__main__":
    main()
