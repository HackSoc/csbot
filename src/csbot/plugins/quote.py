import re
import random
import functools
import collections

import attr
import pymongo
import requests

from csbot.plugin import Plugin
from csbot.util import nick, subdict


@attr.s
class QuoteRecord:
    quote_id = attr.ib()
    channel = attr.ib()
    nick = attr.ib()
    message = attr.ib()

    def format(self, show_channel=False, show_id=True):
        """ Formats a quote into a prettified string.

        >>> self.format()
        "[3] <Alan> some silly quote..."
        >>> self.format(show_channel=True, show_id=False)
        "#test - <Alan> silly quote"
        """
        if show_channel and show_id:
            fmt = '[{quoteId}] - {channel} - <{nick}> {message}'
        elif show_channel and not show_id:
            fmt = '{channel} - <{nick}> {message}'
        elif not show_channel and show_id:
            fmt = '[{quoteId}] <{nick}> {message}'
        else:
            fmt = '<{nick}> {message}'

        return fmt.format(quoteId=self.quote_id, channel=self.channel, nick=self.nick, message=self.message)

    def __bool__(self):
        return True

    def to_udict(self):
        return {'quoteId': self.quote_id, 'nick': self.nick, 'channel': self.channel, 'message': self.message}

    @classmethod
    def from_udict(cls, udict):
        return cls(quote_id=udict['quoteId'],
                   channel=udict['channel'],
                   nick=udict['nick'],
                   message=udict['message'],
                   )

class QuoteDB:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def quote_from_id(self, quote_id):
        """gets a quote with some `quoteId` from the database
        returns None if no such quote exists
        """
        return QuoteRecord.from_udict(self.quotedb.find_one({'quoteId': quote_id}))

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

    def insert_quote(self, quote):
        """ Remember a quote by storing it in the database

        Inserts a {'user': user, 'channel': channel, 'message': msg}
        or        {'account': accnt, 'channel': channel, 'message': msg}
        quote into the persistent storage.
        """

        id = self.get_current_quote_id()
        sId = id + 1
        quote.quote_id = sId
        self.quotedb.insert(quote.to_udict())
        self.set_current_quote_id(sId)
        return sId

    def remove_quote(self, quote_id):
        """ Remove a given quote from the database

        Returns False if the quoteId is invalid or does not exist.
        """

        try:
            id = int(quote_id)
        except ValueError:
            return False
        else:
            q = self.quote_from_id(id)
            if not q:
                return False

            self.quotedb.remove({'quoteId': q.quote_id})

        return True

    def find_quotes(self, nick=None, channel=None, pattern=None, direction=pymongo.ASCENDING):
        """ Finds and yields all quotes for a particular nick on a given channel
        """
        if nick is None or nick == '*':
            user = {'channel': channel}
        elif channel is not None:
            user = {'channel': channel, 'nick': nick}
        else:
            user = {'nick': nick}

        for quote in self.quotedb.find(user, sort=[('quoteId', direction)]):
            if message_matches(quote['message'], pattern=pattern):
                yield QuoteRecord.from_udict(quote)


class Quote(Plugin, QuoteDB):
    """Attach channel specific quotes to a user
    """
    quotedb = Plugin.use('mongodb', collection='quotedb')

    PLUGIN_DEPENDS = ['usertrack', 'auth']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channel_logs = collections.defaultdict(functools.partial(collections.deque, maxlen=100))

    def quote_set(self, nick, channel, pattern=None):
        """ Insert the last matching quote from a user on a particular channel into the quotes database.
        """
        for q in self.channel_logs[channel]:
            if nick == q.nick and channel == q.channel and message_matches(q.message, pattern=pattern):
                self.insert_quote(q)
                return q
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
            return self.remember_quote(e, user_nick, m.group('nick'), channel, None)

        m = re.fullmatch(r'(?P<nick>\S+)\s+(?P<pattern>.+)', data)
        if m:
            return self.remember_quote(e, user_nick, m.group('nick'), channel, m.group('pattern').strip())

        e.reply('Error: invalid command')

    def remember_quote(self, e, user, nick, channel, pattern):
        quote = self.quote_set(nick, channel, pattern)
        if quote is None:
            if pattern is not None:
                e.reply(f'No data for {nick} found matching "{pattern}"')
            else:
                e.reply( f'No data for {nick}')
        else:
            self.bot.reply(user, 'remembered "{}"'.format(quote.format(show_id=False)))

    @Plugin.command('quote', help=("quote [<nick> [<pattern>]]: looks up quotes from <nick>"
                                   " (optionally only those matching <pattern>)"))
    def quote(self, e):
        """ Lookup quotes for the given channel/nick and outputs one
        """
        data = e['data']
        channel = e['channel']

        if data.strip() == '':
            return e.reply(self.find_a_quote(None, channel, None))

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
            if nick is None:
                return 'No data'
            else:
                return 'No data for {}'.format(nick)
        else:
            out = random.choice(res)
            return out.format(show_channel=False)

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
        quotes = list(self.find_quotes(nick=None, channel=channel, pattern=pattern, direction=pymongo.DESCENDING))
        if not quotes:
            if pattern:
                yield 'No quotes for channel {} that match "{}"'.format(channel, pattern)
            else:
                yield 'No quotes for channel {}'.format(channel)

            return

        for q in quotes[:5]:
            yield q.format(show_channel=True)

        if dpaste and len(quotes) > 5:
            paste_link = self.paste_quotes(quotes)
            if paste_link:
                yield 'Full summary at: {}'.format(paste_link)
            else:
                self.log.warn(f'Failed to upload full summary: {paste_link}')

    def paste_quotes(self, quotes):
        """ Pastebins a the last 100 quotes and returns the url
        """
        paste_content = '\n'.join(q.format(show_channel=True) for q in quotes[:100])
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
                try:
                    q = next(self.find_quotes(nick=None, channel=channel, pattern=None, direction=pymongo.DESCENDING))
                except StopIteration:
                    invalid_ids.append(id)
                    continue

                id = q.quote_id

            if not self.remove_quote(id):
                invalid_ids.append(id)

        if invalid_ids:
            str_invalid_ids = ', '.join(str(id) for id in invalid_ids)
            return e.reply('Error: could not remove quote(s) with ID: {ids}'.format(ids=str_invalid_ids))

    @Plugin.hook('core.message.privmsg')
    def log_privmsgs(self, e):
        """Register privmsgs for a channel and stick them into the log for that channel
        this is merely an in-memory deque, so won't survive across restarts/crashes
        """
        msg = e['message']

        channel = e['channel']
        user = nick(e['user'])
        quote = QuoteRecord(None, channel, user, msg)
        self.channel_logs[channel].appendleft(quote)

def message_matches(msg, pattern=None):
    """ Check whether the given message matches the given pattern

    If there is no pattern, it is treated as a wildcard and all messages match.
    """
    if pattern is None:
        return True

    return re.search(pattern, msg) is not None