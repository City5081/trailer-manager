#!/usr/bin/env python3
"""Passwort-Hash fuer WEB_PASSWORD_HASH erzeugen.

    python3 tools/hash_password.py
"""
import getpass
from werkzeug.security import generate_password_hash

pwd = getpass.getpass("Passwort: ")
if pwd != getpass.getpass("Wiederholen: "):
    raise SystemExit("Passwoerter stimmen nicht ueberein.")
print("\nWEB_PASSWORD_HASH=" + generate_password_hash(pwd))
