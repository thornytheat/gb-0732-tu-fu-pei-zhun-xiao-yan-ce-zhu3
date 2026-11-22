import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.errors import RegisterError
from app.manifest import archive_key as archive_key_of, canonical_json

SCHEMA = '''
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    snapshot TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signatures (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    sheet TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    signed_at TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version = 1),
    PRIMARY KEY (run_id, sheet)
);
CREATE TABLE IF NOT EXISTS issuances (
    archive_key TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    issuance_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (archive_key, revision)
);
CREATE INDEX IF NOT EXISTS issuances_run ON issuances(run_id);
'''


class Store:
    def __init__(self, database):
        self.database = database

    @contextmanager
    def connect(self, mode='DEFERRED'):
        connection = sqlite3.connect(self.database, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA foreign_keys = ON')
            connection.execute(f'BEGIN {mode}')
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect('IMMEDIATE') as connection:
            for statement in SCHEMA.strip().removesuffix(';').split(';'):
                connection.execute(statement)

    @staticmethod
    def _read(connection, run_id, required=True):
        row = connection.execute('SELECT snapshot FROM runs WHERE run_id = ?', (run_id,)).fetchone()
        if not row:
            if required:
                raise RegisterError('RUN_NOT_FOUND', '未找到该批次', 404)
            return None
        signatures = connection.execute(
            'SELECT sheet, reviewer, signed_at, version FROM signatures WHERE run_id = ? ORDER BY sheet',
            (run_id,),
        )
        return {**json.loads(row['snapshot']), 'signatures': [dict(signature) for signature in signatures]}

    def get(self, run_id, required=True):
        with self.connect() as connection:
            return self._read(connection, run_id, required)

    def insert(self, snapshot):
        manifest = snapshot['manifest']
        run_id = manifest['run_id']
        serialized = canonical_json(snapshot)
        with self.connect('IMMEDIATE') as connection:
            insert = connection.execute('INSERT INTO runs VALUES (?, ?, ?) ON CONFLICT(run_id) DO NOTHING',
                                        (run_id, manifest['created_at'], serialized))
            return self._read(connection, run_id), insert.rowcount == 0

    def sign(self, run_id, sheet, reviewer, expected_version):
        with self.connect('IMMEDIATE') as connection:
            snapshot = self._read(connection, run_id)
            decision = next((row for row in snapshot['reviews'] if row['code'] == sheet), None)
            if decision is None:
                raise RegisterError('SHEET_NOT_FOUND', '该批次没有此图幅', 404)
            if decision['status'] != 'READY':
                raise RegisterError('SIGNATURE_BLOCKED', '图幅尚未满足签审条件', 409, decision['reason'])
            existing = next((row for row in snapshot['signatures'] if row['sheet'] == sheet), None)
            if existing and existing['reviewer'] == reviewer and expected_version in (0, existing['version']):
                return existing
            if existing or expected_version != 0:
                raise RegisterError('SIGNATURE_VERSION_CONFLICT', '签审版本已变化，请刷新', 409,
                                    existing['version'] if existing else 0)
            signed_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
            connection.execute('INSERT INTO signatures VALUES (?, ?, ?, ?, 1)',
                               (run_id, sheet, reviewer, signed_at))
            return {'sheet': sheet, 'reviewer': reviewer, 'signed_at': signed_at, 'version': 1}

    @staticmethod
    def _history(connection, archive_key):
        rows = connection.execute(
            'SELECT revision, body FROM issuances WHERE archive_key = ? ORDER BY revision',
            (archive_key,)).fetchall()
        return [(row['revision'], json.loads(row['body'])) for row in rows]

    @staticmethod
    def _where(connection, run_id):
        row = connection.execute('SELECT snapshot FROM runs WHERE run_id = ?', (run_id,)).fetchone()
        if not row:
            return None
        return archive_key_of(json.loads(row['snapshot'])['manifest'])

    def get_issuance(self, run_id, revision=None, required=True):
        with self.connect() as connection:
            archive_key = self._where(connection, run_id)
            if archive_key is None:
                self._read(connection, run_id)  # raises RUN_NOT_FOUND
            history = self._history(connection, archive_key)
            match = None
            if revision is not None:
                match = next((body for number, body in history if number == revision), None)
            elif history:
                match = history[-1][1]
            if match is None and required:
                raise RegisterError('ISSUANCE_NOT_FOUND', '该档件尚未形成发放册', 404)
            return match

    def issuance_history(self, run_id):
        with self.connect() as connection:
            archive_key = self._where(connection, run_id)
            if archive_key is None:
                self._read(connection, run_id)
            return [body for _, body in self._history(connection, archive_key)]

    def create_issuance(self, run_id, build, same_content=lambda previous, candidate: False):
        # Read, build and append run in one IMMEDIATE transaction. Revising the
        # register never overwrites a prior revision, and a failure rolls back
        # leaving the previously issued register readable.
        with self.connect('IMMEDIATE') as connection:
            snapshot = self._read(connection, run_id)
            archive_key = archive_key_of(snapshot['manifest'])
            history = self._history(connection, archive_key)
            latest = history[-1][1] if history else None
            candidate = build(snapshot, (history[-1][0] + 1) if history else 1, latest)
            if latest is not None and same_content(latest, candidate):
                return latest, True
            try:
                connection.execute('INSERT INTO issuances VALUES (?, ?, ?, ?, ?, ?)',
                                   (archive_key, candidate['revision'], run_id, candidate['issuance_id'],
                                    candidate['issued_at'], canonical_json(candidate)))
            except sqlite3.IntegrityError:
                # Another connection appended this revision first; return that
                # winner rather than surfacing a write error.
                history = self._history(connection, archive_key)
                if not history:
                    raise
                return history[-1][1], True
            return candidate, False
