# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

"""
Information and methods pertaining to the ledger file.

Author(s): Alec Delaney (Tekktrik)
"""

import csv
import fcntl
import functools
from collections import namedtuple
from typing import Iterator, Literal, Optional

from circlink import LEDGER_FILE

# Namedtuple for ledger entries
LedgerEntry = namedtuple("LedgerEntry", ("filename", "link_id", "process_id"))


def with_ledger(mode: str = "a"):
    """
    Use the ledger file.

    Manages locking and unlocking the file
    """

    def decorator_with_ledger(func):
        """Work with the ledger file."""

        @functools.wraps(func)
        def wrapper_with_ledger(
            entry: LedgerEntry,
            *,
            expect_entry: Optional[bool] = None,
            use_lock: bool = True,
        ) -> bool:
            """Edit the ledger."""
            # Open the ledger file
            with open(LEDGER_FILE, mode=mode, encoding="utf-8") as filedesc:

                # Use a file lock if requested
                if use_lock:
                    fcntl.lockf(filedesc, fcntl.LOCK_EX)

                # Handle the entry
                if (expect_entry is None) or (
                    expect_entry == (entry.filename in iter_ledger_filenames())
                ):
                    result = func(entry, filedesc=filedesc)
                else:
                    result = False

                # Release the file lock if needed
                if use_lock:
                    fcntl.lockf(filedesc, fcntl.LOCK_UN)

                return result

        return wrapper_with_ledger

    return decorator_with_ledger


@with_ledger(mode="a")
def append_to_ledger(entry: LedgerEntry, **args) -> Literal[True]:
    """
    Add a file to the ledger.

    Returns whether the file actually was added (True) or if it already
    existed (False).
    """
    csvwriter = csv.writer(args["filedesc"])
    csvwriter.writerow(entry)
    return True


@with_ledger(mode="w")
def remove_from_ledger(entry: LedgerEntry, **args) -> Literal[True]:
    """
    Remove a file from the ledger.

    Returns whether the file actually was removed (True) or if it didn't
    exist (False).
    """
    csvwriter = csv.writer(args["filedesc"])
    for existing_entry in iter_ledger_filenames(False):
        if existing_entry != entry:
            csvwriter.writerow(existing_entry)
    return True


def iter_ledger_entries(use_lock: bool = True) -> Iterator[LedgerEntry]:
    """Iterate through ledger entries."""
    with open(LEDGER_FILE, mode="r+", encoding="utf-8") as csvfile:
        if use_lock:
            fcntl.lockf(csvfile, fcntl.LOCK_EX)
        csvreader = csv.reader(csvfile)
        for ledger_entry in csvreader:
            yield LedgerEntry(
                ledger_entry[0], int(ledger_entry[1]), int(ledger_entry[2])
            )
        if use_lock:
            fcntl.lockf(csvfile, fcntl.LOCK_UN)


def iter_ledger_filenames(use_lock: bool = True) -> Iterator[str]:
    """Iterate through ledger entry filenames."""
    for entry in iter_ledger_entries(use_lock):
        yield entry.filename
