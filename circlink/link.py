# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

"""
Information and methods pertaining to links and link files

Author(s): Alec Delaney (Tekktrik)
"""

import os
import sys
import time
import json
import pathlib
import shutil
from typing import Dict, List, Union

PACKAGE_DIRECTORY = os.path.abspath(os.path.split(__file__)[0])
LINKS_DIRECTORY = os.path.join(PACKAGE_DIRECTORY, "..", "links")


# pylint: disable=too-many-instance-attributes
class CircuitPythonLink:
    """Thelink to the device"""

    def __init__(
        self,
        read_path: str,
        write_path: str,
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

        self._read_path = pathlib.Path(read_path)
        self._write_path = pathlib.Path(write_path)

        if not self._read_path.exists() and not self._read_path.parent.is_dir():
            print(
                "Read path is not valid, please reference a specific file or glob pattern for files"
            )
            sys.exit(1)

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
        """Get the next link ID"""

        link_gen = pathlib.Path(LINKS_DIRECTORY).glob("link*.json")
        link_nums = [int(link_file.name[4:-5]) for link_file in link_gen]
        if not link_nums:
            return 1
        return max(link_nums) + 1

    @property
    def read_path(self) -> pathlib.Path:
        """The read path for the link"""
        return self._read_path

    @property
    def write_path(self) -> pathlib.Path:
        """The write path for the link"""
        return self._write_path

    @property
    def name(self) -> str:
        """The link name"""
        return self._name

    @property
    def recursive(self) -> bool:
        """Whether the link is recursive for the read path"""
        return self._recursive

    @property
    def link_id(self) -> int:
        """The link ID"""
        return self._link_id

    @property
    def skip_presave(self) -> bool:
        """Whether a forced save was enacted at the start of the link"""
        return self._skip_presave

    @property
    def wipe_dest(self) -> bool:
        """Whether the wrie path was recursively wiped before starting the link"""
        return self._wipe_dest

    @property
    def stopped(self) -> bool:
        """Whether the link is marked has stopped"""
        return self._stopped

    def save_link(self, *, save_directory: str = LINKS_DIRECTORY) -> pathlib.Path:
        """Save the link object as a file in the specified folder"""

        link_obj = {
            "name": self._name,
            "read": str(self._read_path.absolute()),
            "write": str(self._write_path.absolute()),
            "recursive": self._recursive,
            "wipe_dest": self._wipe_dest,
            "skip_presave": self._skip_presave,
            "proc_id": self.process_id,
            "confirmed": self.confirmed,
            "end_flag": self.end_flag,
            "stopped": self._stopped,
        }

        save_filepath = self.link_id_to_filename(
            self._link_id, directory=save_directory
        )

        with open(save_filepath, mode="w", encoding="utf-8") as linkfile:
            json.dump(link_obj, linkfile, indent=4)

        return pathlib.Path(save_filepath)

    @classmethod
    def load_link_by_filepath(cls, link_filepath: str) -> "CircuitPythonLink":
        """Create a CircuitPythonLink from a JSON file, by filepath"""

        with open(link_filepath, mode="r", encoding="utf-8") as linkfile:
            link_obj = json.load(linkfile)

        link = cls(
            name=link_obj["name"],
            read_path=link_obj["read"],
            write_path=link_obj["write"],
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
        """Create a CircuitPythonLink from a JSON file, by number"""

        link_filepath = cls.link_id_to_filename(link_num)
        return cls.load_link_by_filepath(link_filepath)

    @staticmethod
    def link_id_to_filename(num: int, *, directory: str = LINKS_DIRECTORY) -> str:
        """Create a link filename from a link ID"""
        return os.path.join(directory, "link" + str(num) + ".json")

    @staticmethod
    def filename_to_link_id(filepath: Union[pathlib.Path, str]) -> int:
        """Get a link ID from a filename"""

        if isinstance(filepath, str):
            filepath = pathlib.Path(filepath)

        return int(filepath.name[4:-5])

    def _get_files_monitored(self):

        file_pattern = self._read_path.name
        file_parent = self._read_path.parent

        return list(
            file_parent.rglob(file_pattern)
            if self._recursive
            else file_parent.glob(file_pattern)
        )

    def begin_monitoring(self) -> None:
        """Monitor the listed file(s) for changes"""

        # Ensure the write path exists
        os.makedirs(self._write_path, exist_ok=True)

        # Wipe the destination (write path) recursively
        if self._wipe_dest:
            shutil.rmtree(self._write_path)

        read_files = self._get_files_monitored()
        update_map: Dict[pathlib.Path, float] = {}

        read_path_basis_str = (
            self._read_path.name
            if self._read_path.is_dir()
            else self._read_path.parts[-2]
        )

        read_path_basis_str = os.path.join("..", read_path_basis_str)

        for read_file in read_files:
            update_map[read_file] = read_file.stat().st_mtime
            if not self._skip_presave:
                self._copy_file(self._write_path, read_file)

        marked_delete = []

        temp_link = self.load_link_by_num(self._link_id)
        while not temp_link.end_flag:

            temp_link = self.load_link_by_num(self._link_id)
            time.sleep(0.1)

            # Detect new files
            read_files = self._get_files_monitored()
            new_files: List[pathlib.Path] = []
            for file in read_files:
                if file not in update_map:
                    new_files.append(file)
            for file in new_files:
                update_map[file] = file.stat().st_mtime
                self._copy_file(self.write_path, file)
            new_files = []

            for file, last_modtime in update_map.items():

                # Detect deleted
                if not file.exists():
                    marked_delete.append(file)
                    continue

                # Detect changes
                modtime = file.stat().st_mtime
                if modtime > last_modtime:
                    self._copy_file(self._write_path, file)
                    update_map[file] = modtime

            # Delete marked files
            for file in marked_delete:
                self._delete_file(self._write_path, file)
                try:
                    del update_map[file]
                except KeyError:
                    pass
            marked_delete = []

        self.end_flag = True
        self._stopped = True
        self.save_link()

    def _copy_file(
        self,
        write_path: pathlib.Path,
        read_file: pathlib.Path,
    ):
        read_file_relative = read_file.relative_to(os.getcwd())
        file_dest = write_path / read_file_relative

        if not file_dest.exists():
            os.makedirs(os.path.join(str(file_dest.parent.absolute())), exist_ok=True)

        shutil.copyfile(str(read_file.resolve()), file_dest.resolve())

    def _delete_file(
        self,
        write_path: pathlib.Path,
        read_file: pathlib.Path,
    ):

        read_file_relative = read_file.relative_to(os.getcwd())
        file_dest = write_path / read_file_relative

        if file_dest.resolve().exists():
            os.remove(file_dest.resolve())
