from collections import defaultdict

from csbot.plugin import Plugin
from csbot.util import nick


class PermissionDB(defaultdict):
    """A helper class for assembling the permissions database."""
    def __init__(self):
        super(PermissionDB, self).__init__(set)
        self._groups = defaultdict(set)
        self._current = None

    def process(self, entity, permissions):
        """Process a configuration entry, where *entity* is an account name,
        ``@group`` name or ``*`` and *permissions* is a space-separated list of
        permissions to grant.
        """
        self._current = (entity, permissions)

        if entity.startswith('@'):
            entity_perms = self._groups[entity]
        else:
            entity_perms = self[entity]

        for permission in permissions.split():
            if ':' in permission:
                self._add_channel_permissions(entity_perms, permission)
            elif permission.startswith('@'):
                self._copy_group_permissions(entity_perms, permission)
            else:
                self._add_bot_permission(entity_perms, permission)

        self._current = None

    def get_permissions(self, entity):
        return self.get(entity, set()) | self.get('*', set())

    def _add_channel_permissions(self, entity_perms, permission):
        channel, _, permissions = permission.partition(':')

        if not (channel == '*' or channel.startswith('#')):
            self._error('Invalid channel name "{}", must be * or #channel'
                        .format(channel))
        if permissions == '':
            self._error('No permissions specified for channel "{}"'
                        .format(channel))

        for p in permissions.split(','):
            entity_perms.add((channel, p))

    def _copy_group_permissions(self, entity_perms, group):
        if group not in self._groups:
            self._error('Permission group "{}" undefined'.format(group))
        entity_perms.update(self._groups[group])

    def _add_bot_permission(self, entity_perms, permission):
        entity_perms.add(permission)

    def _error(self, s, *args):
        entity, perms = self._current
        raise ValueError('{} (in: {} = {})'.format(s, entity, perms), *args)


class Auth(Plugin):
    PLUGIN_DEPENDS = ['usertrack']

    def setup(self):
        super(Auth, self).setup()

        self._permissions = PermissionDB()
        for entity, permissions in self.config.items():
            self._permissions.process(entity, permissions)

        for e, p in self._permissions.iteritems():
            self.log.debug((e, p))

    def check(self, nick, perm, channel=None):
        account = self.bot.plugins['usertrack'].get_user(nick)['account']

        if account is None:
            # People without accounts still have the universal permissions
            # if any are set
            permissions = self._permissions.get_permissions('*')
        else:
            permissions = self._permissions.get_permissions(account)

        if channel is None:
            checks = {('*', perm)}
        else:
            checks = {('*', '*'), (channel, '*'), ('*', perm), (channel, perm)}

        return len(checks & permissions) > 0