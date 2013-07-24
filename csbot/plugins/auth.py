from csbot.plugin import Plugin
from csbot.util import nick


class Auth(Plugin):
    def setup(self):
        super(Auth, self).setup()
        self._permissions = {}