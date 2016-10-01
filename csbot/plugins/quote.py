import json
import last
from ..plugin import Plugin

class Quote(Plugin):
    """Quote people out of context for fun and for profit.
       Add quotes, recall quotes
    """
    class QuoteError(Exception):
        pass

    def _quote(self, in_quote_num=None):
        quote = {}
        if in_quote_num == None:
            raise self.QuoteError("No quote number passed.")
        #check format of quote_numb
        quote["ID"] = 0
        try:
            quote["ID"] = int(in_quote_num)
        except:
            raise self.QuoteError("Quote number passed not integer.")

        #open the quotes file, and read the quote
        quotes = {}
        try:
            with open("quotes.json","r") as q_file:
                try:
                    quotes = json.loads(q_file.read())
                except:
                    raise self.QuoteError("Quotes JSON file format error.")
        except:
            raise self.QuoteError("Quote file doesn't exist yo.")

        #get quote
        quote["text"] = ""
        try:
            quote["text"] = quotes[str(in_quote_num)]
        except:
            return (quote["ID"], "NOT FOUND")

        return (quote["ID"], quote["text"])

    def _addquote(self, in_quote_text=""):
        if in_quote_text == "":
            raise self.QuoteError("Empty quote!")
        quote = {} #output

        #open up quotes file
        quotes = {}
        try:
            with open("quotes.json","r") as q_file:
                quotes = json.loads(q_file.read())
        except:
            #quote file doesn't exist
            quotes = {"quote_count": 1, '0': "Test quote please ignore."}

        #read the last key used, , this becomes the quote id, add one to it
        num_of_quotes = 0
        try:
            num_of_quotes = quotes["quote_count"]
        except:
            raise self.QuoteError("Can't find quote count in quote dictionary.")
        quotes[num_of_quotes] = in_quote_text
        quote["ID"] = num_of_quotes
        quotes["quote_count"] = num_of_quotes + 1

        #write quote file back
        try:
            with open("quotes.json","w+") as q_file:
                q_file.write(json.dumps(quotes))
        except:
            raise self.QuoteError("Unable to write quote file back")

        quote["text"] = in_quote_text

        return(quote["text"], quote["ID"])


    @Plugin.command('quote', help="quote <ID>")
    def quote(self, e):
        """quote somebody
        """
        try:
            e.reply("#{}: {}".format(*self._quote(e["data"])))
        except self.QuoteError as ex:
            e.reply(str(ex))

    @Plugin.command('addquote', help="addquote <quote>")
    def addquote(self, e):
        """add a quote
        """
        try:
            e.reply("\"{}\" added as quote #{}.".format(*self._addquote(e["data"])))
        except self.QuoteError as ex:
            e.reply(str(ex))
