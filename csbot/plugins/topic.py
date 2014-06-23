from collections import defaultdict, deque

from csbot.plugin import Plugin


class Topic(Plugin):
    PLUGIN_DEPENDS = ['auth']

    CONFIG_DEFAULTS = {
        'history': 5,
        'start': '',
        'sep': '|',
        'end': '',
    }

    def setup(self):
        super(Topic, self).setup()
        self.topics = defaultdict(deque)

    def config_get(self, key, channel=None):
        """A special implementation of :meth:`Plugin.config_get` which looks at
        a channel-based configuration subsection before the plugin's
        configuration section.
        """
        default = super(Topic, self).config_get(key)

        if channel is None:
            return default
        else:
            return self.subconfig(channel).get(key, default)

    def _get_delimiters(self, channel):
        """Get the delimiters for a channel.
        """
        # Start of topic, with a space for padding
        start = self.config_get('start', channel)
        if len(start) > 0:
            start = start + ' '

        # Topic element separator, with spaces for padding
        sep = ' ' + self.config_get('sep', channel) + ' '

        # End of topic, with a space for padding
        end = self.config_get('end', channel)
        if len(end) > 0:
            end = ' ' + end

        return start, sep, end

    @staticmethod
    def _split_topic(delim, topic):
        """Split *topic* according to *delim* (a ``(start, sep, end)`` tuple).
        """
        start, sep, end = delim
        if len(start) > 0 and topic.startswith(start):
            topic = topic[len(start):]
        if len(end) > 0 and topic.endswith(end):
            topic = topic[:-len(end)]
        return [s.strip() for s in topic.split(sep)]

    @staticmethod
    def _build_topic(delim, parts):
        """Join *parts* according to *delim* (a ``(start, sep, end)`` tuple).
        """
        start, sep, end = delim
        return start + sep.join(parts) + end

    def _get_topic(self, channel):
        """Get the most recent topic for *channel*.
        """
        return self.topics[channel][-1]

    def _set_topic(self, e, topic):
        if not self.bot.plugins['auth'].check_or_error(e, 'topic', e['channel']):
            return False
        e.protocol.set_topic(e['channel'], topic)
        return True

    @Plugin.hook('core.channel.topic')
    def topic_changed(self, e):
        topics = self.topics[e['channel']]
        if len(topics) == 0 or e['topic'] != topics[-1]:
            topics.append(e['topic'])
        if len(topics) > int(self.config_get('history', e['channel'])):
            topics.popleft()

    @Plugin.command('topic', help='topic: show current topic as list of parts')
    def topic(self, e):
        topic = self._get_topic(e['channel'])
        delim = self._get_delimiters(e['channel'])
        parts = self._split_topic(delim, topic)
        e.protocol.msg(e['reply_to'], repr(parts))

    @Plugin.command('topic.history', help='topic.history: show recent topics')
    def topic_history(self, e):
        e.protocol.msg(e['reply_to'], repr(list(self.topics[e['channel']])))

    @Plugin.command('topic.undo', help=('topic.undo: revert to previous topic '
                                        'see topic.history)'))
    def topic_undo(self, e):
        topics = self.topics[e['channel']]

        if len(topics) < 2:
            e.protocol.msg(e['reply_to'], 'error: no history to revert to')
            return

        # Attempt to set the topic, and if it was allowed, drop the most recent
        if self._set_topic(e, topics[-2]):
            topics.pop()

    @Plugin.command('topic.append', help=('topic.append <text>: append an '
                                          'element to the topic'))
    @Plugin.command('topic.push', help=('topic.push <text>: alias '
                                        'of topic.append'))
    def topic_append(self, e):
        delim = self._get_delimiters(e['channel'])
        parts = self._split_topic(delim, self._get_topic(e['channel']))
        parts.append(e['data'])
        self._set_topic(e, self._build_topic(delim, parts))

    @Plugin.command('topic.pop', help=('topic.pop [position]: remove a '
                                       '0-indexed element from the topic. '
                                       'Negative positions count from the end, '
                                       'with -1 being the last.. Default '
                                       'position is -1 if omitted.'))
    def topic_pop(self, e):
        delim = self._get_delimiters(e['channel'])
        parts = self._split_topic(delim, self._get_topic(e['channel']))

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
        parts = self._split_topic(delim, self._get_topic(e['channel']))

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

    @Plugin.command('topic.insert', help=('topic.insert <position> <text>: '
                                          'insert an element at a 0-indexed '
                                          'position in the title.  Negative '
                                          'positions count from the end'))
    def topic_insert(self, e):
        delim = self._get_delimiters(e['channel'])
        parts = self._split_topic(delim, self._get_topic(e['channel']))

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

        # Insert topic part
        try:
            parts.insert(position, data_parts[1])
        except IndexError:
            e.protocol.msg(e['reply_to'], 'error: invalid topic position')
            return

        # Update with new topic
        self._set_topic(e, self._build_topic(delim, parts))
