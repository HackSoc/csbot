# Read Me #

We are developing an IRC bot and plugin system for the #cs-york channel on irc.freenode.net.

## Development ##
It's written in Python 2.7, using the PEP 8 coding style.

## Code Management & Version Control ##
The code is stored [here](http://github.com/csyork/csbot/) on github.com. Please fork it if you want to help with it.

The basic procedure for contributing is as follows

- make your changes
- fetch changes from upstream
- check the diffs to ensure nothing is broken
- merge
- check it all still works
- push it to your fork
- send a pull request to upstream.

## Testing ##

Unit testing is done with [Trial](http://twistedmatrix.com/documents/current/core/howto/trial.html), 
Twisted's extension of Python's unittest module.  If structured correctly, tests should be runnable 
with `trial csbot`.

## Further Reading ##
Please read the [Procedures page](https://github.com/csyork/csbot/wiki/Procedure) for more information. The wiki will be updated more often than this Read Me file and so should be taken as the first point of reference.
