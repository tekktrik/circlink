Customizing Your Experience
===========================

Configuration Settings
----------------------

``circlink`` provides a few options for configuring your experience.
You can change this settings using the ``config`` command:

.. code-block:: shell

    circlink config [COMMAND]

Viewing Settings
----------------

You can view your current configurations settings using the ``view``
subcommand:

.. code-block:: shell

    circlink config view

This will show all of your current configuration settings.  If you want
to only see specific settings, you can also provide a dot-spearated
argument.  For example, to see just whether you are showing the process
ID in tables, you can use:

.. code-block:: shell

    circlink config view display.info.process-id

Editing Settings
----------------

You can use the ``edit`` subcommand to change any of the configuration
settings, using dot-spearated paths.  For example, to turn on showing
process IDs in tables:

.. code-block:: shell

    circlink config edit display.info.process-id true

Settings File
-------------

You can see where the settings file is stored to view and modify settings
natively as well:

.. code-block:: shell

    circlink config --filepath

Available Settings
------------------

.. csv-table:: Settings List
    :file: configlist.csv
    :header-rows: 1
