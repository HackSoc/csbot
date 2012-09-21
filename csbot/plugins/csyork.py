from csbot.plugin import Plugin

class CSYork(Plugin):

    def __init__(self, *args, **kwargs):
        pass

    @Plugin.hook('core.message.privmsg')
    def respond(self, e):
    
        # hayashi
        # Completes an ASCII stick man started with `\o/`.
        if e['message'].strip() == '\o/':
            spaces = e['message'].find('\\')
            e.protocol.msg(e['reply_to'], u' '*spaces + ' |')
            e.protocol.msg(e['reply_to'], u' '*spaces + '/ \\')