from csbot.plugin import Plugin
from datetime import datetime, timedelta


class Cal(Plugin):
    """
    A wonderful plugin allowing old people (graduates) to keep track of the
    ever-changing calendar.
    """

    DATE_FORMAT = '%Y-%m-%d'

    def setup(self):
        super(Cal, self).setup()

        # If no term dates have been set, the calendar is uninitialised and
        # can't be asked about term things.
        self.initialised = False

        # Each term is represented as a tuple of the date of the first Monday
        # and the last Friday in it.
        self.terms = {term: (None, None)
                      for term in ['aut', 'spr', 'sum']}

        # And each week is just the date of the Monday
        self.weeks = {'{} {}'.format(term, week): None
                      for term in ['aut', 'spr', 'sum']
                      for week in range(1, 11)}

    @Plugin.command('termdates', help='termdates: show the current term dates')
    def termdates(self, e):
        if not self.initialised:
            e.protocol.msg(e['reply_to'],
                           'error: no term dates (see termdates.set)')
        else:
            e.protocol.msg(e['reply_to'],
                           'Aut {} -- {}, Spr {} -- {}, Sum {} -- {}'.format(
                               self._term_start('aut'), self._term_end('aut'),
                               self._term_start('spr'), self._term_end('spr'),
                               self._term_start('sum'), self._term_end('sum')))

    def _term_start(self, term):
        """
        Get the start date (first Monday) of a term as a string.
        """

        return self.terms[term][0].strftime(self.DATE_FORMAT)

    def _term_end(self, term):
        """
        Get the end date (last Friday) of a term as a string.
        """

        return self.terms[term][1].strftime(self.DATE_FORMAT)

    @Plugin.command('termdates.set', help='termdates.set: set the term dates')
    def termdates_set(self, e):
        dates = e['data'].split()

        if len(dates) < 3:
            e.protocol.msg(e['reply_to'],
                           'error: all three dates must be provided')
            return

        # Firstly compute the start and end dates of each term
        for term, date in zip(['aut', 'spr', 'sum'], dates):
            try:
                term_start = datetime.strptime(date, self.DATE_FORMAT)
            except ValueError:
                e.protocol.msg(e['reply_to'],
                               'error: dates must be in %Y-%M-%d format.')
                return

            term_end = term_start + timedelta(days=4, weeks=9)
            self.terms[term] = (term_start, term_end)

            # Then the start of each week
            for week in range(1, 11):
                week_start = term_start + timedelta(weeks=week-1)
                self.weeks['{} {}'.format(term, week)] = week_start

        # Finally, we're initialised!
        self.initialised = True
