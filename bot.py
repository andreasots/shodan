import irc
import asyncio
import configparser
import pyparsing
import random
import functools

pyparsing.ParserElement.enablePackrat()

def load_config(filename, section="DEFAULT"):
    config = configparser.ConfigParser()
    config.read(filename)
    config = config[section]
    return {
        "host": config.get("host", "irc.twitch.tv"),
        "port": int(config.get("port", 6667)),
        "pass": config["pass"],
        "nick": config["nick"],
        "channels": list(filter(len, map(str.strip, config["channels"].split(',')))),
        "cmdprefix": config.get("cmdprefix", "+"),
        "chatdepot_host": config.get("chatdepot_host", random.choice(["199.9.253.119", "199.9.253.120"])),
        "chatdepot_port": int(config.get("chatdepot_port", 6667)),
    }

class Shodan:
    def __init__(self):
        self.config = load_config("shodan.ini")
        
        self.connection = irc.Connection(self.config["host"], self.config["port"], self)
        self.whisper = irc.Connection(self.config["chatdepot_host"], self.config["chatdepot_port"], self)

        self.ping_timer = {}
        
        self.commands = []
        self.commands_parser = None
    
    @asyncio.coroutine
    def on_connect(self, conn):
        yield from conn.password(self.config["pass"])
        yield from conn.nick(self.config["nick"])
        yield from conn.cap_req("twitch.tv/commands")
        yield from conn.cap_req("twitch.tv/tags")

        if conn == self.connection:
            for channel in self.config["channels"]:
                yield from conn.join(channel)
    
    def send_ping(self, loop):
        loop.call_later(60, self.send_ping, loop)
        asyncio.async(self.connection.ping(self.config["host"]), loop=loop)
        asyncio.async(self.whisper.ping(self.config["chatdepot_host"]), loop=loop)
        self.ping_timer[self.connection] = loop.call_later(55, self.connection.disconnect)
        self.ping_timer[self.whisper] = loop.call_later(55, self.whisper.disconnect)
    
    @asyncio.coroutine
    def on_pong(self, conn, tags, source, params):
        self.ping_timer[conn].cancel()
        self.ping_timer[conn] = None
    
    @asyncio.coroutine
    def on_privmsg(self, conn, tags, source, params):
        channel, message = params
        try:
            handler, *data = self.commands_parser.parseString(message)
            yield from handler(self, tags, source, channel, *data)
        except pyparsing.ParseException as e:
            pass

    @asyncio.coroutine
    def on_cap(self, conn, tags, source, params):
        star, status, cap = params
        if status == "ACK":
            print("Request for", repr(cap), "acknowleged")
        elif status == "NAK":
            print("Request for", repr(cap), "rejected")

    @asyncio.coroutine
    def on_join(self, conn, tags, source, params):
        if isinstance(source, tuple) and source[0] == self.config["nick"]:
            print("Joined", params[0])

    def register_command(self, parser, handler):
        if isinstance(parser, str):
            parser = pyparsing.Literal(parser)
        parser.addParseAction(lambda s, loc, toks: [handler] + list(toks))
        self.commands.append((parser, handler))

    def compile(self):
        prefix = pyparsing.Literal(self.config["cmdprefix"])
        prefix.addParseAction(lambda *args: [])
        self.commands_parser = prefix + pyparsing.Or([parser for parser, handler in self.commands]) + pyparsing.StringEnd()

    @asyncio.coroutine
    def privmsg(self, target, message):
        if target.startswith("_WHISPER_"):
            yield from self.whisper.privmsg("#jtv", "/w %s %s" % (target.split("_")[2], message))
        else:
            yield from self.connection.privmsg(target, message)

    @asyncio.coroutine
    def on_whisper(self, conn, tags, source, params):
        user, message = params
        yield from self.on_privmsg(conn, tags, source, ["_WHISPER_" + source[0], message])

    @asyncio.coroutine
    def on_ping(self, conn, tags, source, params):
        yield from conn.pong(*params)

    @asyncio.coroutine
    def on_ctcp_action(self, conn, tags, source, params):
        yield from self.on_privmsg(conn, tags, source, [params[0], "/me " + params[1]])

    def run(self):
        return asyncio.gather(self.connection.run(), self.whisper.run())

static_responses = {
    "advice": ["Go left.", "No, the other way.", "Flip it turnways.", "Try jumping."],
    "badadvice": ["Go right.", "Try dying more.", "Have you tried turning it off?", "Take the Master Key."],
    "bad advice": ["Go right.", "Try dying more.", "Have you tried turning it off?", "Take the Master Key."],
    "help": "Commands: +advice, +badadvice or +bad advice, +<k>d<n>, +d<n>",
}

@asyncio.coroutine
def static_response(bot, tags, source, channel, key):
    if isinstance(static_responses[key], list):
        yield from bot.privmsg(channel, random.choice(static_responses[key]))
    else:
        yield from bot.privmsg(channel, static_responses[key])

def static_response_parsers():
    for command in static_responses:
        command = command.split()
        parser = pyparsing.Literal(command[0])
        for token in command[1:]:
            space = pyparsing.White()
            space.addParseAction(lambda s, loc, toks: [" "])
            parser += pyparsing.Literal(token)
        parser.addParseAction(lambda s, loc, toks: ["".join(toks)])
        yield parser

static_response_parser = pyparsing.Or(list(static_response_parsers()))

@asyncio.coroutine
def dice(bot, tags, source, channel, num, d, sides):
    if num is None:
        num = 1
    else:
        num = int(num)
    sides = int(sides)
    result = sum(random.randint(1, sides) for dice in range(num))
    yield from bot.privmsg(channel, str(result))

dice_parser = pyparsing.Optional(pyparsing.Word(pyparsing.nums), None) + "d" + pyparsing.Word(pyparsing.nums)

class Restrict:
    def __init__(self, criterion, message = None):
        self.criterion = criterion
        self.message = message

    def __call__(self, func):
        @functools.wraps(func)
        @asyncio.coroutine
        def wrapper(bot, tags, source, channel, *args, **kwargs):
            if self.criterion(bot, tags, source, channel):
                yield from func(bot, tags, source, channel, *args, **kwargs)
            elif self.message is not None:
                name = tags.get("display-name", "")
                if name == "":
                    name = source[0]
                yield from bot.privmsg(channel, "%s: %s" % (name, self.message))
        return wrapper

def is_mod(bot, tags, source, channel):
    return tags.get("user-type") in {"mod", "global_mod", "admin", "staff"} or source[0] == channel[1:]

def is_sub(bot, tags, source, channel):
    return tags.get("subscriber", "0") == "1"

mod_only = Restrict(is_mod, "That is a mod-only command.")
sub_only = Restrict(lambda *args: is_sub(*args) or is_mod(*args), "That is a sub-only command.")

@mod_only
@asyncio.coroutine
def test(bot, tags, source, channel, _):
    yield from bot.privmsg(channel, "Test.")

loop = asyncio.get_event_loop()
bot = Shodan()
bot.register_command(static_response_parser, static_response)
bot.register_command(dice_parser, dice)
bot.register_command("test", test)
bot.compile()
loop.call_later(5, bot.send_ping, loop)
loop.run_until_complete(bot.run())
