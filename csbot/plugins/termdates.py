from csbot.plugin import Plugin
from datetime import datetime, timedelta


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

        term = term.lower()
        return self.terms[term][0].strftime(self.DATE_FORMAT)

    def _term_end(self, term):
        """
        Get the end date (last Friday) of a term as a string.
        """

        term = term.lower()
        return self.terms[term][1].strftime(self.DATE_FORMAT)

    @Plugin.command('week',
                    help='week [term] <num>: get the start date of a week')
    def week(self, e):
        if not self.initialised:
            e.protocol.msg(e['reply_to'],
                           'error: no term dates (see termdates.set)')
            return

        # We can handle weeks in the following formats:
        #  !week n - get the date of week n in the current (or next, if in
        #            holiday) term
        #  !week term n - get the date of week n in the given term
        #  !week n term - as above

        week = e['data'].split()
        if len(week) == 1:
            term = self._current_term()
            weeknum = week[0][:3]
        elif len(week) >= 2:
            try:
                term = week[0][:3]
                weeknum = int(week[1])
            except ValueError:
                try:
                    term = week[1][:3]
                    weeknum = int(week[0])
                except ValueError:
                    e.prototol.msg(e['reply_to'], 'error: bad week format')
                    return
        else:
            e.protocol.msg(e['reply_to'], 'error: bad week format')
            return

        try:
            weekstart = self._week_start(term, weeknum)
        except KeyError:
            e.protocol.msg(e['reply_to'], 'error: bad week')
            return

        term = term.capitalize()
        e.protocol.msg(e['reply_to'],
                       '{} {}: {}'.format(term, weeknum, weekstart))

    def _current_term(self):
        """
        Get the name of the current term
        """

        now = datetime.now()
        for term in ['aut', 'spr', 'sum']:
            dates = self.terms[term]
            if now >= dates[0] and now <= dates[1]:
                return term
            elif now <= dates[0]:
                # We can do this because the terms are ordered
                return term

    def _week_start(self, term, week):
        """
        Get the start date of a week as a string.
        """

        term = term.lower()
        return self.weeks['{} {}'.format(term, week)].strftime(
            self.DATE_FORMAT)

    @Plugin.command('termdates.set',
                    help='termdates.set <aut> <spr> <sum>: set the term dates')
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
        self.db_terms.save(self.terms)
        self.db_weeks.save(self.weeks)

        # Finally, we're initialised!
        self.initialised = True
