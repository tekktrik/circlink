# SPDX-FileCopyrightText: 2022 Alec Delaney
#
# SPDX-License-Identifier: MIT

"""The main script handling CLI interactions for ``circlink``.

Author(s): Alec Delaney (Tekktrik)
"""

import importlib.util
import os
import pkgutil
import shutil
import sys

import circup
import click
import tabulate

import circlink
import circlink.backend
import circlink.ledger
import circlink.link


@click.group()
@click.version_option(package_name="circlink")
def cli() -> None:
    """Autosave local files to your CircuitPython board."""
    circlink.ensure_app_folder_setup()


@cli.command()
@click.argument("readpath")
@click.argument("writepath")
@click.option(
    "--path",
    is_flag=True,
    default=False,
    help="Designate the write path as absolute or relative to the current directory",
)
@click.option("-n", "--name", help="A name for the new link")
@click.option(
    "-r",
    "--recursive",
    is_flag=True,
    default=False,
    help="Whether the link glob pattern is recursive",
)
@click.option(
    "-w",
    "--wipe-destination",
    is_flag=True,
    default=False,
    help="Wipe the write destination recursively before starting the link",
)
@click.option(
    "-s",
    "--skip-presave",
    is_flag=True,
    default=False,
    help="Skip the inital save and write performed when opening a link",
)
def start(  # noqa: PLR0913
    readpath: str,
    writepath: str,
    *,
    path: bool,
    name: str,
    recursive: bool,
    wipe_dest: bool,
    skip_presave: bool,
) -> None:
    """Start a CircuitPython link."""
    circlink.backend.start_backend(
        readpath,
        writepath,
        os.getcwd(),
        path=path,
        name=name,
        recursive=recursive,
        wipe_dest=wipe_dest,
        skip_presave=skip_presave,
    )
    circlink.backend.set_cws_name("")


@cli.command()
@click.argument("link_id")
@click.option(
    "-c",
    "--clear",
    is_flag=True,
    default=False,
    help="Clear the history of the specified link(s) as well",
)
def stop(
    link_id: str,
    clear_flag: bool,
) -> None:
    """Stop a CircuitPython link."""
    # If stopping all links, stop links using the "last" option until done
    if link_id == "all":
        link_entries = circlink.link.get_links_list("*")
        for link_entry in link_entries:
            circlink.backend.stop_backend(link_entry[0], hard_fault=False)
            if clear_flag:
                circlink.backend.clear_backend(link_entry[0], hard_fault=False)
        return

    # If stopping the last link, calculate its link ID
    if link_id == "last":
        link_id = str(circlink.link.CircuitPythonLink.get_next_link_id() - 1)
        if link_id == "0":
            raise click.ClickException("There are no links in the history")

    # Detect if the link ID is not valid
    try:
        link_id = int(link_id)
    except ValueError:
        raise click.ClickException('Link ID must be the ID, "last", or "all"')

    # Stop the link, clear as well if requested
    circlink.backend.stop_backend(link_id)
    if clear_flag:
        circlink.backend.clear_backend(link_id)


@cli.command()
@click.argument("link_id")
@click.option(
    "-f",
    "--force",
    is_flag=True,
    default=False,
    help="Ignore warning and force clear from history",
)
def clear(
    link_id: str,
    *,
    force: bool,
) -> None:
    """Clear the link from the history."""
    # If clearing all links, repetitively clear the last link
    if link_id == "all":
        link_entries = circlink.link.get_links_list("*")
        for link_entry in link_entries:
            circlink.backend.clear_backend(link_entry[0], force=force, hard_fault=False)
        return

    # If clearing the last link link, calculate its link ID
    if link_id == "last":
        link_id = str(circlink.link.CircuitPythonLink.get_next_link_id() - 1)
        if link_id == "0":
            return

    # Detect if the link ID is not valid
    try:
        link_id = int(link_id)
    except ValueError:
        raise click.ClickException('Link ID must be the ID, "last", or "all"')

    # Clear the link
    circlink.backend.clear_backend(link_id, force=force)


@cli.command()
@click.argument("link_id", default="all")
@click.option(
    "-a",
    "--abs_paths",
    is_flag=True,
    default=False,
    help="Show the read path as absolute",
)
def view(
    link_id: str,
    *,
    abs_paths: bool,
) -> None:
    """List links in the history."""
    # For recursion purposes, note whether link ID is "last"
    last_requested_flag = False

    # Handle cases of link ID being "all" or "last", or just parse link ID
    if link_id == "all":
        pattern = "*"
    elif link_id == "last":
        last_requested_flag = True
        link_id = str(circlink.link.CircuitPythonLink.get_next_link_id() - 1)
        pattern = "link" + link_id + ".json"
        if link_id == "0":
            pattern = "*"
    else:
        try:
            int(link_id)
            pattern = "link" + link_id + ".json"
        except ValueError:
            raise click.ClickException(
                'Please use a valid link ID, "last", or "all" (default)'
            )

    # Discard the link base directory for printing purposes
    link_infos = circlink.backend.view_backend(pattern, abs_paths=abs_paths)

    # Handle if no links available
    if not link_infos:
        if link_id == "all" or last_requested_flag:
            raise click.echo("No links in the history to view")
            return
        raise click.ClickException("This link ID is not in the history")


@cli.command()
@click.argument("link_id")
def restart(link_id: str) -> None:
    """Restart a link."""
    # Handle cases of "all" or "last", or parse link ID
    if link_id == "all":
        pattern = "*"
    elif link_id == "last":
        link_id = str(circlink.link.CircuitPythonLink.get_next_link_id() - 1)
        pattern = "link" + link_id + ".json"
        if link_id == "0":
            pattern = "*"
    else:
        try:
            int(link_id)
            pattern = "link" + link_id + ".json"
        except ValueError as err:
            raise click.ClickException('Please use a valid link ID, "last", or "all"')

    # Get the list of links in history if possible
    link_list = circlink.link.get_links_list(pattern)
    if not link_list:
        raise click.ClickException("There are no links in the history to restart")

    # Attempt to restart and clear the link if it's not active
    for link in link_list:
        if link[2]:
            click.echo(f"Link #{link[0]} is active, not restarting this link.")
        else:
            circlink.backend.start_backend(
                str(link[3]),
                str(link[4]),
                link[-1],
                name=link[1],
                recursive=link[5],
                path=True,
            )
            circlink.backend.clear_backend(link[0])


@cli.command()
def detect() -> None:
    """Attempt to detect a CircuitPython board."""
    device = circup.find_device()
    if device:
        click.echo(f"CircuitPython device detected: {device}")
    else:
        raise click.ClickException("No CircuitPython device detected")


@cli.command()
def about() -> None:
    """Display information about circlink."""
    click.echo("Originally built with love by Tekktrik")
    click.echo("Happy hackin'!")


def reset() -> None:
    """Reset the app directory.

    Useful if you upgrade circlink and there are breaking changes.
    """
    shutil.rmtree(circlink.APP_DIRECTORY)
    click.echo("Removed circlink app directory, settngs and history deleted!")
    click.echo("These will be created on next use of circlink.")
    click.echo("Please check the integrity of any files handled by circlink.")


@cli.command()
def ledger() -> None:
    """View the ledger of files controlled by links."""
    # Get the list of ledger entries if possible
    ledger_entries = list(circlink.ledger.iter_ledger_entries())
    if not ledger_entries:
        click.echo("No files being tracked by circlink")
        return

    # Display the process ID of links depending on settings
    table_headers = ("Write Path", "Link")
    if circlink.get_settings()["display"]["info"]["process-id"]:
        table_headers = table_headers + ("Process ID",)
    else:
        ledger_entries = [entry[:-1] for entry in ledger_entries]

    # Print the table with the format specified in config settings
    click.echo(
        tabulate.tabulate(
            ledger_entries,
            headers=table_headers,
            tablefmt=circlink.get_settings()["display"]["table"]["format"],
        )
    )


# Dynamically loading commands reused from circfirm, MIT License
# https://github.com/tekktrik/circfirm/blob/main/circfirm


def load_subcmd_folder(path: str, super_import_name: str) -> None:
    """Load subcommands dynamically from a folder of modules and packages."""
    subcmd_names = [
        (modname, ispkg) for _, modname, ispkg in pkgutil.iter_modules((path,))
    ]
    subcmd_paths = [
        os.path.abspath(os.path.join(path, subcmd_name[0]))
        for subcmd_name in subcmd_names
    ]

    for (subcmd_name, ispkg), subcmd_path in zip(subcmd_names, subcmd_paths):
        import_name = ".".join([super_import_name, subcmd_name])
        import_path = subcmd_path if ispkg else subcmd_path + ".py"
        module_spec = importlib.util.spec_from_file_location(import_name, import_path)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        source_cli: click.MultiCommand = getattr(module, "cli")
        if isinstance(source_cli, click.Group):
            subcmd = click.CommandCollection(sources=(source_cli,))
            subcmd.help = source_cli.__doc__
        else:
            subcmd = source_cli
        cli.add_command(subcmd, subcmd_name)


# Load extra commands from the rest of the circfirm.cli subpackage
cli_pkg_path = os.path.dirname(os.path.abspath(__file__))
cli_pkg_name = "circlink.cli"
load_subcmd_folder(cli_pkg_path, cli_pkg_name)
