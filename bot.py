import irc
import asyncio
import configparser
import pyparsing

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

    def register_command(self, parser, handler):
        if isinstance(parser, str):
            parser = pyparsing.Literal(parser)
        parser.addParseAction(lambda s, loc, toks: [handler] + list(toks))
        self.commands.append((parser, handler))
    
    def compile(self):
        prefix = pyparsing.Literal(self.config["cmdprefix"])
        prefix.addParseAction(lambda *args: [])
        self.commands_parser = prefix + pyparsing.Or([parser for parser, handler in self.commands]) + pyparsing.StringEnd()

loop = asyncio.get_event_loop()
bot = Shodan()
bot.register_command("advice", lambda bot, tags, source, channel, *args: bot.privmsg(channel, "Go left."))
bot.register_command("bad" + pyparsing.Optional(" ") + "advice", lambda bot, tags, source, channel, *args: bot.privmsg(channel, "Go right."))
bot.compile()
loop.call_later(5, bot.send_ping, loop)
loop.run_until_complete(bot.run())
