import json
import sqlite3
from copy import deepcopy

import pytest

from jev_harness.runner import new_run
from jev_harness.store import Store


def comparison():
    return {"id": "example", "created_at": "2026-01-01", "status": "running",
            "runs": {path: new_run(path, {}) for path in ("normal", "jev")}}


def test_event_append_does_not_rewrite_history_or_other_run(tmp_path):
    store = Store(tmp_path)
    value = comparison()
    store.save(value)
    run = value['runs']['normal']
    run['events'].append({'id': 'e1', 'type': 'model', 'detail': {'large': 'x'*10000}})
    store.update_run(value['id'], 'normal', run)
    old = store.connection.execute('SELECT rowid,payload FROM events').fetchall()
    metadata = store.connection.execute('SELECT payload FROM comparisons').fetchone()[0]
    before = store.connection.total_changes
    run['events'].append({'id': 'e2', 'type': 'response', 'detail': {}})
    store.update_run(value['id'], 'normal', run)
    assert store.connection.total_changes - before == 1
    assert store.connection.execute('SELECT rowid,payload FROM events ORDER BY position LIMIT 1').fetchall() == old
    assert store.connection.execute('SELECT payload FROM comparisons').fetchone()[0] == metadata
    assert 'runs' not in json.loads(metadata)
    assert store.get(value['id'])['runs']['normal'] == run
    assert store.get(value['id'])['runs']['jev'] == value['runs']['jev']
    store.close()


def test_failed_update_is_atomic(tmp_path):
    store = Store(tmp_path)
    value = comparison()
    store.save(value)
    before = store.get(value['id'])
    broken = deepcopy(before['runs']['normal'])
    broken['status'] = 'completed'
    broken['events'] = [{'id': 'same'}, {'id': 'same'}]
    with pytest.raises(sqlite3.IntegrityError):
        store.update_run(value['id'], 'normal', broken)
    assert store.get(value['id']) == before
    store.close()


def test_legacy_migration_keeps_backup_and_normalizes_hint(tmp_path):
    value = comparison()
    value['runs']['jev'].update(workflow='clarify', event_keys=['workflow'], events=[
        {'id':'legacy', 'type':'workflow', 'title':'Workflow: clarify', 'detail':{'workflow':'clarify'}}])
    with sqlite3.connect(tmp_path / 'comparisons.db') as connection:
        connection.execute('CREATE TABLE comparisons (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)')
        connection.execute('INSERT INTO comparisons VALUES (?,?,?)', (value['id'], value['created_at'], json.dumps(value)))
    store = Store(tmp_path)
    restored = store.get(value['id'])['runs']['jev']
    assert 'workflow' not in restored
    assert restored['playbook_hint'] == 'clarify'
    assert restored['event_keys'] == ['playbook_hint']
    assert restored['events'][0]['type'] == 'playbook_hint'
    assert restored['events'][0]['detail'] == {'playbook_hint': 'clarify'}
    with sqlite3.connect(tmp_path / 'comparisons.pre-fields.db') as backup:
        assert json.loads(backup.execute('SELECT payload FROM comparisons').fetchone()[0]) == value
    store.close()
    reopened = Store(tmp_path)
    assert reopened.get(value['id'])['runs']['jev'] == restored
    reopened.close()
