"""Shared fakes. Tests never touch the real database: pool() is replaced by an
in-memory stand-in that records every statement and answers from a script."""
from types import SimpleNamespace

import pytest


class FakeCursor:
    def __init__(self, rows, rowcount):
        self.rows, self.rowcount = list(rows), rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class FakeConn:
    def __init__(self, respond):
        self.respond, self.log = respond, []

    def execute(self, sql, params=None):
        self.log.append((" ".join(sql.split()), params))
        rows, rc = self.respond(" ".join(sql.split()), params)
        return FakeCursor(rows, rc)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakePool:
    """respond(sql, params) -> (rows, rowcount). Unscripted statements return nothing."""
    def __init__(self, respond=None):
        self.conn = FakeConn(respond or (lambda sql, p: ([], 0)))

    def connection(self):
        return self.conn

    @property
    def log(self):
        return self.conn.log

    def sql_like(self, fragment):
        return [s for s, _ in self.log if fragment in s]


@pytest.fixture
def fake_pool():
    return FakePool


@pytest.fixture
def fake_project():
    """The slice of Project the pure code paths read."""
    def make(**kw):
        acts = []
        p = SimpleNamespace(id="p1", lang="bg", filters=[], dashboard=[], notes=[],
                            activity=acts, log_activity=lambda kind, text: acts.append((kind, text)))
        for k, v in kw.items():
            setattr(p, k, v)
        return p
    return make
