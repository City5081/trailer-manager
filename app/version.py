"""Where the application says who it is."""

VERSION = "0.5.1"

# Sent with every outgoing request. Without it urllib announces itself as
# "Python-urllib/3.x", which some reverse proxies and CDNs answer with a flat
# 403 - a failure that looks exactly like a wrong token.
USER_AGENT = "trailer-manager/{}".format(VERSION)
