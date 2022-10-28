# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

"""
The main script handling CLI interactions for ``circlink``.

Author(s): Alec Delaney (Tekktrik)
"""

import os
import pathlib
import shutil

import typer
import yaml

__version__ = "0.0.0+auto.0"

# Filepath constants
APP_DIRECTORY = typer.get_app_dir("circlink")
LINKS_DIRECTORY = os.path.join(APP_DIRECTORY, "links")
LEDGER_FILE = os.path.join(APP_DIRECTORY, "ledger.csv")
SETTINGS_FILE = os.path.join(APP_DIRECTORY, "settings.yaml")
WORKSPACE_DIRECTORY = os.path.join(APP_DIRECTORY, "workspaces")
WORKSPACE_LIST_DIRECTORY = os.path.join(WORKSPACE_DIRECTORY, "saved")
CURRENT_WORKSPACE_FILE = os.path.join(WORKSPACE_DIRECTORY, "current.txt")


def get_settings():
    """Get the contents of the settings file."""
    with open(SETTINGS_FILE, encoding="utf-8") as yamlfile:
        return yaml.safe_load(yamlfile)


def reset_config_file() -> None:
    """Reset the config file."""
    settings_file = os.path.join(__file__, "..", "templates", "settings.yaml")
    shutil.copy(os.path.abspath(settings_file), SETTINGS_FILE)


def ensure_app_folder_setup() -> None:
    """Ensure that the configuration folder exists."""
    if not os.path.exists(APP_DIRECTORY):
        os.mkdir(APP_DIRECTORY)

    ensure_links_folder()
    ensure_ledger_file()
    ensure_settings_file()
    ensure_workspace_tree()


def ensure_settings_file() -> None:
    """Ensure the settings file is set up."""
    settings_path = pathlib.Path(SETTINGS_FILE)
    if not settings_path.exists():
        reset_config_file()


def ensure_links_folder() -> None:
    """Ensure the links folder is created."""
    if not os.path.exists(LINKS_DIRECTORY):
        os.mkdir(LINKS_DIRECTORY)


def ensure_ledger_file() -> None:
    """Ensure the ledger file exists, or create it if not."""
    ledger_path = pathlib.Path(LEDGER_FILE)
    ledger_path.touch(exist_ok=True)


def ensure_workspace_tree() -> None:
    """Ensure the workspace tree exists, or create it if not."""
    for directory in (WORKSPACE_DIRECTORY, WORKSPACE_LIST_DIRECTORY):
        if not os.path.exists(directory):
            os.mkdir(directory)
    pathlib.Path(CURRENT_WORKSPACE_FILE).touch(exist_ok=True)
