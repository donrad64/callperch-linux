#!/usr/bin/env python3
"""Explicitly enrich an existing snapshot from its matching FCC license archive."""
import importlib.util
import sqlite3
import sys
import zipfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('fcc',Path(__file__).resolve().parents[1]/'backend/fcc.py')
fcc=importlib.util.module_from_spec(spec);spec.loader.exec_module(fcc)
with sqlite3.connect(sys.argv[1]) as c, zipfile.ZipFile(sys.argv[2]) as z:
    # DDL and inserts are transactional; do not change the original import date.
    c.execute('BEGIN IMMEDIATE')
    for statement in fcc.SWITCH_SCHEMA.split(';'):
        if statement.strip(): c.execute(statement)
    fcc.import_switch_identity(c,z,'L')
    c.execute("INSERT OR REPLACE INTO metadata VALUES('switching_identity_source',?)",(Path(sys.argv[2]).name,))
print('Added FRN and amateur change fields. Original snapshot import date preserved.')
