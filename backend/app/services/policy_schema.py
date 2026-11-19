"""Fail closed on older deployments; never auto-migrate a working database."""
from weakref import WeakKeyDictionary
from sqlalchemy import inspect

_ready = WeakKeyDictionary()


def available(db):
    engine = db.get_bind()
    if engine not in _ready:
        inspector = inspect(db.connection())
        _ready[engine] = all(inspector.has_table(name) for name in ('booking_cancellations', 'membership_transfers'))
    return _ready[engine]