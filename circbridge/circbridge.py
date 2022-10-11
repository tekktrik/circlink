# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

import os
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
def start(read_path: str, write_path: str, *, name: str = "") -> None:
    """Start a CiruitPython bridge"""

    bridge = BridgeRecord(read_path, write_path, name=name)
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
            if datetime.now() >= error_time:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                raise OSError("Could not start bridge process!")

    else:  # PID is 0
        while not bridge.process_id:
            bridge = BridgeRecord.load_bridge_by_num(bridge_id)
        bridge.confirmed = True
        bridge.save_bridge()

        bridge.begin_monitoring()



@app.command()
def stop(id: int = 0, *, name: str = "") -> None:
    pass


@app.command()
def clear(id: int = 0, *, name: str = "") -> None:
    pass


@app.command(name="list")
def list_bridges() -> None:
    pass


@app.command()
def about(id: int = 0, *, name: str = "") -> None:
    pass


def main() -> None:
    _ensure_bridges_folder()
    app()


if __name__ == "__main__":
    main()
