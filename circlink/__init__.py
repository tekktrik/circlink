# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

"""
The main script handling CLI interactions for ``circlink``.

Author(s): Alec Delaney (Tekktrik)
"""

import os
import shutil

import typer
import yaml

__version__ = "0.0.0+auto.0"

# Filepath constants
APP_DIRECTORY = typer.get_app_dir("circlink")
LINKS_DIRECTORY = os.path.join(APP_DIRECTORY, "links")
LEDGER_FILE = os.path.join(APP_DIRECTORY, "ledger.csv")
SETTINGS_FILE = os.path.join(APP_DIRECTORY, "settings.yaml")


def get_settings():
    """Get the contents of the settings file."""
    with open(SETTINGS_FILE, encoding="utf-8") as yamlfile:
        return yaml.safe_load(yamlfile)


def reset_config_file() -> None:
    """Reset the config file."""
    settings_file = os.path.join(__file__, "..", "templates", "settings.yaml")
    shutil.copy(os.path.abspath(settings_file), SETTINGS_FILE)
