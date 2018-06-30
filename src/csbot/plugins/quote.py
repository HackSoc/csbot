import re
import random
import functools
import collections

import pymongo
import requests

from csbot.plugin import Plugin
from csbot.util import nick, subdict

class Quote(Plugin):
    """Attach channel specific quotes to a user
    """

    PLUGIN_DEPENDS = ['usertrack', 'auth']

    quotedb = Plugin.use('mongodb', collection='quotedb')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channel_logs = collections.defaultdict(functools.partial(collections.deque, maxlen=100))

    def quote_from_id(self, quoteId):
        """gets a quote with some `quoteId` from the database
        returns None if no such quote exists
        """
        return self.quotedb.find_one({'quoteId': quoteId})

    def format_quote_id(self, quote_id, pad=False):
        """Formats the quote_id as a string.

        Can ask for a long-form version, which pads and aligns, or a short version:

        >>> self.format_quote_id(3)
        '3'
        >>> self.format_quote_id(23, pad=True)
        '23   '
        """

        if not pad:
            return str(quote_id)
        else:
            current = self.get_current_quote_id()

            if current == -1:  # quote_id is the first quote
                return str(quote_id)

            length = len(str(current))
            return '{:<{length}}'.format(quote_id, length=length)

    def format_quote(self, q, show_channel=False, show_id=True):
        """ Formats a quote into a prettified string.

        >>> self.format_quote({'quoteId': 3})
        "[3] <Alan> some silly quote..."
        >>> self.format_quote({'quoteId': 3}, show_channel=True, show_id=False)
        "[1  ] - #test - <Alan> silly quote"
        """
        quote_id_fmt = self.format_quote_id(q['quoteId'], pad=show_channel)

        if show_channel and show_id:
            fmt = '[{quoteId}] - {channel} - <{nick}> {message}'
        elif show_channel and not show_id:
            fmt = '{channel} - <{nick}> {message}'
        elif not show_channel and show_id:
            fmt = '[{quoteId}] <{nick}> {message}'
        else:
            fmt = '<{nick}> {message}'

        return fmt.format(quoteId=quote_id_fmt, channel=q['channel'], nick=q['nick'], message=q['message'])

    def set_current_quote_id(self, id):
        """ Sets the last quote id

        We keep track of the latest quote ID (they're sequential) in the database
        To update it we remove the old one and insert a new record.
        """
        self.quotedb.remove({'header': 'currentQuoteId'})
        self.quotedb.insert({'header': 'currentQuoteId', 'maxQuoteId': id})

    def get_current_quote_id(self):
        """ Gets the current maximum quote ID
        """
        id_dict = self.quotedb.find_one({'header': 'currentQuoteId'})
        if id_dict is not None:
            current_id = id_dict['maxQuoteId']
        else:
            current_id = -1

        return current_id

    def insert_quote(self, udict):
        """ Remember a quote by storing it in the database

        Inserts a {'user': user, 'channel': channel, 'message': msg}
        or        {'account': accnt, 'channel': channel, 'message': msg}
        quote into the persistent storage.
        """

        id = self.get_current_quote_id()
        sId = id + 1
        udict['quoteId'] = sId
        self.quotedb.insert(udict)
        self.set_current_quote_id(sId)
        return sId

    def message_matches(self, msg, pattern=None):
        """ Check whether the given message matches the given pattern

        If there is no pattern, it is treated as a wildcard and all messages match.
        """
        if pattern is None:
            return True

        return re.search(pattern, msg) is not None

    def quote_set(self, nick, channel, pattern=None):
        """ Insert the last matching quote from a user on a particular channel into the quotes database.
        """
        user = self.identify_user(nick, channel)

        for udict in self.channel_logs[channel]:
            if subdict(user, udict):
                if self.message_matches(udict['message'], pattern=pattern):
                    self.insert_quote(udict)
                    return udict

        return None

    @Plugin.command('remember', help=("remember <nick> [<pattern>]: adds last quote that matches <pattern> to the database"))
    def remember(self, e):
        """ Remembers the last matching quote from a user
        """
        data = e['data'].strip()
        channel = e['channel']
        user_nick = nick(e['user'])

        m = re.fullmatch(r'(?P<nick>\S+)', data)
        if m:
            print('fullmatch nick!')
            return self.remember_quote(e, user_nick, m.group('nick'), channel, None)

        m = re.fullmatch(r'(?P<nick>\S+)\s+(?P<pattern>.+)', data)
        if m:
            print('fullmatch pat')
            return self.remember_quote(e, user_nick, m.group('nick'), channel, m.group('pattern').strip())

        e.reply('Invalid nick or pattern')

    def remember_quote(self, e, user, nick, channel, pattern):
        res = self.quote_set(nick, channel, pattern)
        if res is None:
            if pattern is not None:
                e.reply(f'No data for {nick} found matching "{pattern}"')
            else:
                e.reply( f'No data for {nick}')
        else:
            self.bot.reply(user, 'remembered "{}"'.format(self.format_quote(res, show_id=False)))

    @Plugin.command('quote', help=("quote [<nick> [<pattern>]]: looks up quotes from <nick>"
                                   " (optionally only those matching <pattern>)"))
    def quote(self, e):
        """ Lookup quotes for the given channel/nick and outputs one
        """
        data = e['data']
        channel = e['channel']

        if data.strip() == '':
            return e.reply(self.find_a_quote('*', channel, None))

        m = re.fullmatch(r'(?P<nick>\S+)', data)
        if m:
            return e.reply(self.find_a_quote(m.group('nick'), channel, None))

        m = re.fullmatch(r'(?P<nick>\S+)\s+(?P<pattern>.+)', data)
        if m:
            return e.reply(self.find_a_quote(m.group('nick'), channel, m.group('pattern')))

    def find_a_quote(self, nick, channel, pattern):
        """ Finds a random matching quote from a user on a specific channel

        Returns the formatted quote string
        """
        res = list(self.find_quotes(nick, channel, pattern))
        if not res:
            if nick == '*':
                return 'No data'
            else:
                return 'No data for {}'.format(nick)
        else:
            out = random.choice(res)
            return self.format_quote(out, show_channel=False)

    def find_quotes(self, nick, channel, pattern=None):
        """ Finds and yields all quotes for a particular nick on a given channel
        """
        if nick == '*':
            user = {'channel': channel}
        else:
            user = self.identify_user(nick, channel)

        for quote in self.quotedb.find(user, sort=[('quoteId', pymongo.ASCENDING)]):
            if self.message_matches(quote['message'], pattern=pattern):
                yield quote

    @Plugin.command('quote.list', help=("quote.list [<pattern>]: looks up all quotes on the channel"))
    def quote_list(self, e):
        """ Look for all quotes that match a given pattern in a channel

        This action pastes multiple lines and so needs authorization.
        """
        channel = e['channel']
        nick_ = nick(e['user'])

        if not self.bot.plugins['auth'].check_or_error(e, 'quote', channel):
            return

        if channel == self.bot.nick:
            # first argument must be a channel
            data = e['data'].split(maxsplit=1)

            # TODO: use assignment expressions here when they come out
            # https://www.python.org/dev/peps/pep-0572/
            just_channel = re.fullmatch(r'(?P<channel>\S+)', data)
            channel_and_pat = re.fullmatch(r'(?P<channel>\S+)\s+(?P<pattern>.+)', data)
            if just_channel:
                return self.reply_with_summary(nick_, just_channel.group('channel'), None)
            elif channel_and_pat:
                return self.reply_with_summary(nick_, channel_and_pat.group('channel'), channel_and_pat.group('pattern'))

            return e.reply('Invalid command. Syntax in privmsg is !quote.list <channel> [<pattern>]')
        else:
            pattern = e['data']
            return self.reply_with_summary(nick_, channel, pattern)

    def reply_with_summary(self, to, channel, pattern):
        """ Helper to list all quotes for a summary paste.
        """
        for line in self.quote_summary(channel, pattern=pattern):
            self.bot.reply(to, line)

    def quote_summary(self, channel, pattern=None, dpaste=True):
        """ Search through all quotes for a channel and optionally paste a list of them

        Returns the last 5 matching quotes only, the remainder are added to a pastebin.
        """
        quotes = list(self.quotedb.find({'channel': channel}, sort=[('quoteId', pymongo.DESCENDING)]))
        if not quotes:
            if pattern:
                yield 'No quotes for channel {} that match "{}"'.format(channel, pattern)
            else:
                yield 'No quotes for channel {}'.format(channel)

            return

        for q in quotes[:5]:
            yield self.format_quote(q, show_channel=True)

        if dpaste and len(quotes) > 5:
            paste_link = self.paste_quotes(quotes)
            if paste_link:
                yield 'Full summary at: {}'.format(paste_link)
            else:
                self.log.warn(f'Failed to upload full summary: {paste_link}')

    def paste_quotes(self, quotes):
        """ Pastebins a the last 100 quotes and returns the url
        """
        paste_content = '\n'.join(self.format_quote(q, show_channel=True) for q in quotes[:100])
        if len(quotes) > 100:
            paste_content = 'Latest 100 quotes:\n' + paste_content

        req = requests.post('http://dpaste.com/api/v2/', {'content': paste_content})
        if req:
            return req.content.decode('utf-8').strip()

        return req  # return the failed request to handle error later

    @Plugin.command('quote.remove', help=("quote.remove <id> [, <id>]*: removes quotes from the database"))
    def quotes_remove(self, e):
        """Lookup the given quotes and remove them from the database transcationally
        """
        data = e['data'].split(',')
        channel = e['channel']

        if not self.bot.plugins['auth'].check_or_error(e, 'quote', e['channel']):
            return

        if len(data) < 1:
            return e.reply('No quoteID supplied')

        ids = [qId.strip() for qId in data]
        invalid_ids = []
        for id in ids:
            if id == '-1':
                # special case -1, to be the last
                _id = self.quotedb.find_one({'channel': channel}, sort=[('quoteId', pymongo.DESCENDING)])
                if _id:
                    id = _id['quoteId']

            if not self.remove_quote(id):
                invalid_ids.append(id)

        if invalid_ids:
            str_invalid_ids = ', '.join(str(id) for id in invalid_ids)
            return e.reply('Could not remove quotes with IDs: {ids} (error: quote does not exist)'.format(ids=str_invalid_ids))

    def remove_quote(self, quoteId):
        """ Remove a given quote from the database

        Returns False if the quoteId is invalid or does not exist.
        """

        try:
            id = int(quoteId)
        except ValueError:
            return False
        else:
            q = self.quote_from_id(id)
            if not q:
                return False

            self.quotedb.remove(q)

    @Plugin.hook('core.message.privmsg')
    def log_privmsgs(self, e):
        """Register privmsgs for a channel and stick them into the log for that channel
        this is merely an in-memory deque, so won't survive across restarts/crashes
        """
        msg = e['message']

        channel = e['channel']
        user = nick(e['user'])
        ident = self.identify_user(user, channel)
        ident['message'] = msg
        ident['nick'] = user  # even for auth'd user, save their nick
        self.channel_logs[channel].appendleft(ident)

    def identify_user(self, nick, channel):
        """Identify a user: by account if authed, if not, by nick. Produces a dict
        suitable for throwing at mongo."""

        user = self.bot.plugins['usertrack'].get_user(nick)

        if user['account'] is not None:
            return {'account': user['account'],
                    'channel': channel}
        else:
            return {'nick': nick,
                    'channel': channel}
