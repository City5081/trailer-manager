#!/usr/bin/env python3
"""Create a password hash for WEB_PASSWORD_HASH.

    python3 tools/hash_password.py

Only needed for unattended deployments that set credentials through the
environment. The normal way is the setup wizard, which stores the hash itself.
"""
import getpass

from werkzeug.security import generate_password_hash

pwd = getpass.getpass("Password: ")
if pwd != getpass.getpass("Repeat: "):
    raise SystemExit("The passwords do not match.")
print("\nWEB_PASSWORD_HASH=" + generate_password_hash(pwd))
