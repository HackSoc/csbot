import pymongo

from csbot.plugin import Plugin


class MongoDB(Plugin):
    """A plugin that provides access to a MongoDB server via pymongo.
    """
    CONFIG_DEFAULTS = {
        'uri': 'mongodb://localhost:27017',
        'prefix': 'csbot__',
    }

    CONFIG_ENVVARS = {
        'uri': ['MONGOLAB_URI', 'MONGODB_URI'],
    }

    def __init__(self, *args, **kwargs):
        super(MongoDB, self).__init__(*args, **kwargs)
        self.log.info('connecting to mongodb: ' + self.config_get('uri'))
        self.connection = pymongo.Connection(self.config_get('uri'))

    def get_db(self, name):
        """Get a named database.

        A plugin depending on having access to MongoDB should firstly make sure
        it states the dependency, and secondly grab references to any databases
        it needs.  For example::

            class MyPlugin(Plugin):
                PLUGIN_DEPENDS = ['mongodb']

                @Plugin.integrate_with('mongodb')
                def _get_db(self, mongodb):
                    self.db = mongodb.get_db(self.plugin_name())
        """
        dbname = self.config_get('prefix') + name
        self.log.debug('creating database reference: ' + dbname)
        return self.connection[dbname]
