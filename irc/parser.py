import pyparsing

pyparsing.ParserElement.enablePackrat()

#
# Parse actions
#
def ignore(s, lok, toks):
    "Ignore tokens"
    return []

#
# Rules
#
ignored_literal = lambda lit: pyparsing.Literal(lit).addParseAction(ignore)
ignored_space = ignored_literal(" ")
ignored_colon = ignored_literal(":")

ip4addr = pyparsing.Word(pyparsing.nums, min=1, max=3) + ("." + pyparsing.Word(pyparsing.nums, min=1, max=3)) * 3
ip6addr = pyparsing.Or([
    pyparsing.Word(pyparsing.hexnums) + (":" + pyparsing.Word(pyparsing.hexnums))*7,
    "0:0:0:0:0:" + pyparsing.Or(["0", "FFFF"]) + ":" + ip4addr
])
hostaddr = pyparsing.Or([ip4addr, ip6addr])
shortname = pyparsing.Word(pyparsing.alphas + pyparsing.nums, pyparsing.alphas + pyparsing.nums + '-')
nickname = pyparsing.Word(pyparsing.alphas + pyparsing.nums + "[]\\`_^{|}-")
hostname = pyparsing.Combine(nickname + pyparsing.ZeroOrMore('.' + shortname))
servername = hostname
host = pyparsing.Or([hostname, hostaddr])
vendor = host
key = pyparsing.Optional(vendor + '/') + pyparsing.Word(pyparsing.alphas + pyparsing.nums + '-' + '_')
escaped_value = pyparsing.CharsNotIn("\0\r\n; ")
tag = pyparsing.Group(key + pyparsing.Optional(ignored_literal('=') + pyparsing.Optional(escaped_value, ""), ""))
tags = pyparsing.Group(tag + pyparsing.ZeroOrMore(ignored_literal(';') + tag))
user = pyparsing.CharsNotIn("\0\r\n @")
prefix = pyparsing.Group(pyparsing.Or([servername.setResultsName("server"), (nickname + pyparsing.Optional(pyparsing.Optional(ignored_literal("!") + user) + ignored_literal("@") + host)).setResultsName("nick")]))
command = pyparsing.Or([pyparsing.Word(pyparsing.alphas), pyparsing.Word(pyparsing.nums, exact=3)])
params = pyparsing.Group(pyparsing.ZeroOrMore(ignored_space + pyparsing.CharsNotIn("\0\r\n :")) + pyparsing.Optional(ignored_space + pyparsing.Optional(ignored_colon) + pyparsing.CharsNotIn("\0\r\n")))
message = pyparsing.Optional(ignored_literal('@') + tags + ignored_space, []) + pyparsing.Optional(ignored_colon + prefix + ignored_space, []) + command + pyparsing.Optional(params) + ignored_literal("\r\n")

for name, local in list(locals().items()):
    if isinstance(local, pyparsing.ParserElement):
        local.leaveWhitespace()
        local.parseWithTabs()
        local.setName(name)