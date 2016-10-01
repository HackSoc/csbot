import last
import random
from ..plugin import Plugin

class Quote(Plugin):
    """Quote people out of context for fun and for profit.
       Add quotes, recall quotes
    """
    db = Plugin.use('mongodb', collection='quote')

    class QuoteError(Exception):
        pass

    def _quote(self, nick):
        """Find a quote by person"""
        if not nick:
            self.QuoteError("No nick!")

        #find quote by nick
        quotes = self.db.find({'nick': nick})
        quote_list = list(quotes)

        if len(quote_list) == 0:
            self.QuoteError("No quotes by", nick)

        #Randomly pick quote from returned quotes
        quote_list = list(quotes)
        quote = random.choice(quote_list)

        return (quote["text"], quote["nick"])

    def _quoteExists(self, quote_post):
        """Checks to see if a nick + quote already exists to stop repeats."""
        if self.db.find(quote_post).count > 0:
            return True
        else:
            return False

    def _addquote(self, nick=""):
        """Add quote from what person last said"""

        if not nick:
            raise self.QuoteError("No nick!")

        quote = {} #output
        quote["quote"] = last.last_message(nick)[2]

        if not quote["quote"]:
            raise self.QuoteError("No Last message from nick, or nick not found.")

        #Create post object
        post_quote = {'nick': nick, 'quote': quote["quote"]}

        #check if quote already in database
        if not _quoteExists(post_quote):
            self.db.insert_one(post_quote)
        else:
            self.QuoteError("Quote already in Database.")

        return(quote["quote"], nick)


    @Plugin.command('quote', help="quote [nick]")
    def quote(self, e):
        """quote somebody
        """
        try:
            e.reply("\"{}\" - {}".format(*self._quote(e["data"])))
        except self.QuoteError as ex:
            e.reply(str(ex))

    @Plugin.command('addquote', help="addquote <nick>")
    def addquote(self, e):
        """add a quote
        """
        try:
            e.reply("\"{}\" - {} added as quote.".format(*self._addquote(e["data"])))
        except self.QuoteError as ex:
            e.reply(str(ex))
