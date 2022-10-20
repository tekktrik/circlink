# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

"""
Methods pertaining to the ledger file of all tracked files

Author(s): Alec Delaney (Tekktrik)
"""

import os
import pathlib
from typer import get_app_dir

APP_DIRECTORY = get_app_dir("circlink")
LEDGER_FILE = os.path.join(APP_DIRECTORY, "ledger.csv")


def ensure_ledger_file() -> None:
    """Ensure the ledger file exists, or create it if not"""

    ledger_path = pathlib.Path(LEDGER_FILE)
    ledger_path.touch(exist_ok=True)
