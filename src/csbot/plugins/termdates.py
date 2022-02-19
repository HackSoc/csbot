from csbot.plugin import Plugin
import datetime
import math
import typing as _t

from ..util import ordinal


class Term:
    def __init__(self, key: str, start_date: datetime.datetime):
        self.key = key
        self.start_date = start_date

    @property
    def first_monday(self) -> datetime.datetime:
        return self.start_date - datetime.timedelta(days=self.start_date.weekday())

    @property
    def last_friday(self) -> datetime.datetime:
        return self.first_monday + datetime.timedelta(days=4, weeks=9)

    def get_week_number(self, date: datetime.date) -> int:
        """Get the "term week number" of a date relative to this term.

        The first week of term is week 1, not week 0. Week 1 starts at the
        Monday of the term's start date, even if the term's start date is not
        Monday. Any date before the start of the term gives a negative week
        number.
        """
        delta = date - self.first_monday.date()
        week_number = math.floor(delta.days / 7.0)
        if week_number >= 0:
            return week_number + 1
        else:
            return week_number

    def get_week_start(self, week_number: int) -> datetime.datetime:
        """Get the start date of a specific week number relative to this term.

        The first week of term is week 1, not week 0, although this method
        allows both. When referring to the first week of term, the start date is
        the term start date (which may not be a Monday). All other weeks start
        on their Monday.
        """
        if week_number in (0, 1):
            return self.start_date
        elif week_number > 1:
            return self.first_monday + datetime.timedelta(weeks=week_number - 1)
        else:
            return self.first_monday + datetime.timedelta(weeks=week_number)


class TermDates(Plugin):
    """
    A wonderful plugin allowing old people (graduates) to keep track of the
    ever-changing calendar.
    """
    DATE_FORMAT = '%Y-%m-%d'
    TERM_KEYS = ('aut', 'spr', 'sum')

    db_terms = Plugin.use('mongodb', collection='terms')

    terms = None
    _doc_id = None

    def setup(self):
        super(TermDates, self).setup()
        self._load()

    def _load(self):
        doc = self.db_terms.find_one()
        if not doc:
            return False
        self.terms = {key: Term(key, doc[key][0]) for key in self.TERM_KEYS}
        self._doc_id = doc['_id']
        return True

    def _save(self):
        if not self.terms:
            return False
        doc = {key: (self.terms[key].start_date, self.terms[key].last_friday) for key in self.TERM_KEYS}
        if self._doc_id:
            self.db_terms.replace_one({'_id': self._doc_id}, doc, upsert=True)
        else:
            res = self.db_terms.insert_one(doc)
            self._doc_id = res.inserted_id
        return True

    @property
    def initialised(self) -> bool:
        """If no term dates have been set, the calendar is uninitialised and can't be asked about term thing."""
        return self._doc_id is not None

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
        return self.terms[term].start_date.strftime(self.DATE_FORMAT)

    def _term_end(self, term):
        """
        Get the end date (last Friday) of a term as a string.
        """

        term = term.lower()
        return self.terms[term].last_friday.strftime(self.DATE_FORMAT)

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

        week = e['data'].lower().split()
        if len(week) == 0:
            term, week_number = self._current_week()
        elif len(week) == 1:
            try:
                term = self._current_or_next_term()
                week_number = int(week[0])
                if week_number < 1:
                    e.reply('error: bad week format')
                    return
            except ValueError:
                term_key = week[0][:3]
                term, week_number = self._current_week(term_key)
        elif len(week) >= 2:
            try:
                term_key = week[0][:3]
                week_number = int(week[1])
            except ValueError:
                try:
                    term_key = week[1][:3]
                    week_number = int(week[0])
                except ValueError:
                    e.reply('error: bad week format')
                    return
            try:
                term = self.terms[term_key]
            except KeyError:
                e.reply('error: bad week format')
                return
        else:
            e.reply('error: bad week format')
            return

        if term is None:
            e.reply('error: no term dates (see termdates.set)')
        elif week_number > 0:
            e.reply('{} {}: {}'.format(term.key.capitalize(),
                                       week_number,
                                       term.get_week_start(week_number).strftime(self.DATE_FORMAT)))
        else:
            e.reply('{} week before {} (starts {})'
                    .format(ordinal(-week_number),
                            term.key.capitalize(),
                            term.start_date.strftime(self.DATE_FORMAT)))

    def _current_or_next_term(self) -> _t.Optional[Term]:
        """
        Get the name of the current term
        """

        now = datetime.datetime.now().date()
        for key in self.TERM_KEYS:
            term = self.terms[key]
            if now < term.first_monday.date():
                return term
            elif now <= term.last_friday.date():
                return term
        return None

    def _current_week(self, key: _t.Optional[str] = None) -> (_t.Optional[Term], _t.Optional[int]):
        if key:
            term = self.terms.get(key.lower())
        else:
            term = self._current_or_next_term()
        if term:
            return term, term.get_week_number(datetime.date.today())
        else:
            return None, None

    @Plugin.command('termdates.set',
                    help='termdates.set <aut> <spr> <sum>: set the term dates')
    def termdates_set(self, e):
        dates = e['data'].split()

        if len(dates) < 3:
            e.reply('error: all three dates must be provided')
            return

        terms = {}
        for key, date in zip(self.TERM_KEYS, dates):
            try:
                term_start = datetime.datetime.strptime(date, self.DATE_FORMAT)
            except ValueError:
                e.reply('error: dates must be in %Y-%M-%d format.')
                return

            terms[key] = Term(key, term_start)

        self.terms = terms
        self._save()
