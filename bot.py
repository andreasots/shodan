import irc
import asyncio
import configparser
import pyparsing
import random

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
        "cmdprefix": config.get("cmdprefix", "@")
    }

class Shodan(irc.Bot):
    def __init__(self):
        self.config = load_config("shodan.ini")
        super(Shodan, self).__init__(self.config["host"], self.config["port"])
        
        self.ping_timer = None
        
        self.commands = []
        self.commands_parser = None
    
    @asyncio.coroutine
    def on_connect(self):
        yield from self.password(self.config["pass"])
        yield from self.nick(self.config["nick"])
        for channel in self.config["channels"]:
            yield from self.join(channel)
        yield from self.cap_req("twitch.tv/commands")
        yield from self.cap_req("twitch.tv/tags")
        yield from self.cap_req("echo-message")
    
    def send_ping(self, loop):
        loop.call_later(60, self.send_ping, loop)
        asyncio.async(self.ping(self.host), loop=loop)
        self.ping_timer = loop.call_later(55, self.disconnect)
    
    @asyncio.coroutine
    def on_pong(self, tags, source, params):
        self.ping_timer.cancel()
        self.ping_timer = None
    
    @asyncio.coroutine
    def on_privmsg(self, tags, source, params):
        channel, message = params
        try:
            handler, *data = self.commands_parser.parseString(message)
            yield from handler(self, tags, source, channel, *data)
        except pyparsing.ParseException as e:
            pass
    
    @asyncio.coroutine
    def on_cap(self, tags, source, params):
        star, status, cap = params
        if status == "ACK":
            print("Request for", repr(cap), "acknowleged")
        elif status == "NAK":
            print("Request for", repr(cap), "rejected")

    def register_command(self, parser, handler):
        if isinstance(parser, str):
            parser = pyparsing.Literal(parser)
        parser.addParseAction(lambda s, loc, toks: [handler] + list(toks))
        self.commands.append((parser, handler))
    
    def compile(self):
        prefix = pyparsing.Literal(self.config["cmdprefix"])
        prefix.addParseAction(lambda *args: [])
        self.commands_parser = prefix + pyparsing.Or([parser for parser, handler in self.commands]) + pyparsing.StringEnd()

static_responses = {
    "advice": ["Go left.", "No, the other way.", "Flip it turnways.", "Try jumping."],
    "badadvice": ["Go right.", "Try dying more.", "Have you tried turning it off?", "Take the Master Key."],
    "bad advice": ["Go right.", "Try dying more.", "Have you tried turning it off?", "Take the Master Key."],
    "help": "Commands: @advice, @badadvice or @bad advice, @<k>d<n>, @d<n>",
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

loop = asyncio.get_event_loop()
bot = Shodan()
bot.register_command(static_response_parser, static_response)
bot.register_command(dice_parser, dice)
bot.compile()
loop.call_later(5, bot.send_ping, loop)
loop.run_until_complete(bot.run())