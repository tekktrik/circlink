# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

"""
Information and methods pertaining to links and link files.

Author(s): Alec Delaney (Tekktrik)
"""

import csv
import fcntl
import functools
import json
import os
import pathlib
import shutil
import time
from collections import namedtuple
from typing import Dict, Iterator, List, Literal, Optional, Union

from typer import Exit

from circlink import LEDGER_FILE, LINKS_DIRECTORY

# Namedtuple for ledger entries
LedgerEntry = namedtuple("LedgerEntry", ("filename", "link_id", "process_id"))


# pylint: disable=too-many-instance-attributes
class CircuitPythonLink:
    """The link to the device."""

    def __init__(
        self,
        read_path: str,
        write_path: str,
        base_dir: str,
        *,
        name: str = "",
        recursive: bool = False,
        wipe_dest: bool = False,
        skip_presave: bool = False,
        proc_id: int = 0,
        confirmed: bool = False,
        end_flag: bool = False,
        stopped: bool = False,
    ) -> None:
        """Initialize the link."""
        self._read_path = pathlib.Path(read_path)
        self._write_path = pathlib.Path(write_path)
        self._base_dir = pathlib.Path(base_dir)

        if not self._read_path.exists() and not self._read_path.parent.is_dir():
            print(
                "Read path is not valid, please reference a specific file or glob pattern for files"
            )
            raise Exit(1)

        self._name = name
        self._recursive = recursive
        self._wipe_dest = wipe_dest
        self._skip_presave = skip_presave
        self._link_id = self.get_next_link_id()
        self.process_id: int = proc_id
        self.confirmed: bool = confirmed
        self.end_flag: bool = end_flag
        self._stopped = stopped

    @staticmethod
    def get_next_link_id() -> int:
        """Get the next link ID."""
        link_gen = pathlib.Path(LINKS_DIRECTORY).glob("link*.json")
        link_nums = [int(link_file.name[4:-5]) for link_file in link_gen]
        if not link_nums:
            return 1
        return max(link_nums) + 1

    @property
    def read_path(self) -> pathlib.Path:
        """Get the read path for the link."""
        return self._read_path

    @property
    def write_path(self) -> pathlib.Path:
        """Get the write path for the link."""
        return self._write_path

    @property
    def base_dir(self) -> pathlib.Path:
        """Get the base directory for the read path."""
        return self._base_dir

    @property
    def name(self) -> str:
        """Get the link name."""
        return self._name

    @property
    def recursive(self) -> bool:
        """Whether the link is recursive for the read path."""
        return self._recursive

    @property
    def link_id(self) -> int:
        """Link ID."""
        return self._link_id

    @property
    def skip_presave(self) -> bool:
        """Whether a forced save was enacted at the start of the link."""
        return self._skip_presave

    @property
    def wipe_dest(self) -> bool:
        """Whether the wrie path was recursively wiped before starting the link."""
        return self._wipe_dest

    @property
    def stopped(self) -> bool:
        """Whether the link is marked has stopped."""
        return self._stopped

    def save_link(self, *, save_directory: str = LINKS_DIRECTORY) -> pathlib.Path:
        """Save the link object as a file in the specified folder."""
        # Create the representative object
        link_obj = {
            "name": self._name,
            "read": str(self._read_path.resolve()),
            "write": str(self._write_path.resolve()),
            "base_dir": str(self._base_dir.resolve()),
            "recursive": self._recursive,
            "wipe_dest": self._wipe_dest,
            "skip_presave": self._skip_presave,
            "proc_id": self.process_id,
            "confirmed": self.confirmed,
            "end_flag": self.end_flag,
            "stopped": self._stopped,
        }

        # Get the filename
        save_filepath = self.link_id_to_filename(
            self._link_id, directory=save_directory
        )

        # Save the object as a JSON file
        with open(save_filepath, mode="w", encoding="utf-8") as linkfile:
            json.dump(link_obj, linkfile, indent=4)

        # Return the save filepath
        return pathlib.Path(save_filepath)

    @classmethod
    def load_link_by_filepath(cls, link_filepath: str) -> "CircuitPythonLink":
        """Create a CircuitPythonLink from a JSON file, by filepath."""
        with open(link_filepath, encoding="utf-8") as linkfile:
            link_obj = json.load(linkfile)

        link = cls(
            name=link_obj["name"],
            read_path=link_obj["read"],
            write_path=link_obj["write"],
            base_dir=link_obj["base_dir"],
            recursive=link_obj["recursive"],
            wipe_dest=link_obj["wipe_dest"],
            skip_presave=link_obj["skip_presave"],
            proc_id=link_obj["proc_id"],
            confirmed=link_obj["confirmed"],
            end_flag=link_obj["end_flag"],
            stopped=link_obj["stopped"],
        )

        link._link_id = CircuitPythonLink.filename_to_link_id(link_filepath)

        return link

    @classmethod
    def load_link_by_num(cls, link_num: int) -> "CircuitPythonLink":
        """Create a CircuitPythonLink from a JSON file, by number."""
        link_filepath = cls.link_id_to_filename(link_num)
        return cls.load_link_by_filepath(link_filepath)

    @staticmethod
    def link_id_to_filename(num: int, *, directory: str = LINKS_DIRECTORY) -> str:
        """Create a link filename from a link ID."""
        return os.path.join(directory, "link" + str(num) + ".json")

    @staticmethod
    def filename_to_link_id(filepath: Union[pathlib.Path, str]) -> int:
        """Get a link ID from a filename."""
        if isinstance(filepath, str):
            filepath = pathlib.Path(filepath)

        return int(filepath.name[4:-5])

    def _get_files_monitored(self):

        file_pattern = self._read_path.name
        file_parent = self._read_path.parent

        all_potential = list(
            file_parent.rglob(file_pattern)
            if self._recursive
            else file_parent.glob(file_pattern)
        )

        return [file for file in all_potential if file.is_file()]

    # pylint: disable=too-many-branches
    def begin_monitoring(self) -> None:
        """Monitor the listed file(s) for changes."""
        # Ensure the write path exists
        os.makedirs(self._write_path, exist_ok=True)

        # Wipe the destination (write path) recursively
        if self._wipe_dest:
            shutil.rmtree(self._write_path)

        # Get the files that match the read path
        read_files = self._get_files_monitored()
        update_map: Dict[pathlib.Path, float] = {}

        # Add all the files to ledger and monitor struct if not already
        for read_file in read_files:
            ledger_file_path = str(
                self.get_write_filepath(self.write_path, read_file, self.base_dir)
            )
            if append_to_ledger(
                LedgerEntry(ledger_file_path, self.link_id, self.process_id),
                expect_entry=False,
            ):
                update_map[read_file] = read_file.stat().st_mtime
                if not self._skip_presave:
                    self._copy_file(self._write_path, read_file, self.base_dir)

        # Initialize list for files marked for deletion
        marked_delete = []

        # Load the link and repeatedly load while not flagged to stop
        temp_link = self.load_link_by_num(self._link_id)
        while not temp_link.end_flag:

            # Load the link
            temp_link = self.load_link_by_num(self._link_id)
            time.sleep(0.1)

            # Detect new files
            read_files = self._get_files_monitored()
            new_files: List[pathlib.Path] = []
            for file in read_files:
                ledger_file_path = str(
                    self.get_write_filepath(self.write_path, file, self.base_dir)
                )
                if (
                    append_to_ledger(
                        LedgerEntry(ledger_file_path, self.link_id, self.process_id),
                        expect_entry=False,
                    )
                    and file not in update_map
                ):
                    new_files.append(file)

            # Update the modified time for new files
            for file in new_files:
                update_map[file] = file.stat().st_mtime
                self._copy_file(self.write_path, file, self.base_dir)
            new_files = []

            # Iterate through listed existing files
            for file, last_modtime in update_map.items():

                # Detect deleted
                if not file.exists():
                    marked_delete.append(file)
                    continue

                # Detect changes
                modtime = file.stat().st_mtime
                if modtime > last_modtime:
                    self._copy_file(self._write_path, file, self.base_dir)
                    update_map[file] = modtime

            # Delete marked files
            for file in marked_delete:
                self._delete_file(self._write_path, file, self.base_dir)
                ledger_file_path = str(
                    self.get_write_filepath(self.write_path, file, self.base_dir)
                )
                ledger_entry = LedgerEntry(
                    ledger_file_path, self.link_id, self.process_id
                )
                remove_from_ledger(ledger_entry, expect_entry=True)
                try:
                    del update_map[file]
                except KeyError:
                    pass
            marked_delete = []

        # Remove files from ledger
        for file in self._get_files_monitored():
            ledger_entry = LedgerEntry(
                str(file.resolve()), self.link_id, self.process_id
            )
            remove_from_ledger(ledger_entry, expect_entry=True)

        # Mark link as end flag set and stopped, then save
        self.end_flag = True
        self._stopped = True
        self.save_link()

    @staticmethod
    def get_write_filepath(
        write_path: pathlib.Path, read_file: pathlib.Path, base_dir: pathlib.Path
    ) -> pathlib.Path:
        """Get the write filepath for a specific file."""
        read_file_relative = read_file.relative_to(base_dir)
        return write_path / read_file_relative

    @staticmethod
    def _copy_file(
        write_path: pathlib.Path,
        read_file: pathlib.Path,
        base_dir: pathlib.Path,
    ):
        read_file_relative = read_file.relative_to(base_dir)
        file_dest = write_path / read_file_relative

        if not file_dest.exists():
            os.makedirs(os.path.join(str(file_dest.parent.resolve())), exist_ok=True)

        shutil.copyfile(str(read_file.resolve()), file_dest.resolve())

    @staticmethod
    def _delete_file(
        write_path: pathlib.Path,
        read_file: pathlib.Path,
        base_dir: pathlib.Path,
    ):

        file_dest = CircuitPythonLink.get_write_filepath(
            write_path, read_file, base_dir
        )

        if file_dest.resolve().exists():
            os.remove(file_dest.resolve())


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
