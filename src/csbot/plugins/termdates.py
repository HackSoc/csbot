from csbot.plugin import Plugin
from datetime import datetime, timedelta
import math

from ..util import ordinal


class TermDates(Plugin):
    """
    A wonderful plugin allowing old people (graduates) to keep track of the
    ever-changing calendar.
    """
    DATE_FORMAT = '%Y-%m-%d'

    db_terms = Plugin.use('mongodb', collection='terms')
    db_weeks = Plugin.use('mongodb', collection='weeks')

    def setup(self):
        super(TermDates, self).setup()

        # If we have stuff in mongodb, we can just load it directly.
        if self.db_terms.find_one():
            self.initialised = True
            self.terms = self.db_terms.find_one()
            self.weeks = self.db_weeks.find_one()
            return

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
            e.reply('error: no term dates (see termdates.set)')
        else:
            e.reply('Aut {} -- {}, Spr {} -- {}, Sum {} -- {}'.format(
                self._term_start('aut'), self._term_end('aut'),
                self._term_start('spr'), self._term_end('spr'),
                self._term_start('sum'), self._term_end('sum')))

    def _term_start(self, term):
        """
        Get the start date (first Monday) of a term as a string.
        """

        term = term.lower()
        return self.terms[term][0].strftime(self.DATE_FORMAT)

    def _term_end(self, term):
        """
        Get the end date (last Friday) of a term as a string.
        """

        term = term.lower()
        return self.terms[term][1].strftime(self.DATE_FORMAT)

    @Plugin.command('week',
                    help='week [term] [num]: info about a week, '
                         'relative to the UoY term schedule')
    def week(self, e):
        if not self.initialised:
            e.reply('error: no term dates (see termdates.set)')
            return

        # We can handle weeks in the following formats:
        #  !week - get information about the current week
        #  !week n - get the date of week n in the current (or next, if in
        #            holiday) term
        #  !week term n - get the date of week n in the given term
        #  !week n term - as above

        week = e['data'].split()
        if len(week) == 0:
            term, weeknum = self._current_week()
        elif len(week) == 1:
            try:
                term = self._current_term()
                weeknum = int(week[0])
                if weeknum < 1:
                    e.reply('error: bad week format')
                    return
            except ValueError:
                term = week[0][:3]
                term, weeknum = self._current_week(term)
        elif len(week) >= 2:
            try:
                term = week[0][:3]
                weeknum = int(week[1])
            except ValueError:
                try:
                    term = week[1][:3]
                    weeknum = int(week[0])
                except ValueError:
                    e.reply('error: bad week format')
                    return
        else:
            e.reply('error: bad week format')
            return

        if weeknum > 0:
            e.reply('{} {}: {}'.format(term.capitalize(),
                                       weeknum,
                                       self._week_start(term, weeknum)))
        else:
            e.reply('{} week before {} (starts {})'
                    .format(ordinal(-weeknum),
                            term.capitalize(),
                            self._week_start(term, 1)))

    def _current_term(self):
        """
        Get the name of the current term
        """

        now = datetime.now().date()
        for term in ['aut', 'spr', 'sum']:
            dates = self.terms[term]
            if now >= dates[0].date() and now <= dates[1].date():
                return term
            elif now <= dates[0].date():
                # We can do this because the terms are ordered
                return term

    def _current_week(self, term=None):
        if term is None:
            term = self._current_term()
        start, _ = self.terms[term]
        now = datetime.now()
        delta = now.date() - start.date()
        weeknum = math.floor(delta.days / 7.0)
        if weeknum >= 0:
            weeknum += 1
        return term, weeknum

    def _week_start(self, term, week):
        """
        Get the start date of a week as a string.
        """

        term = term.lower()
        start = self.weeks['{} 1'.format(term)]
        if week > 0:
            offset = timedelta(weeks=week - 1)
        else:
            offset = timedelta(weeks=week)
        return (start + offset).strftime(self.DATE_FORMAT)

    @Plugin.command('termdates.set',
                    help='termdates.set <aut> <spr> <sum>: set the term dates')
    def termdates_set(self, e):
        dates = e['data'].split()

        if len(dates) < 3:
            e.reply('error: all three dates must be provided')
            return

        # Firstly compute the start and end dates of each term
        for term, date in zip(['aut', 'spr', 'sum'], dates):
            try:
                term_start = datetime.strptime(date, self.DATE_FORMAT)
            except ValueError:
                e.reply('error: dates must be in %Y-%M-%d format.')
                return

            # Not all terms start on a monday, so we need to compute the "real"
            # term start used in all the other calculations.
            # Fortunately Monday is used as the start of the week in Python's
            # datetime stuff, which makes this really simple.
            real_start = term_start - timedelta(days=term_start.weekday())

            # Log for informational purposes
            if not term_start == real_start:
                self.log.info('Computed real_start as {} (from {})'.format(
                    repr(real_start), repr(term_start)))

            term_end = real_start + timedelta(days=4, weeks=9)
            self.terms[term] = (term_start, term_end)

            # Then the start of each week
            self.weeks['{} 1'.format(term)] = term_start
            for week in range(2, 11):
                week_start = real_start + timedelta(weeks=week-1)
                self.weeks['{} {}'.format(term, week)] = week_start

        # Save to the database. As we don't touch the _id attribute in this
        # method, this will cause `save` to override the previously-loaded
        # entry (if there is one).
        if '_id' in self.terms:
            self.db_terms.replace_one({'_id': self.terms['_id']}, self.terms, upsert=True)
        else:
            res = self.db_terms.insert_one(self.terms)
            self.terms['_id'] = res.inserted_id
        if '_id' in self.weeks:
            self.db_weeks.replace_one({'_id': self.weeks['_id']}, self.weeks, upsert=True)
        else:
            res = self.db_weeks.insert_one(self.weeks)
            self.weeks['_id'] = res.inserted_id

        # Finally, we're initialised!
        self.initialised = True
