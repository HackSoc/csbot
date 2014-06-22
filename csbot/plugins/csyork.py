from csbot.plugin import Plugin


class CSYork(Plugin):
    """Amusing replacements for various #cs-york members"""

    @Plugin.hook('core.message.privmsg')
    def respond(self, e):
        # hayashi
        # Completes an ASCII stick man started with `\o/`.
        if e['message'].strip() == '\o/':
            spaces = e['message'].find('\\')
            e.protocol.msg(e['reply_to'], ' ' * spaces + ' |')
            e.protocol.msg(e['reply_to'], ' ' * spaces + '/ \\')
