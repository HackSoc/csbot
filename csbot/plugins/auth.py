from collections import defaultdict

from csbot.plugin import Plugin
import csbot.util


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
            if entity in self._groups:
                self._error('Group "{}" already defined'.format(entity))
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
        """Get the set of permissions for *entity*.

        The union of the permissions for *entity* and the universal (``*``)
        permissions is returned.  If *entity* is ``None``, only the universal
        permissions are returned.
        """
        if entity is None:
            return set(self.get('*', set()))
        else:
            return self.get(entity, set()) | self.get('*', set())

    def check(self, entity, permission, channel=None):
        """Check if *entity* has *permission*.

        If *channel* is present, check for a channel permission, otherwise check
        for a bot permission.  Compatible wildcard permissions are also checked.
        """
        if channel is None:
            checks = {permission, '*'}
        else:
            checks = {(channel, permission), (channel, '*'),
                      ('*', permission), ('*', '*')}

        return len(checks & self.get_permissions(entity)) > 0

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
        if group == self._current[0]:
            self._error('Recursive group definition')
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

        for e, p in self._permissions.items():
            self.log.debug((e, p))

    def check(self, nick, perm, channel=None):
        account = self.bot.plugins['usertrack'].get_user(nick)['account']
        return self._permissions.check(account, perm, channel)

    def check_or_error(self, e, perm, channel=None):
        nick = csbot.util.nick(e['user'])
        account = self.bot.plugins['usertrack'].get_user(nick)['account']
        success = self._permissions.check(account, perm, channel)

        if channel is None:
            printable_perm = perm
        else:
            printable_perm = channel + ':' + perm

        if account is None:
            e.protocol.msg(e['reply_to'], 'error: not authenticated')
            return False
        elif success is False:
            e.protocol.msg(e['reply_to'], ('error: {} not authorised for {}'
                                           .format(account, printable_perm)))
            return False
        else:
            return True
