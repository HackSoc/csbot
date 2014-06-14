import asyncio
import logging
import signal
import re


def ircparse(line):
    match = re.fullmatch((r'(:(?P<prefix>\S+) )?(?P<command>\S+)'
                          r'(?P<args>( (?!:)\S+)*)( :(?P<data>.*))?'),
                         line)
    if match is None:
        print('error parsing: ' + line)
        return None
    else:
        groups = match.groupdict()
        groups['args'] = groups['args'].split()
        return groups


class IRCProtocol(asyncio.Protocol):
    LOG = logging.getLogger('csbot.IRCProtocol')

    def __init__(self, bot):
        self.bot = bot
        self.buffer = b''
        self.transport = None
        self.exiting = False

    def connection_made(self, transport):
        self.LOG.debug('connection made')
        self.transport = transport

    def data_received(self, data):
        self.LOG.debug('data received: %s', data)
        data = self.buffer + data
        lines = data.split(b'\r\n')
        self.buffer = lines.pop()
        for line in lines:
            # Attempt to decode incoming strings; if they are neither UTF-8 or
            # CP1252 they will get mangled as whatever CP1252 thinks they are.
            try:
                line = line.decode('utf-8')
            except UnicodeDecodeError:
                line = line.decode('cp1252')
            self.bot.line_received(line)

    def write_line(self, data):
        data = data.encode('utf-8') + b'\r\n'
        self.transport.write(data)
        self.LOG.debug('data sent: %s', data)

    def connection_lost(self, exc):
        self.transport = None
        if not self.exiting:
            self.bot.loop.call_later(5, self.bot.create_connection)
        self.LOG.debug('connection lost')

    def close(self):
        self.exiting = True
        if self.transport is not None:
            self.transport.close()


class IRCBot(object):
    LOG = logging.getLogger('csbot.IRCBot')

    def __init__(self, config=None):
        self.loop = asyncio.get_event_loop()
        self.protocol = None

    def start(self, run_forever=True):
        self.LOG.info('starting bot')
        # Run bot setup()
        self.create_connection()
        self.loop.add_signal_handler(signal.SIGINT, self.stop)
        if run_forever:
            self.loop.run_forever()

    def stop(self):
        self.LOG.info('stopping bot')
        # Run bot teardown()
        self.protocol.close()
        self.loop.stop()

    def create_connection(self):
        create_protocol = lambda: IRCProtocol(self)
        t = asyncio.Task(self.loop.create_connection(create_protocol,
                                                     'chat.freenode.net',
                                                     6667))
        t.add_done_callback(self.connection_made)

    def connection_made(self, f):
        if self.protocol is not None:
            self.protocol.close()
            self.protocol = None

        # Get result of create_connection from Future
        transport, self.protocol = f.result()

        self.send_raw('USER csbot * * :csbot')
        self.send_raw('NICK not_really_csbot')
        self.send_raw('JOIN #cs-york-dev')

    def line_received(self, line):
        self.LOG.debug('line received: %s', line)
        cmd = ircparse(line)
        self.LOG.debug('command parsed: %r', cmd)
        if cmd['command'] == 'PING':
            self.send_raw('PONG :{data}'.format(**cmd))

    def send_raw(self, line):
        self.protocol.write_line(line)


def main():
    logging.basicConfig(format='[%(levelname).1s:%(name)s] %(message)s',
                        level=logging.DEBUG)
    logging.getLogger('asyncio').setLevel(logging.INFO)

    loop = asyncio.get_event_loop()
    bot = IRCBot()
    bot.start()
    loop.close()


if __name__ == '__main__':
    main()