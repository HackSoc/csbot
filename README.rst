csbot - an IRC bot
==================
This is an IRC bot developed by members of HackSoc_ to provide various features
in the #cs-york channel on Freenode.

Development
-----------
csbot is written for Python 3.4 and based on the asyncio_ library which became
part of the Python standard library in 3.4.  It *may* also work on Python 3.3
with the asyncio package installed, but this is currently untested.

It's recommend to develop within a virtual environment.  This should get you up
and running [1]_::

    $ virtualenv -p python3 venv3
    $ source venv3/bin/activate
    $ pip install -r requirements.txt
    $ ./run_csbot.py --help

Look at ``csbot.deploy.cfg`` for an example of a bot configuration.

If you want to develop features for the bot, create a uniquely named plugin (see
``csbot/plugins/`` for examples), try it out, preferably write some unit tests
(see ``csbot/test/plugins/``) and submit a pull request.

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

    $ ./run_tests.py

We're also using Travis-CI for continuous integration and continuous deployment.

.. image:: https://travis-ci.org/HackSoc/csbot.svg?branch=master
    :target: https://travis-ci.org/HackSoc/csbot

.. image:: https://coveralls.io/repos/HackSoc/csbot/badge.png
    :target: https://coveralls.io/r/HackSoc/csbot


.. [1] csbot depends on lxml_, which is a compiled extension module based on
    libxml2 and libxslt.  Make sure you have the appropriate libraries and
    headers, e.g. ``python3-dev``, ``libxml2-dev`` and ``libxslt1-dev`` on
    Ubuntu or Debian.

.. _HackSoc: http://hacksoc.org/
.. _asyncio: https://docs.python.org/3/library/asyncio.html
.. _lxml: http://lxml.de/
