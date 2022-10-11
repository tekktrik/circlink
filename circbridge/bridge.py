# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

import os
import time
import json
import pathlib
import shutil
from typing import Dict, List

PACKAGE_DIRECTORY = os.path.abspath(os.path.split(__file__)[0])
BRIDGES_DIRECTORY = os.path.join(PACKAGE_DIRECTORY, "..", "bridges")


class BridgeRecord:
    """The bridge record"""

    def __init__(
        self,
        read_path: str,
        write_path: str,
        *,
        name: str = "",
        contents_only: bool = False,
        clean_folder: bool = False,
        wipe_dest: bool = False,
        skip_presave: bool = False,
        proc_id: int = 0,
        confirmed: bool = False,
        end_flag: bool = False,
    ) -> None:

        self._read_path = pathlib.Path(read_path)
        self._write_path = pathlib.Path(write_path)
        self._name = name
        self._contents_only = contents_only
        self._clean_folder = clean_folder
        self._wipe_dest = wipe_dest
        self._skip_presave = skip_presave
        self._bridge_id = self.get_next_bridge_id()
        self.process_id: int = proc_id
        self.confirmed: bool = confirmed
        self.end_flag: bool = end_flag

        if contents_only and self._read_path.is_file():
            raise OSError(
                "Contents only option cannot be used when the source is a file"
            )

        if clean_folder and (
            self._read_path.is_file() or (self._read_path.is_dir() and contents_only)
        ):
            raise OSError("Wiping endpoint can only be used to wipe a folder source")

    @staticmethod
    def get_next_bridge_id() -> int:
        """Get the next bridge ID"""

        bridge_gen = pathlib.Path(BRIDGES_DIRECTORY).glob("bridge*.json")
        bridge_nums = [int(bridge_file.name[6:-5]) for bridge_file in bridge_gen]
        if not bridge_nums:
            return 1
        return max(bridge_nums) + 1

    @property
    def read_path(self) -> pathlib.Path:
        return self._read_path

    @property
    def write_path(self) -> pathlib.Path:
        return self._write_path

    @property
    def name(self) -> str:
        return self._name

    @property
    def bridge_id(self) -> int:
        return self._bridge_id

    @property
    def contents_only(self) -> bool:
        return self._contents_only

    @property
    def clean_folder(self) -> bool:
        return self._clean_folder

    @property
    def skip_presave(self) -> bool:
        return self._skip_presave

    @property
    def wipe_dest(self) -> bool:
        return self._wipe_dest

    def save_bridge(self, *, save_directory: str = BRIDGES_DIRECTORY) -> pathlib.Path:
        """Save the bridge object as a file in the specified folder"""

        bridge_obj = {
            "name": self._name,
            "read": str(self._read_path.absolute()),
            "write": str(self._write_path.absolute()),
            "contents_only": self._contents_only,
            "clean_folder": self._clean_folder,
            "wipe_dest": self._wipe_dest,
            "skip_presave": self._skip_presave,
            "proc_id": self.process_id,
            "confirmed": self.confirmed,
            "end_flag": self.end_flag,
        }

        save_filepath = self.bridge_num_to_filename(
            self._bridge_id, directory=save_directory
        )

        with open(save_filepath, mode="w", encoding="utf-8") as bridgefile:
            json.dump(bridge_obj, bridgefile, indent=4)

        return pathlib.Path(save_filepath)

    @classmethod
    def _load_bridge_by_filepath(cls, bridge_filepath: str) -> "BridgeRecord":
        """Create a BridgeRecord from a JSON file, by filepath"""

        with open(bridge_filepath, mode="r", encoding="utf-8") as bridgefile:
            #print(bridgefile.read())
            bridge_obj = json.load(bridgefile)

        return cls(
            name=bridge_obj["name"],
            read_path=bridge_obj["read"],
            write_path=bridge_obj["write"],
            contents_only=bridge_obj["contents_only"],
            clean_folder=bridge_obj["clean_folder"],
            wipe_dest=bridge_obj["wipe_dest"],
            skip_presave=bridge_obj["skip_presave"],
            proc_id=bridge_obj["proc_id"],
            confirmed=bridge_obj["confirmed"],
            end_flag=bridge_obj["end_flag"],
        )

    @classmethod
    def load_bridge_by_num(cls, bridge_num: int) -> "BridgeRecord":
        """Create a BridgeRecord from a JSON file, by number"""

        bridge_filepath = cls.bridge_num_to_filename(bridge_num)
        bridge = cls._load_bridge_by_filepath(bridge_filepath)
        bridge._bridge_id = bridge_num
        return bridge

    @staticmethod
    def bridge_num_to_filename(num: int, *, directory: str = BRIDGES_DIRECTORY) -> str:
        return os.path.join(directory, "bridge" + str(num) + ".json")

    def begin_monitoring(self) -> None:
        """Monitor the listed file/directory for changes"""

        if self._wipe_dest:
            shutil.rmtree(self._write_path)

        os.makedirs(self._write_path, exist_ok=True)

        read_files = (
            [self._read_path]
            if self._read_path.is_file()
            else list(self._read_path.rglob("*"))
        )
        update_map: Dict[pathlib.Path, float] = {}

        if self._contents_only:
            write_path = self._write_path
        else:
            new_folder_name = os.path.basename(os.path.split(self._read_path)[0])
            write_path_str = os.path.join(self._write_path, new_folder_name)
            os.makedirs(write_path_str, exist_ok=True)
            write_path = pathlib.Path(write_path_str)

        wacky = self._read_path.is_dir()
        read_path_basis_str = (
            self._read_path.name
            if self._read_path.is_dir()
            else self._read_path.parts[-2]
        )
        # TODO: same parent and child names confuse it
        read_path_basis = pathlib.Path(os.path.join("..", read_path_basis_str)).absolute()

        if self._clean_folder:
            shutil.rmtree(write_path)

        for read_file in read_files:
            update_map[read_file] = read_file.stat().st_mtime
            if not self._skip_presave:
                self._copy_file(write_path, read_file, read_path_basis)

        temp_bridge = self.load_bridge_by_num(self._bridge_id)
        while not temp_bridge.end_flag:

            #print(temp_bridge.end_flag)
            temp_bridge = self.load_bridge_by_num(self._bridge_id)
            time.sleep(0.1)

            # Detect new files
            read_files = (
                [self._read_path]
                if self._read_path.is_file()
                else list(self._read_path.rglob("*"))
            )
            new_files: List[pathlib.Path] = []
            for file in read_files:
                if file not in update_map:
                    new_files.append(file)
            for file in new_files:
                update_map[file] = file.stat().st_mtime

            for file, last_modtime in update_map.items():

                # Detect deleted
                if not file.exists():
                    self._delete_file(write_path, file, read_path_basis)
                    del update_map[file]

                # Detect changes
                modtime = file.stat().st_mode
                if modtime > last_modtime:
                    self._copy_file(write_path, file, read_path_basis)
                    update_map[file] = modtime

    def _copy_file(
        self,
        write_path: pathlib.Path,
        read_file: pathlib.Path,
        read_basis: pathlib.Path,
    ):
        absy = read_basis.absolute()
        save_file_path = os.path.join(
            str(write_path), read_file.relative_to(absy.resolve())
        )
        shutil.copyfile(str(read_file), save_file_path)

    def _delete_file(
        self,
        write_path: pathlib.Path,
        read_file: pathlib.Path,
        read_basis: pathlib.Path,
    ):
        os.remove(os.path.join(str(write_path), read_file.relative_to(str(read_basis.absolute()))))
