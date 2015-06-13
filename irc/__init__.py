import asyncio

import irc.parser

def unescape(value):
    return value.replace("\\:", ";") \
                .replace("\\s", " ") \
                .replace("\\\\", "\\") \
                .replace("\\r", "\r") \
                .replace("\\n", "\n")

class Bot:
    def __init__(self, host, port, loop=None):
        self.host = host
        self.port = port
        
        self.loop = loop or asyncio.get_event_loop()
        self.writer = None
    
    @asyncio.coroutine
    def run(self):
        wait_time = 1
        while True:
            try:
                reader, self.writer = yield from asyncio.open_connection(self.host, self.port, loop=self.loop)
                yield from self.signal("connect")
                while not reader.at_eof():
                    line = yield from reader.readline()
                    if not line.endswith(b"\r\n"):
                        continue
                    wait_time = 1
                    tags, source, command, params = irc.parser.message.parseString(line.decode("utf-8", "replace"))
                    tags = {tag: unescape(value) for tag, value in tags}
                    params = list(params)
                    if "server" in source:
                        source = source["server"]
                    elif "nick" in source:
                        source = source["nick"]
                        if len(source) == 1:
                            source = (source[0], None, None)
                        elif len(source) == 2:
                            source = (source[0], None, source[1])
                        else:
                            source = (source[0], source[1], source[2])
                    else:
                        source = self.host
                    yield from self.signal(command.lower(), tags, source, params)
            except IOError as e:
                pass
            yield from asyncio.sleep(wait_time)
            wait_time *= 2
    
    def disconnect(self):
        self.writer.close()
        self.writer = None
    
    @asyncio.coroutine
    def signal(self, name, *args, **kwargs):
        callback = getattr(self, "on_" + name, None)
        if callback is not None:
            yield from callback(*args, **kwargs)
    
    #
    # IRC commands
    #
    @asyncio.coroutine
    def command_raw(self, command):
        self.writer.write((command+"\r\n").encode("utf-8"))
        yield from self.writer.drain()

    @asyncio.coroutine
    def password(self, password):
        yield from self.command_raw("PASS " + password)
    
    @asyncio.coroutine
    def nick(self, nick):
        yield from self.command_raw("NICK " + nick)
    
    @asyncio.coroutine
    def join(self, target):
        yield from self.command_raw("JOIN " + target)
    
    @asyncio.coroutine
    def cap_req(self, cap):
        yield from self.command_raw("CAP REQ :" + cap)
    
    @asyncio.coroutine
    def ping(self, server1, server2=None):
        yield from self.command_raw("PING " + server1 + (" " + server2 if server2 is not None else ""))
    
    @asyncio.coroutine
    def pong(self, server1, server2=None):
        yield from self.command_raw("PONG " + server1 + (" " + server2 if server2 is not None else ""))
    
    @asyncio.coroutine
    def privmsg(self, target, message):
        yield from self.command_raw("PRIVMSG " + target + " :" + message)
    
    #
    # Default handlers
    #
    @asyncio.coroutine
    def on_ping(self, tags, source, params):
        yield from self.pong(*params)