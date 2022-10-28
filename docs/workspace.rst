Working With Workspaces
=======================

Introduction
------------

``circlink`` provides a quick and easy way to save complicated arrangements
of links using workspaces.  Workspaces are copies of link settings that can
be quickly saved and loaded for convenience.  You can interact with them
using the ``workspace`` command:

.. code-block:: shell

    circlink workspace [COMMAND]

Saving Workspaces
-----------------

To save a workspace, use the ``save`` subcommand.  For example, to save a
your current link history as a workspace named 'blinka_bot', you would use:

.. code-block:: shell

    circlink workspace save blinka_bot

Each workspace you save must have a unique name, to protect accidentally
losing a workspace.  If you want to explictly overwrite one, you can use
the ``--overwrite`` flag:

.. code-block:: shell

    circlink workspace save blinka_bot --overwrite

Loading Workspaces
------------------

To load a workspace, use the ``load`` subcommand.  For example, to load a
previously saved workspace named 'blinka_bot':

.. code-block:: shell

    circlink workspace load blinka_bot

Note that you can't load a workspace if you have any links in your current
history; this prevents you from interupting running links.  Use ``circlink
clear`` to clear links if this is the case.

Listing Workspaces
------------------

To list all of the saved workspaces, you can use the ``list`` subcommand:

.. code-block:: shell

    circlink workspace list

This will show all the saved links, as well as an asterisk before one if
it is your current workspace.  If you only want to see your current
workspace, you could also use the ``current`` subcommand:

.. code-block:: shell

    circlink workspace current

Deleting a Workspace
--------------------

If you ever want to delete a saved workspace, you can use the ``delete``
subcommand.  For example, to delete a previously saved workspace named
'blinka_bot':

.. code-block:: shell

    circlink workspace delete blinka_bot

Renaming a Workspace
--------------------

You may want to update the name for a workspace after creating it.  To
do so, use the ``rename`` subcommand.  For example, to renamed a previously
saved workspace named 'blinka_bot' to 'ruby_robot':

.. code-block:: shell

    circlink workspace rename blinka_bot ruby_robot

Other Features
--------------

You can also import and expore workspaces if needed (e.g. before resetting
``circlink``).  You can use ``circlink workspace --help`` to find those\
commands, and use ``--help`` with them to see more information.
