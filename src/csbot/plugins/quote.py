import re
import functools
import collections

import pymongo
import requests

from csbot.plugin import Plugin
from csbot.util import nick, subdict

class Quote(Plugin):
    """Attach channel specific quotes to a user
    """

    PLUGIN_DEPENDS = ['usertrack']

    quotedb = Plugin.use('mongodb', collection='quotedb')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channel_logs = collections.defaultdict(functools.partial(collections.deque, maxlen=100))

    def quote_from_id(self, quoteId):
        """gets a quote with some `quoteId` from the database
        returns None if no such quote exists
        """
        return self.quotedb.find_one({'quoteId': quoteId})

    def format_quote(self, q):
        current = self.get_current_quote_id()
        len_current = len(str(current))
        quoteId = str(q['quoteId']).ljust(len_current)
        return '{quoteId} - {channel} - <{nick}> {message}'.format(quoteId=quoteId,
                                                                   channel=q['channel'],
                                                                   nick=q['nick'],
                                                                   message=q['message'])

    def paste_quotes(self, quotes):
        if len(quotes) > 5:
            paste_content = '\n'.join(self.format_quote(q) for q in quotes)
            req = requests.post('http://dpaste.com/api/v2/', {'content': paste_content})
            if req:
                return req.content.decode('utf-8').strip()

    def set_current_quote_id(self, id):
        """sets the last quote id
        """
        self.quotedb.remove({'header': 'currentQuoteId'})
        self.quotedb.insert({'header': 'currentQuoteId', 'maxQuoteId': id})

    def get_current_quote_id(self):
        """gets the current maximum quote id
        """
        id_dict = self.quotedb.find_one({'header': 'currentQuoteId'})
        if id_dict is not None:
            current_id = id_dict['maxQuoteId']
        else:
            current_id = -1

        return current_id

    def insert_quote(self, udict):
        """inserts a {'user': user, 'channel': channel, 'message': msg}
           or        {'account': accnt, 'channel': channel, 'message': msg}
        quote into the database
        """

        id = self.get_current_quote_id()
        sId = id + 1
        udict['quoteId'] = sId
        self.quotedb.insert(udict)
        self.set_current_quote_id(sId)
        return sId

    def message_matches(self, msg, pattern=None):
        """returns True if `msg` matches `pattern`
        """
        if pattern is None:
            return True

        return re.search(pattern, msg) is not None

    def quote_set(self, nick, channel, pattern=None):
        """writes the last quote that matches `pattern` to the database
        and returns its id
        returns None if no match found
        """
        user = self.identify_user(nick, channel)

        for udict in self.channel_logs[channel]:
            if subdict(user, udict):
                if self.message_matches(udict['message'], pattern=pattern):
                    return self.insert_quote(udict)

        return None

    def find_quotes(self, nick, channel, pattern=None):
        """finds and yields all quotes from nick
        on channel `channel` (optionally matching on `pattern`)
        """
        user = self.identify_user(nick, channel)
        for quote in self.quotedb.find(user, sort=[('quoteId', pymongo.ASCENDING)]):
            if self.message_matches(quote['message'], pattern=pattern):
                yield quote

    def quote_summary(self, channel, pattern=None, dpaste=True):
        quotes = list(self.quotedb.find({'channel': channel}, sort=[('quoteId', pymongo.ASCENDING)]))
        if not quotes:
            if pattern:
                yield 'Cannot find quotes for channel {} that match "{}"'.format(channel, pattern)
            else:
                yield 'Cannot find quotes for channel {}'.format(channel)

            return

        for q in quotes[:5]:
            yield self.format_quote(q)

        if dpaste:
            paste_link = self.paste_quotes(quotes)
            if paste_link:
                yield 'Full summary at: {}'.format(paste_link)

    @Plugin.command('quote', help=("quote <nick> [<pattern>]: adds last quote that matches <pattern> to the database"))
    def quote(self, e):
        """Lookup the nick given
        """
        data = e['data'].split(maxsplit=1)

        if len(data) < 1:
            return e.reply('Expected more arguments, see !help quote')

        nick_ = data[0].strip()

        if len(data) == 1:
            pattern = ''
        else:
            pattern = data[1].strip()

        res = self.quote_set(nick_, e['channel'], pattern)

        if res is None:
            if pattern:
                e.reply('Found no messages from {} found matching "{}"'.format(nick_, pattern))
            else:
                e.reply('Unknown nick {}'.format(nick_))

    @Plugin.command('quotes', help=("quote <nick> [<pattern>]: looks up quotes from <nick>"
                                    " (optionally only those matching <pattern>)"))
    def quotes(self, e):
        """Lookup the nick given
        """
        data = e['data'].split(maxsplit=1)
        channel = e['channel']

        if len(data) < 1:
            return e.reply('Expected arguments, see !help quote')

        nick_ = data[0].strip()

        if len(data) == 1:
            pattern = ''
        else:
            pattern = data[1].strip()

        res = self.find_quotes(nick_, channel, pattern)
        out = next(res, None)
        if out is None:
            e.reply('No quotes recorded for {}'.format(nick_))
        else:
            e.reply('<{}> {}'.format(out['nick'], out['message']))


    @Plugin.command('quotes.list', help=("quotes.list [<pattern>]: looks up all quotes on the channel"))
    def quoteslist(self, e):
        """Lookup the nick given
        """
        channel = e['channel']
        nick_ = nick(e['user'])

        if nick_ == channel:
            # first argument must be a channel
            data = e['data'].split(maxsplit=1)
            if len(data) < 1:
                return e.reply('Expected at least <channel> argument in PRIVMSGs, see !help quotes.list')

            quote_channel = data[0]

            if len(data) == 1:
                pattern = None
            else:
                pattern = data[1]

            for line in self.quote_summary(quote_channel, pattern=pattern):
                e.reply(line)
        else:
            pattern = e['data']

            for line in self.quote_summary(channel, pattern=pattern):
                self.bot.reply(nick_, line)

    @Plugin.command('quotes.remove', help=("quotes.remove <id> [, <id>]*: removes quotes from the database"))
    def quotes_remove(self, e):
        """Lookup the given quotes and remove them from the database transcationally
        """
        data = e['data'].split(',')
        channel = e['channel']

        if len(data) < 1:
            return e.reply('Expected at least 1 quoteID to remove.')

        ids = [qId.strip() for qId in data]
        invalid_ids = []
        quotes = []
        for id in ids:
            if id == '-1':
                # special case -1, to be the last
                _id = self.quotedb.find_one({'channel': channel}, sort=[('quoteId', pymongo.DESCENDING)])
                if _id:
                    id = _id['quoteId']

            try:
                id = int(id)
            except ValueError:
                invalid_ids.append(id)
            else:
                q = self.quote_from_id(id)
                if q:
                    quotes.append(q)
                else:
                    invalid_ids.append(id)

        if invalid_ids:
            str_invalid_ids = ', '.join(str(id) for id in invalid_ids)
            return e.reply('Cannot find quotes with ids {ids} (request aborted)'.format(ids=str_invalid_ids))
        else:
            for q in quotes:
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
