"""Opt-in isolated-run diagnostics: IDs/timings only, no SQL values or secrets."""
import json
import os
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine

DIRECTORY = Path(os.environ['FITIGO_TEST_ARTIFACTS'])
COUNTS = Counter()
SECONDS = Counter()


def emit(value):
    with (DIRECTORY / 'progress.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(value) + '\n')


@event.listens_for(Engine, 'before_cursor_execute')
def before(connection, cursor, statement, parameters, context, executemany):
    context.release_started = time.perf_counter()


@event.listens_for(Engine, 'after_cursor_execute')
def after(connection, cursor, statement, parameters, context, executemany):
    operation = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else 'EMPTY'
    COUNTS[operation] += 1
    SECONDS[operation] += time.perf_counter() - context.release_started


def pytest_collection_modifyitems(config, items):
    ids = [item.nodeid for item in items]
    (DIRECTORY / 'collected.json').write_text(json.dumps(ids, indent=2), encoding='utf-8')
    count = int(os.environ.get('FITIGO_TEST_SHARD_COUNT', '1'))
    index = int(os.environ.get('FITIGO_TEST_SHARD_INDEX', '0'))
    files = sorted({item.nodeid.split('::')[0] for item in items})
    assigned = {name for number, name in enumerate(files) if number % count == index}
    selected = [item for item in items if item.nodeid.split('::')[0] in assigned]
    removed = [item for item in items if item.nodeid.split('::')[0] not in assigned]
    if removed:
        config.hook.pytest_deselected(items=removed)
    items[:] = selected
    (DIRECTORY / 'selected.json').write_text(json.dumps([item.nodeid for item in selected], indent=2), encoding='utf-8')


def pytest_runtest_logstart(nodeid, location):
    COUNTS.clear(); SECONDS.clear()
    emit({'event': 'start', 'nodeid': nodeid, 'at': time.time()})


def pytest_runtest_logreport(report):
    emit({'event': 'phase', 'nodeid': report.nodeid, 'phase': report.when,
          'outcome': report.outcome, 'seconds': report.duration,
          'sql_counts': dict(COUNTS), 'sql_seconds': dict(SECONDS), 'at': time.time()})


def pytest_sessionfinish(session, exitstatus):
    emit({'event': 'finished', 'exit': int(exitstatus), 'at': time.time()})