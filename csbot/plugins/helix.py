import hashlib
from csbot.plugin import Plugin


class Helix(Plugin):
    """
    The premier csbot plugin, allowing mere mortals to put questions
    to the mighty helix, and receive his divine wisdom.

    Notes:
        - The popular online version basically just selects a random
          outcome, and saves it with a random url so that it can be
          reused if the same question is asked.
        - I'm lazy, so I'm just going to hash whatever the person puts
          in and mod the resulting value (taken from hex) to pick out
          an element of the outcomes list. That way if the same
          questions gets asked twice, it gets (hopefully) the same
          answer.
    """
    outcomes = ["It is certain", "It is decidedly so", "Without a doubt",
                "Yes definitely", "You may rely on it", "As I see it, yes",
                "Most likely", "Outlook good", "Yes",
                "Signs point to yes", "Reply hazy try again",
                "Ask again later", "Better not tell you now",
                "Cannot predict now", "Concentrate and ask again ",
                "Don't count on it", "My reply is no", "My sources say no",
                "Outlook not so good", "Very doubtful", "no.",
                "START", "A", "B", "UP", "DOWN", "LEFT",
                "RIGHT", "SELECT", "START", "A", "B", "UP",
                "DOWN", "LEFT", "RIGHT", "SELECT"]

    def setup(self):
        super(Helix, self).setup()

    def _answer(self, message):
        # The almighty helix accepts only cleansed queries
        worshippers_question = ''.join(filter(lambda x: x.isalpha(), message)).lower()

        # Recieve and demystify the almighty helix's answer
        answer = hashlib.sha1(worshippers_question.encode('utf-8'))
        answer = int(answer.hexdigest(), 16)
        return self.outcomes[answer % len(self.outcomes)]

    @Plugin.command('helix')
    def ask_the_almighty_helix(self, e):
        """
        Ask and you shall recieve.
        """
        answer = self._answer(e["data"])
        e.protocol.msg(e['reply_to'],
                       'The Helix Fossil says: "{}"'.format(answer))
