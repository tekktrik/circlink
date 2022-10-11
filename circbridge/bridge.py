# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

import os
import json
import pathlib

PACKAGE_DIRECTORY = os.path.abspath(os.path.split(__file__)[0])
BRIDGES_DIRECTORY = os.path.join(PACKAGE_DIRECTORY, "..", "bridges")

class BridgeRecord:
    """The bridge record"""

    def __init__(self, read_path: str, write_path: str, *, name: str = "", proc_id: int = 0, confirmed: bool = False) -> None:

        self._read_path = pathlib.Path(read_path)
        self._write_path = pathlib.Path(write_path)
        self._name = name
        self._bridge_id = self.get_next_bridge_id()
        self.process_id: int = proc_id
        self.confirmed: bool = confirmed

    @staticmethod
    def get_next_bridge_id() -> int:
        """Get the next bridge ID"""

        bridge_gen = pathlib.Path(BRIDGES_DIRECTORY).glob("bridge*.json")
        bridge_nums = [int(bridge_file[6:-5]) for bridge_file in bridge_gen]
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

    def save_bridge(self, *, save_directory: str = BRIDGES_DIRECTORY) -> pathlib.Path:
        """Save the bridge object as a file in the specified folder"""

        bridge_obj = {
            "name": self._name,
            "read": str(self._read_path.absolute()),
            "write": str(self._write_path.absolute()),
            "proc_id": self.process_id,
            "confirmed": self.confirmed,
        }

        save_filepath = self.bridge_num_to_filename(self._bridge_id, directory=save_directory)

        with open(save_filepath, mode="w", encoding="utf-8") as bridgefile:
            json.dump(bridge_obj, bridgefile, indent=4)

        return pathlib.Path(save_filepath)


    @classmethod
    def load_bridge_by_filepath(cls, bridge_filepath: str) -> "BridgeRecord":
        """Create a BridgeRecord from a JSON file, by filepath"""

        with open(bridge_filepath, mode="r", encoding="utf-8") as bridgefile:
            bridge_obj = json.load(bridgefile)

        return cls(
            read_path=bridge_obj["read"],
            write_path=bridge_obj["write"],
            name=bridge_obj["name"],
            proc_id=bridge_obj["proc_id"],
            confirmed=bridge_obj["confirmed"],
        )


    def load_bridge_by_num(cls, bridge_num: int) -> "BridgeRecord":
        """Create a BridgeRecord from a JSON file, by number"""

        bridge_filepath = cls.bridge_num_to_filename(bridge_num)
        return cls.load_bridge_by_filepath(bridge_filepath)


    @staticmethod
    def bridge_num_to_filename(num: int, *, directory: str = BRIDGES_DIRECTORY) -> str:
        return os.path.join(directory, "bridge" + str(num) + ".json")


    def begin_monitoring(self) -> None:
        """Monitor the listed file/directory for changes"""

        while True:
            pass

