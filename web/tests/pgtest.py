"""A new empty PostgreSQL database for one test run (dropped when the process ends).

TEST_DATABASE_URL is a server where the user may create databases, e.g.
postgresql://postgres:postgres@localhost:5432/postgres"""
import atexit
import os
import secrets
from urllib.parse import urlsplit, urlunsplit

import psycopg

SERVER = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")


def _admin(statement: str) -> None:
    conn = psycopg.connect(SERVER, autocommit=True)
    try:
        conn.execute(statement)
    finally:
        conn.close()


def fresh_database() -> str:
    name = "ahead_test_" + secrets.token_hex(6)
    _admin(f"CREATE DATABASE {name}")
    atexit.register(lambda: _admin(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
    return urlunsplit(urlsplit(SERVER)._replace(path="/" + name))
