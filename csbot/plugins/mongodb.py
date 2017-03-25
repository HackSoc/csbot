import pymongo
import mongomock

from csbot.plugin import Plugin


class MongoDB(Plugin):
    """A plugin that provides access to a MongoDB server via pymongo.
    """
    CONFIG_DEFAULTS = {
        'uri': 'mongodb://localhost:27017/csbot',
        'mode': 'uri',
    }

    CONFIG_ENVVARS = {
        'uri': ['MONGOLAB_URI', 'MONGODB_URI'],
    }

    def __init__(self, *args, **kwargs):
        super(MongoDB, self).__init__(*args, **kwargs)
        self.log.info('connecting to mongodb: ' + self.config_get('uri'))

        if self.config_get('mode') == 'uri':
            self.client = pymongo.MongoClient(self.config_get('uri'))
            self.db = self.client.get_default_database()
        elif self.config_get('mode') == 'mock':
            self.log.info('using mock instead')
            self.client = mongomock.MongoClient()
            self.db = self.client.db
        else:
            raise ValueError('Expected a mode of either "uri" or "mock"')

    def provide(self, plugin_name, collection):
        """Get a MongoDB collection for ``{plugin_name}__{collection}``."""
        return self.db['{}__{}'.format(plugin_name, collection)]