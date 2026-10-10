"""Windows portability checks that also run on the development Mac."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'linux'))
import core
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import fcc

class WindowsPortTests(unittest.TestCase):
    def test_windows_data_uses_local_app_data(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(core.sys,'platform','win32'), patch.dict(os.environ,{'LOCALAPPDATA':folder,'XDG_DATA_HOME':'/ignored'}):
            self.assertEqual(core.data_directory(),Path(folder)/'CallPerch')
            core.save_settings({'watches':['K1AB']})
            self.assertEqual(core.read_settings()['watches'],['K1AB'])

    def test_relative_windows_data_setting_falls_back_to_home(self):
        with patch.object(core.sys,'platform','win32'),patch.dict(os.environ,{'LOCALAPPDATA':'relative'}):
            self.assertEqual(core.data_directory(),Path.home()/'AppData/Local/CallPerch')

    def test_read_only_database_with_unicode_and_uri_characters(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'CallPerch ü # %.sqlite'
            with sqlite3.connect(db) as connection:connection.execute('CREATE TABLE example(value)')
            with fcc.connect(db) as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM example').fetchone()[0],0)
                with self.assertRaises(sqlite3.OperationalError):connection.execute('INSERT INTO example VALUES(1)')

class FreshnessTests(unittest.TestCase):
    def test_mac_thresholds_and_same_day_dismissal(self):
        import datetime as dt
        now=dt.datetime(2026,10,10,12,tzinfo=dt.timezone.utc)
        for days in [6,7,29,30]:
            timestamp=(now-dt.timedelta(days=days)).isoformat()
            info=core.snapshot_freshness(timestamp,now)
            self.assertEqual(info is not None,days>=7)
            if info:self.assertEqual(info['very_old'],days>=30)
            self.assertIsNone(core.snapshot_freshness(timestamp,now,timestamp,now.date().isoformat()))
        self.assertIsNotNone(core.snapshot_freshness(timestamp,now,timestamp,'2026-10-09'))
        self.assertIsNone(core.snapshot_freshness('invalid',now))
        self.assertIsNone(core.snapshot_freshness((now+dt.timedelta(days=1)).isoformat(),now))

    def test_grouped_choices_sort_and_deduplicate(self):
        self.assertEqual(core.choice_label({'rank':1,'ranks':'3,1,3,2'}),'Choices 1, 2, 3')
        self.assertEqual(core.choice_label({'rank':2}),'Choice 2')

if __name__=='__main__':unittest.main()
