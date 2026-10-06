import sqlite3, unittest
from test_fcc import fcc

class SwitchingTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
        self.c.executescript('CREATE TABLE licenses(id TEXT,call TEXT,grant_date TEXT,cancel_date TEXT,status TEXT); CREATE TABLE entities(kind TEXT,id TEXT,name TEXT);'+fcc.SWITCH_SCHEMA)
    def tearDown(self): self.c.close()
    def add(self,i,call,date,cancel='',frn='1234567890',name='SAME NAME',status='C'):
        self.c.execute('INSERT INTO licenses VALUES(?,?,?,?,?)',(str(i),call,date,cancel,status))
        self.c.execute('INSERT INTO entities VALUES(?,?,?)',('L',str(i),name))
        self.c.execute('INSERT INTO holder_identity VALUES(?,?,?,?)',('L',str(i),frn,'I'))
    def cycle(self):
        self.add(1,'N4BD','2018-11-24','2019-11-26')
        self.add(2,'KV4M','2019-11-26','2020-06-16')
        self.add(3,'N4BD','2020-06-16','2021-03-23')
        self.add(4,'KV4M','2021-03-23','2022-04-22')
    def test_cycle_and_early_returns(self):
        self.cycle();self.add(5,'N4BD','2025-01-25',frn='9999999999',name='NEW HOLDER',status='A')
        result=fcc.repeated_switching(self.c,'N4BD')['holders']
        self.assertEqual(len(result),1);self.assertEqual(result[0]['returns'],2);self.assertEqual(result[0]['early_returns'],2)
        self.assertEqual(len(result[0]['timeline']),4)
    def test_names_do_not_link_different_frns(self):
        self.cycle();self.c.execute("UPDATE holder_identity SET frn=id")
        self.assertEqual(fcc.repeated_switching(self.c,'N4BD')['holders'],[])
    def test_renewals_do_not_count(self):
        for i in range(5): self.add(i,'N4BD',f'{2010+i}-01-01')
        self.assertEqual(fcc.repeated_switching(self.c,'N4BD')['holders'],[])
    def test_single_return_does_not_flag(self):
        self.cycle();self.c.execute("DELETE FROM licenses WHERE id='4'")
        self.assertEqual(fcc.repeated_switching(self.c,'N4BD')['holders'],[])
    def test_unknown_identity_and_old_snapshot(self):
        self.add(1,'N4BD','2020-01-01',frn='')
        self.assertEqual(fcc.repeated_switching(self.c,'N4BD')['state'],'identity_unavailable')
        self.c.execute('DROP TABLE holder_identity')
        self.assertEqual(fcc.repeated_switching(self.c,'N4BD')['state'],'needs_sync')
    def test_same_day_ambiguous_assignments_do_not_flag(self):
        self.cycle();self.c.execute("UPDATE licenses SET grant_date='2020-06-16' WHERE id='4'")
        self.assertEqual(fcc.repeated_switching(self.c,'N4BD')['holders'],[])
    def test_missing_cancel_date_does_not_imply_early_return(self):
        self.cycle();self.c.execute("UPDATE licenses SET cancel_date=''")
        self.assertEqual(fcc.repeated_switching(self.c,'N4BD')['holders'][0]['early_returns'],0)
    def test_import_identity_field_positions(self):
        from test_fcc import row
        import tempfile,zipfile
        with tempfile.TemporaryDirectory() as d:
            with zipfile.ZipFile(d+'/l.zip','w') as z:
                z.writestr('EN.dat',row('EN',30,{1:'1',5:'L',22:'0012345678',23:'I'}))
                z.writestr('AM.dat',row('AM',18,{1:'1',14:'FORMER',15:'N4BD',9:'Y'}))
            with zipfile.ZipFile(d+'/l.zip') as z: fcc.import_switch_identity(self.c,z,'L')
        self.assertEqual(self.c.execute('SELECT frn FROM holder_identity').fetchone()[0],'0012345678')
        self.assertEqual(tuple(self.c.execute('SELECT relationship,previous_call,trustee FROM amateur_changes').fetchone()),('FORMER','N4BD','Y'))
    def test_clubs_and_trustees_excluded(self):
        self.cycle();self.c.execute("UPDATE holder_identity SET applicant_type='C'")
        self.assertEqual(fcc.repeated_switching(self.c,'N4BD')['holders'],[])
        self.c.execute("UPDATE holder_identity SET applicant_type='I'")
        for i in range(1,5): self.c.execute("INSERT INTO amateur_changes VALUES('L',?,'','','Y')",(str(i),))
        self.assertEqual(fcc.repeated_switching(self.c,'N4BD')['holders'],[])
    def test_release_boundary_is_not_early(self):
        self.cycle()
        self.c.execute("UPDATE licenses SET cancel_date='2018-06-15' WHERE id='1'")
        self.c.execute("UPDATE licenses SET cancel_date='2019-03-22' WHERE id='2'")
        self.assertEqual(fcc.repeated_switching(self.c,'N4BD')['holders'][0]['early_returns'],0)
    def test_invalidated_grants_excluded(self):
        self.cycle();self.c.execute("UPDATE licenses SET status='V' WHERE id='4'")
        self.assertEqual(fcc.repeated_switching(self.c,'N4BD')['holders'],[])
