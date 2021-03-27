csbot - an IRC bot
==================
This is an IRC bot developed by members of HackSoc_ to provide various features
in the #cs-york channel (and a few others) on Freenode.

Development
-----------
csbot is written for Python 3.6+ and based on the asyncio_ library which became
part of the standard library in 3.4.

It's recommend to develop within a virtual environment.  This should get you up
and running [1]_::

    $ python3 -m venv venv3
    $ source venv3/bin/activate
    $ pip install -r requirements.txt
    $ csbot --help

Look at ``csbot.deploy.cfg`` for an example of a bot configuration.

If you want to develop features for the bot, create a uniquely named plugin (see
``csbot/plugins/`` for examples), try it out, preferably write some unit tests
(see ``csbot/test/plugins/``) and submit a pull request.

Deployment
----------
Create ``csbot.cfg``, and then use `Docker Compose`_ to build and launch the
Docker containers (a MongoDB instance and the bot)::

    $ docker-compose up

This will use the `published image`_. To build locally::

    $ docker build -t alanbriolat/csbot:latest .

Environment variables to expose to the bot, e.g. for sensitive configuration
values, should be defined in ``deploy.env``.  Environment variables used in
``docker-compose.yml`` should be defined in ``.env``:

==========================  ==================  ===========
Variable                    Default             Description
==========================  ==================  ===========
``CSBOT_CONFIG_LOCAL``      ``./csbot.cfg``     Path to config file in host filesystem to mount at ``/app/csbot.cfg``
``CSBOT_CONFIG``            ``csbot.cfg``       Path to config file in container, relative to ``/app``
``CSBOT_WATCHTOWER``        ``false``           Set to ``true`` to use Watchtower_ to auto-update when published container is updated
==========================  ==================  ===========

Backup MongoDB once services are running::

    $ docker-compose exec -T mongodb mongodump --archive --gzip --quiet > foo.mongodump.gz

Restore MongoDB::

    $ docker-compose exec -T mongodb mongorestore --archive --gzip --drop < foo.mongodump.gz

Documentation
-------------
The code is documented to varying degrees, and Sphinx-based documentation is
automatically generated on Read the Docs: http://hacksoc-csbot.readthedocs.org.
Of particular use is the "How to write plugins" section.

You can build the documentation yourself with::

    $ pip install sphinx
    $ cd docs/
    $ make html

Testing
-------
csbot has some unit tests.  (It'd be nice to have more.)  To run them::

    $ tox

We're also using GitHub Actions for continuous integration and continuous deployment.

.. image:: https://github.com/HackSoc/csbot/actions/workflows/main.yml/badge.svg

.. image:: https://codecov.io/gh/HackSoc/csbot/branch/master/graph/badge.svg?token=oMJcY9E9lj
    :target: https://codecov.io/gh/HackSoc/csbot


.. [1] csbot depends on lxml_, which is a compiled extension module based on
    libxml2 and libxslt.  Make sure you have the appropriate libraries and
    headers, e.g. ``python3-dev``, ``libxml2-dev`` and ``libxslt1-dev`` on
    Ubuntu or Debian.

.. _HackSoc: http://hacksoc.org/
.. _asyncio: https://docs.python.org/3/library/asyncio.html
.. _lxml: http://lxml.de/
.. _Docker Compose: https://docs.docker.com/compose/
.. _published image: https://hub.docker.com/r/alanbriolat/csbot
.. _Watchtower: https://containrrr.github.io/watchtower/