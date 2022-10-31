# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

"""
The sub-script for handling the config options for ``circlink``.

Author(s): Alec Delaney (Tekktrik)
"""

import json
import os

import yaml
from typer import Argument, Exit, Option, Typer

import circlink

config_app = Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Change config settings for circlink",
)


@config_app.callback(invoke_without_command=True)
def callback(
    filepath: bool = Option(
        False, "--filepath", "-f", help="Print the settings file location"
    ),
    reset: bool = Option(
        False, "--reset", help="Reset the configuration settings to their defaults"
    ),
) -> None:
    """Run the callback for the config subcommand."""
    if filepath:
        print(f"Settings file: {os.path.abspath(circlink.SETTINGS_FILE)}")
        raise Exit()
    if reset:
        circlink.reset_config_file()


@config_app.command()
def view(
    config_path: str = Argument("all", help="The setting to view, using dot notation")
) -> None:
    """View a config setting for circlink."""
    # Get the settings, show all settings if no specific on is specified
    setting = circlink.get_settings()
    if config_path == "all":
        print(json.dumps(setting, indent=4))
        raise Exit()

    # Get the specified settings
    config_args = config_path.split(".")
    try:
        for extra_arg in config_args[:-1]:
            setting = setting[extra_arg]
        value = setting[config_args[-1]]
    except KeyError as err:
        print(f"Setting {config_path} does not exist")
        raise Exit(1) from err

    # Show the specified setting
    print(f"{config_path}: {json.dumps(value, indent=4)}")


@config_app.command()
def edit(
    config_path: str = Argument("all", help="The setting to view, using dot notation"),
    value: str = Argument(..., help="The value to set for the setting"),
) -> None:
    """Edit a config setting for circlink."""
    # Get the settings, use another reference to parse
    orig_setting = circlink.get_settings()
    setting = orig_setting
    config_args = config_path.split(".")

    # Handle bool conversions
    if value.lower() == "true":
        value = True
    elif value.lower() == "false":
        value = False

    # Attempt to parse for the specified config setting and set it
    try:
        for extra_arg in config_args[:-1]:
            setting = setting[extra_arg]
        prev_value = setting[config_args[-1]]
        prev_value_type = type(prev_value)
        if prev_value_type == dict:
            raise ValueError
        if prev_value_type == bool and value not in (True, False):
            raise TypeError
        setting[config_args[-1]] = prev_value_type(value)
    except KeyError as err:
        print(f"Setting {config_path} does not exist")
        raise Exit(1) from err
    except TypeError as err:
        print(
            f"Cannot use that value for this setting, must be of type {prev_value_type}"
        )
        raise Exit(1) from err
    except ValueError as err:
        print("Cannot change this setting, please change the sub-settings within it")
        raise Exit(1) from err

    # Write the settings back to the file
    with open(circlink.SETTINGS_FILE, mode="w", encoding="utf-8") as yamlfile:
        yaml.safe_dump(orig_setting, yamlfile)
