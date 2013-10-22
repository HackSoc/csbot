from csbot.plugin import Plugin
from csbot.util import nick


class TopicException(Exception):
    pass


class Topic(Plugin):
    PLUGIN_DEPENDS = ['auth']

    CONFIG_DEFAULTS = {
        'start': '',
        'sep': '|',
        'end': '',
    }

    def setup(self):
        super(Topic, self).setup()
        self.topics = {}

    def _get_delimiters(self, channel):
        """Get the delimiters for a channel.
        """
        config = self.subconfig(channel)
        start = config.get('start', self.config_get('start'))
        sep = config.get('sep', self.config_get('sep'))
        end = config.get('end', self.config_get('end'))
        return start + ' ', ' ' + sep + ' ', ' ' + end

    @staticmethod
    def _split_topic(delim, topic):
        """Split *topic* according to *delim* (a ``(start, sep, end)`` tuple).
        """
        start, sep, end = delim
        if topic.startswith(start):
            topic = topic[len(start):]
        if topic.endswith(end):
            topic = topic[:-len(end)]
        return [s.strip() for s in topic.split(sep)]

    @staticmethod
    def _build_topic(delim, parts):
        """Join *parts* according to *delim* (a ``(start, sep, end)`` tuple).
        """
        start, sep, end = delim
        return start + sep.join(parts) + end

    def _set_topic(self, e, topic):
        if not self.bot.plugins['auth'].check_or_error(e, 'topic', e['channel']):
            return
        e.protocol.topic(e['channel'], topic)

    @Plugin.hook('core.channel.topic')
    def topic_changed(self, e):
        self.topics[e['channel']] = e['topic']

    @Plugin.command('topic', help='topic: show current topic as list of parts')
    def topic(self, e):
        topic = self.topics[e['channel']]
        delim = self._get_delimiters(e['channel'])
        parts = self._split_topic(delim, topic)
        e.protocol.msg(e['reply_to'], repr(parts))

    @Plugin.command('topic.append', help=('topic.append <text>: append an '
                                          'element to the topic'))
    def topic_append(self, e):
        delim = self._get_delimiters(e['channel'])
        parts = self._split_topic(delim, self.topics[e['channel']])
        parts.append(e['data'])
        self._set_topic(e, self._build_topic(delim, parts))

    @Plugin.command('topic.pop', help=('topic.pop [position]: remove a '
                                       '0-indexed element from the topic. '
                                       'Negative positions count from the end, '
                                       'with -1 being the last.. Default '
                                       'position is -1 if omitted.'))
    def topic_pop(self, e):
        delim = self._get_delimiters(e['channel'])
        parts = self._split_topic(delim, self.topics[e['channel']])

        if e['data']:
            # Try and use provided position, error if it's not an integer
            try:
                position = int(e['data'])
            except ValueError:
                e.protocol.msg(e['reply_to'], 'error: invalid topic position')
                return
        else:
            # Default to removing the last item
            position = -1

        # Pop the specified item, error if tho position was invalid
        try:
            parts.pop(position)
        except IndexError:
            e.protocol.msg(e['reply_to'], 'error: invalid topic position')
            return

        # Update with new topic
        self._set_topic(e, self._build_topic(delim, parts))

    @Plugin.command('topic.replace', help=('topic.replace <position> <text>: '
                                           'replace a 0-indexed element in the '
                                           'topic. Negative positions count '
                                           'from the end, with -1 being the '
                                           'last.'))
    def topic_replace(self, e):
        delim = self._get_delimiters(e['channel'])
        parts = self._split_topic(delim, self.topics[e['channel']])

        # Check number of arguments
        data_parts = e['data'].split(None, 1)
        if len(data_parts) != 2:
            e.protocol.msg(e['reply_to'], 'error: missing argument')
            return

        # Parse position number
        try:
            position = int(data_parts[0])
        except ValueError:
            e.protocol.msg(e['reply_to'], 'error: invalid topic position')
            return

        # Set topic part
        try:
            parts[position] = data_parts[1]
        except IndexError:
            e.protocol.msg(e['reply_to'], 'error: invalid topic position')
            return

        # Update with new topic
        self._set_topic(e, self._build_topic(delim, parts))