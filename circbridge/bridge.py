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
            exit(1)

        self._name = name
        self._recursive = recursive
        self._wipe_dest = wipe_dest
        self._skip_presave = skip_presave
        self._bridge_id = self.get_next_bridge_id()
        self.process_id: int = proc_id
        self.confirmed: bool = confirmed
        self.end_flag: bool = end_flag
        self._stopped = stopped

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
    def recursive(self) -> bool:
        return self._recursive

    @property
    def bridge_id(self) -> int:
        return self._bridge_id

    @property
    def skip_presave(self) -> bool:
        return self._skip_presave

    @property
    def wipe_dest(self) -> bool:
        return self._wipe_dest

    @property
    def stopped(self) -> bool:
        return self._stopped

    def save_bridge(self, *, save_directory: str = BRIDGES_DIRECTORY) -> pathlib.Path:
        """Save the bridge object as a file in the specified folder"""

        bridge_obj = {
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
            # print(bridgefile.read())
            bridge_obj = json.load(bridgefile)

        return cls(
            name=bridge_obj["name"],
            read_path=bridge_obj["read"],
            write_path=bridge_obj["write"],
            recursive=bridge_obj["recursive"],
            wipe_dest=bridge_obj["wipe_dest"],
            skip_presave=bridge_obj["skip_presave"],
            proc_id=bridge_obj["proc_id"],
            confirmed=bridge_obj["confirmed"],
            end_flag=bridge_obj["end_flag"],
            stopped=bridge_obj["stopped"],
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

        # Wipe the destination (write path) recursively
        if self._wipe_dest:
            shutil.rmtree(self._write_path)

        # Ensure the write path exists
        os.makedirs(self._write_path, exist_ok=True)

        file_pattern = self._read_path.name
        file_parent = self._read_path.parent
        read_files = list(
            file_parent.rglob(file_pattern)
            if self._recursive
            else file_parent.glob(file_pattern)
        )
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

        temp_bridge = self.load_bridge_by_num(self._bridge_id)
        while not temp_bridge.end_flag:

            # print(temp_bridge.end_flag)
            temp_bridge = self.load_bridge_by_num(self._bridge_id)
            time.sleep(0.1)

            # Detect new files
            # TODO: making getting files into its own function
            read_files = list(
                file_parent.rglob(file_pattern)
                if self._recursive
                else file_parent.glob(file_pattern)
            )
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
        self.save_bridge()

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
