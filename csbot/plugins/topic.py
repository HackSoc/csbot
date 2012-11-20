import requests
import urllib

from csbot.plugin import Plugin
from csbot.util import nick

class TopicException(Exception):
    pass

class Topic(Plugin):

    def setup(self):
        super(Topic, self).setup()
        self.topic = {}


    @Plugin.hook('core.channel.topic')
    def currentTopic(self, e):
        self.topics[e["channel"]] = e['topic']

    @Plugin.command('topic')
    def topic(self, e):
        """Manipulate the topic. Possible commands: add append prepend remove change.
        """
        try: 
            if not nick(e['user']) in self.config_get("users").split(" "):
                raise TopicException(u"You do not have permission to execute that command")

            command, payload = e['data'].split(" ", 1)
            separator = self.config_get("separator")

            splitted_topic = self.topics[e["reply_to"]].split(" "+separator+" ")

            position = None

            #map append alias to add to last position
            if command == "append":
                command = "add"
                position = len(splitted_topic)

            #map prepend alias to add to first position
            if command == "prepend":
                command = "add"
                position = 0

            #handle the add comand
            if command == "add":
                if position is None:
                    position, payload = payload.split(" ", 1)

                    if not position.isdigit() or int(position) >= len(splitted_topic):
                        raise TopicException(u"Invalid position number")

                    position = int(position)

                if position == len(splitted_topic):
                    splitted_topic.append(payload)
                else: 
                    splitted_topic.insert(position, payload)

            #handle the remove command
            elif command == "remove":
                position = payload

                if not position.isdigit() or int(position) >= len(splitted_topic):
                    raise TopicException(u"Invalid position number")

                position = int(position) 

                del splitted_topic[position]
            #handle the change command
            elif command == "change":
                position, payload = payload.split(" ", 1)

                if not position.isdigit() or int(position) >= len(splitted_topic):
                    raise TopicException(u"Invalid position number")

                position = int(position)

                splitted_topic[position] = payload

            e.protocol.topic(e["reply_to"], (" "+separator+" ").join(splitted_topic))
        except TopicException as exception:
            e.protocol.msg(e["reply_to"], "Topic error: " + str(exception))
