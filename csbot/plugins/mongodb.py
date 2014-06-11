import pymongo

from csbot.plugin import Plugin


class MongoDB(Plugin):
    """A plugin that provides access to a MongoDB server via pymongo.
    """
    CONFIG_DEFAULTS = {
        'uri': 'mongodb://localhost:27017/csbot',
    }

    CONFIG_ENVVARS = {
        'uri': ['MONGOLAB_URI', 'MONGODB_URI'],
    }

    def __init__(self, *args, **kwargs):
        super(MongoDB, self).__init__(*args, **kwargs)
        self.log.info('connecting to mongodb: ' + self.config_get('uri'))
        self.client = pymongo.MongoClient(self.config_get('uri'))
        self.db = self.client.get_default_database()

    def provide(self, plugin_name, collection):
        """Get a MongoDB collection for ``{plugin_name}__{collection}``."""
        return self.db['{}__{}'.format(plugin_name, collection)]
