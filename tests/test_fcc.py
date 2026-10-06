import importlib.util, json, sqlite3, tempfile, unittest, zipfile, hashlib
from unittest.mock import patch
from pathlib import Path
spec=importlib.util.spec_from_file_location('fcc',Path(__file__).parents[1]/'backend/fcc.py'); fcc=importlib.util.module_from_spec(spec); spec.loader.exec_module(fcc)

def row(table,length,values):
    fields=['']*length; fields[0]=table
    for k,v in values.items(): fields[k]=v
    return '|'.join(fields)+'\n'

class FCCTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.db=self.root/'fcc.sqlite'
        l={'HD':row('HD',59,{1:'100',4:'K1AB',5:'E',6:'HA',7:'01/01/2014',8:'01/01/2024'}),
           'EN':row('EN',30,{1:'100',5:'L',7:'TEST OPERATOR',16:'BOSTON',17:'MA'}),
           'AM':row('AM',18,{1:'100',5:'E'}),'HS':row('HS',6,{1:'100',4:'01/01/2024',5:'EXP'})}
        a={'AD':''.join(row('AD',31,{1:str(i),2:str(i),4:'MD',5:status,10:'01/02/2026'}) for i,status in [(1,'1'),(2,'2'),(3,'G')]),
           'VC':row('VC',6,{1:'1',2:'1',4:'1',5:'K1AB'})+row('VC',6,{1:'1',2:'1',4:'2',5:'K1AB'})+row('VC',6,{1:'2',2:'2',4:'1',5:'K1AB'})+row('VC',6,{1:'3',2:'3',4:'1',5:'K1AB'}),
           'EN':'','AM':'','HS':''}
        for name,data in [('l',l),('a',a)]:
            with zipfile.ZipFile(self.root/(name+'.zip'),'w') as z:
                for table,content in data.items(): z.writestr(table+'.dat',content)
        fcc.build(self.db,self.root/'l.zip',self.root/'a.zip')
    def connection(self):
        c=sqlite3.connect(self.db)
        c.create_function('cw_weight',1,fcc.cw_weight,deterministic=True)
        return c
    def tearDown(self): self.temp.cleanup()
    def test_leap_date(self): self.assertEqual(fcc.release('2024-02-29'),'2026-03-01')
    def test_counts_distinct_pending_applications(self):
        result=fcc.query(self.db,'search','k1ab'); self.assertEqual(result[0]['applicants'],2)
        self.assertEqual(result[0]['name'],'TEST OPERATOR'); self.assertEqual(result[0]['estimate'],'2026-01-02')
    def test_region_and_shape(self):
        self.assertEqual(fcc.shape('AE7Q'),(7,'2x1'))
        self.assertEqual(fcc.query(self.db,'search','K1AB',region=2),[])
    def test_detail_retains_final_application(self):
        self.assertEqual(len(fcc.query(self.db,'detail','K1AB')['applications']),4)
    def test_search_treats_wildcards_literally(self): self.assertEqual(fcc.query(self.db,'search','%'),[])
    def test_failed_import_preserves_snapshot(self):
        with zipfile.ZipFile(self.root/'bad.zip','w') as z: z.writestr('HD.dat','HD|broken\n')
        with self.assertRaises(ValueError): fcc.build(self.db,self.root/'bad.zip',self.root/'a.zip')
        self.assertEqual(fcc.query(self.db,'stats')['licenses'],1)
    def test_unassigned_calls_appear_in_application_view(self):
        c=self.connection()
        c.execute("INSERT INTO choices VALUES('1',3,'N7ZZ')")
        c.execute("INSERT INTO counts VALUES('N7ZZ',1)"); c.commit(); c.close()
        rows=fcc.query(self.db,'contested',region=7)
        self.assertEqual(rows[0]['call'],'N7ZZ'); self.assertEqual(rows[0]['applicants'],1)
    def test_receipt_date_filter(self):
        self.assertEqual(fcc.query(self.db,'contested',term='2026-01-02')[0]['applicants'],2)
        self.assertEqual(fcc.query(self.db,'contested',term='2026-01-03'),[])
        with self.assertRaises(ValueError): fcc.query(self.db,'contested',term='yesterday')
    def test_invalid_requested_call_preserved(self):
        with zipfile.ZipFile(self.root/'a.zip') as z: tables={n:z.read(n) for n in z.namelist()}
        tables['VC.dat']=row('VC',6,{1:'1',4:'1',5:'NOAHY'}).encode()
        with zipfile.ZipFile(self.root/'a.zip','w') as z:
            for name,data in tables.items(): z.writestr(name,data)
        fcc.build(self.db,self.root/'l.zip',self.root/'a.zip')
        self.assertEqual(fcc.query(self.db,'detail','NOAHY')['applications'][0]['rank'],1)
    def test_canceled_call_uses_earlier_date(self):
        with zipfile.ZipFile(self.root/'l.zip') as z: tables={n:z.read(n) for n in z.namelist()}
        tables['HD.dat']=row('HD',59,{1:'100',4:'K1AB',5:'C',6:'HV',7:'01/01/2014',8:'01/01/2034',9:'01/01/2024'}).encode()
        with zipfile.ZipFile(self.root/'l.zip','w') as z:
            for name,data in tables.items(): z.writestr(name,data)
        fcc.build(self.db,self.root/'l.zip',self.root/'a.zip')
        result=fcc.query(self.db,'search','K1AB')[0]
        self.assertEqual(result['estimate'],'2026-01-02');self.assertEqual(result['cancel_date'],'2024-01-01')
    def test_available_excludes_future_release(self):
        c=self.connection()
        c.execute("UPDATE licenses SET estimate='2099-01-01'"); c.commit(); c.close()
        self.assertEqual(fcc.query(self.db,'available'),[])
    def seed_sort_rows(self, rows):
        c=self.connection()
        c.execute("UPDATE licenses SET estimate='2099-01-01'")
        for identifier,call,estimate in rows:
            digit,pattern=fcc.shape(call)
            c.execute("INSERT INTO licenses(id,call,status,grant_date,expires,region,format,estimate,cancel_date) VALUES(?,?, 'E','2000-01-01','2008-01-01',?,?,?,'')",(identifier,call,digit,pattern,estimate))
        c.execute('UPDATE licenses SET cw=cw_weight(call)'); c.commit(); c.close()
    def test_weight_convention_matches_display(self):
        self.assertEqual(fcc.cw_weight('AE7Q'),41)
        self.assertEqual(fcc.cw_weight('PARIS'),43)
        self.assertEqual(fcc.cw_weight('0'),19)
        self.assertIsNone(fcc.cw_weight('K1?'))
    def test_cw_sort_both_directions(self):
        self.seed_sort_rows([('x','W0ZZ','2020-01-01'),('y','N5EE','2021-01-01'),('z','K1AC','2020-01-01')])
        self.assertEqual([r['call'] for r in fcc.query(self.db,'available',sort='cw')],['N5EE','K1AC','W0ZZ'])
        self.assertEqual([r['call'] for r in fcc.query(self.db,'available',sort='cw',direction='desc')],['W0ZZ','K1AC','N5EE'])
    def test_date_sort_and_weight_tiebreaker(self):
        self.seed_sort_rows([('x','W0ZZ','2020-01-01'),('y','N5EE','2021-01-01'),('z','K1AC','2020-01-01')])
        self.assertEqual([r['call'] for r in fcc.query(self.db,'available')],['K1AC','W0ZZ','N5EE'])
        self.assertEqual([r['call'] for r in fcc.query(self.db,'available',direction='desc')],['N5EE','K1AC','W0ZZ'])
    def test_upcoming_sort_retains_region_and_window_filters(self):
        tomorrow=(fcc.dt.date.today()+fcc.dt.timedelta(days=1)).isoformat()
        later=(fcc.dt.date.today()+fcc.dt.timedelta(days=20)).isoformat()
        self.seed_sort_rows([('x','W0ZZ',tomorrow),('y','N5EE',later),('z','K5AB',tomorrow)])
        self.assertEqual([r['call'] for r in fcc.query(self.db,'upcoming',region=5,horizon=30,sort='cw')],['N5EE','K5AB'])
        self.assertEqual([r['call'] for r in fcc.query(self.db,'upcoming',region=5,horizon=10,sort='cw')],['K5AB'])
    def test_sort_runs_before_result_limit(self):
        calls=['W0'+a+b for a in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' for b in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'][:501]
        self.seed_sort_rows([(str(i+1000),call,'2010-01-01') for i,call in enumerate(calls)]+[('best','N5EE','2020-01-01')])
        rows=fcc.query(self.db,'available',sort='cw')
        self.assertEqual(len(rows),500); self.assertEqual(rows[0]['call'],'N5EE')
        self.assertEqual(fcc.query(self.db,'available',direction='desc')[0]['call'],'N5EE')
    def test_queries_never_change_snapshot(self):
        before=hashlib.sha256(self.db.read_bytes()).digest()
        for mode in ['stats','available','upcoming','detail','watchdates','search','contested']:
            fcc.query(self.db,mode,term='K1AB' if mode not in ('contested',) else '',sort='cw')
        self.assertEqual(before,hashlib.sha256(self.db.read_bytes()).digest())
        c=fcc.connect(self.db)
        with self.assertRaises(sqlite3.OperationalError): c.execute('DELETE FROM licenses')
        c.close()
    def test_unknown_weight_sorts_last_in_both_directions(self):
        self.seed_sort_rows([('x','W0ZZ','2020-01-01'),('y','N5EE','2021-01-01'),('z','N?','2020-01-01')])
        for direction in ['asc','desc']:
            self.assertEqual(fcc.query(self.db,'available',sort='cw',direction=direction)[-1]['call'],'N?')
    def test_sort_does_not_create_a_missing_snapshot(self):
        missing=self.root/'missing.sqlite'
        with self.assertRaises(ValueError): fcc.query(missing,'available',sort='cw')
        self.assertFalse(missing.exists())
    def test_invalid_sort_options_rejected(self):
        with self.assertRaises(ValueError): fcc.query(self.db,'available',sort='bad')
        with self.assertRaises(ValueError): fcc.query(self.db,'available',direction='bad')
    def test_watch_dates_are_exact_and_deduplicated(self):
        c=self.connection()
        c.execute("UPDATE licenses SET estimate='2099-01-02'"); c.commit(); c.close()
        self.assertEqual(fcc.query(self.db,'watchdates',' k1ab,K1AB,UNKNOWN'),[dict(call='K1AB',estimate='2099-01-02')])
    def test_watch_dates_exclude_superseded_and_currently_held_calls(self):
        c=self.connection()
        c.execute("UPDATE licenses SET estimate='2099-01-02'")
        c.execute("INSERT INTO licenses(id,call,status,grant_date,expires,region,format,estimate,cancel_date) VALUES('101','K1AB','A','2025-01-01','2095-01-01',1,'1x2','2097-01-02','')"); c.commit(); c.close()
        self.assertEqual(fcc.query(self.db,'watchdates','K1AB'),[])
    def test_watch_dates_do_not_remind_for_missing_estimates(self):
        c=self.connection()
        c.execute("UPDATE licenses SET estimate=''"); c.commit(); c.close()
        self.assertEqual(fcc.query(self.db,'watchdates','K1AB'),[])
    def test_active_reassignment_excludes_old_estimate(self):
        c=self.connection()
        c.execute("INSERT INTO licenses(id,call,status,grant_date,expires,region,format,estimate,cancel_date) VALUES('101','K1AB','A','2025-01-01','2035-01-01',1,'1x2','2037-01-02','')"); c.commit(); c.close()
        self.assertEqual(fcc.query(self.db,'upcoming',horizon=3650),[])
    def seed_addresses(self):
        c=self.connection()
        c.execute("UPDATE licenses SET status='A',expires='2099-01-01'")
        street='123 MAIN ST APT 1'
        for identifier,call,status,expiry,address in [
            ('100','K1AB','A','2099-01-01',street),
            ('101','N1AA','A','2099-01-01',' 123 main st   apt 1 '),
            ('102','N1BB','A','2099-01-01','123 MAIN ST APT 2'),
            ('103','N1CC','E','2020-01-01',street),
            ('104','N1DD','A','2099-01-01',street),
            ('105','N1EE','A','2000-01-01',street)]:
            if identifier!='100':
                c.execute("INSERT INTO licenses(id,call,status,grant_date,expires,region,format,estimate,cancel_date) VALUES(?,?,?,'2020-01-01',?,1,'1x2','','')",(identifier,call,status,expiry))
            values=(address,'BOSTON','MA','02101','','')
            c.execute('INSERT OR REPLACE INTO addresses VALUES(?,?,?,?,?,?,?,?)',(identifier,*values,fcc.address_key(*values)))
        # N1DD has since been assigned to a new license at a different address.
        c.execute("INSERT INTO licenses(id,call,status,grant_date,expires,region,format,estimate,cancel_date) VALUES('106','N1DD','A','2025-01-01','2099-01-01',1,'1x2','','')")
        values=('456 OTHER ST','BOSTON','MA','02101','','')
        c.execute('INSERT OR REPLACE INTO addresses VALUES(?,?,?,?,?,?,?,?)',('106',*values,fcc.address_key(*values)))
        c.commit(); c.close()
    def test_same_address_exact_and_historical(self):
        self.seed_addresses()
        result=fcc.query(self.db,'detail','K1AB')['same_address']
        self.assertEqual(result['state'],'ready')
        self.assertEqual([r['call'] for r in result['matches']],['N1AA','N1CC','N1EE'])
        self.assertEqual([r['current'] for r in result['matches']],[True,False,False])
        self.assertEqual(result['address']['street'],'123 MAIN ST APT 1')
    def test_address_keys_do_not_merge_units_postal_or_attention(self):
        base=('123 MAIN ST APT 1','BOSTON','MA','02101','','')
        for position,replacement in [(0,'123 MAIN ST APT 2'),(1,'CAMBRIDGE'),(2,'NH'),(3,'021010001'),(4,'12'),(5,'UNIT 2')]:
            changed=list(base);changed[position]=replacement
            self.assertNotEqual(fcc.address_key(*base),fcc.address_key(*changed))
        self.assertEqual(fcc.address_key(*base),fcc.address_key(' 123 main st apt 1 ',' boston ','ma','02101','',''))
        self.assertNotEqual(fcc.address_key(*base),fcc.address_key('123 MAIN STREET APT 1',*base[1:]))
    def test_incomplete_addresses_never_group(self):
        self.assertEqual(fcc.query(self.db,'detail','K1AB')['same_address']['state'],'incomplete')
        for values in [('', 'BOSTON','MA','02101','',''),('123 ST','','MA','02101','',''),('123 ST','BOSTON','MA','','','')]:
            self.assertEqual(fcc.address_key(*values),'')
        self.assertTrue(fcc.address_key('','BOSTON','MA','02101','42',''))
    def test_legacy_snapshot_requests_sync_and_unknown_call_is_handled(self):
        self.assertEqual(fcc.query(self.db,'detail','UNKNOWN')['same_address']['state'],'unknown')
        c=self.connection(); c.execute('DROP TABLE addresses'); c.commit();c.close()
        self.assertEqual(fcc.query(self.db,'detail','K1AB')['same_address']['state'],'missing')
        self.assertEqual(fcc.query(self.db,'detail','K1AB')['licenses'][0]['call'],'K1AB')
    def test_address_import_parses_fcc_en_and_preserves_snapshot(self):
        with zipfile.ZipFile(self.root/'addresses.zip','w') as z:
            z.writestr('EN.dat',row('EN',30,{1:'100',5:'L',15:'123 MAIN ST',16:'BOSTON',17:'MA',18:'02101',19:'42',20:'APT 1'})+row('EN',30,{1:'100',5:'C',15:'IGNORE CONTACT'}))
        fcc.import_addresses(self.db,self.root/'addresses.zip')
        result=fcc.query(self.db,'detail','K1AB')
        self.assertEqual(result['same_address']['address']['street'],'123 MAIN ST')
        self.assertEqual(result['same_address']['address']['po_box'],'42')
        self.assertEqual(result['same_address']['address']['attention'],'APT 1')
        self.assertEqual(len(result['applications']),4)
        with zipfile.ZipFile(self.root/'empty.zip','w') as z: z.writestr('EN.dat','')
        with self.assertRaises(ValueError): fcc.import_addresses(self.db,self.root/'empty.zip')
        self.assertEqual(fcc.query(self.db,'detail','K1AB')['same_address']['address']['street'],'123 MAIN ST')
    def test_full_snapshot_import_retains_addresses(self):
        with zipfile.ZipFile(self.root/'l.zip') as z: tables={n:z.read(n) for n in z.namelist()}
        tables['EN.dat']=row('EN',30,{1:'100',5:'L',7:'TEST OPERATOR',15:'123 MAIN ST',16:'BOSTON',17:'MA',18:'02101'}).encode()
        with zipfile.ZipFile(self.root/'l.zip','w') as z:
            for name,data in tables.items(): z.writestr(name,data)
        fcc.build(self.db,self.root/'l.zip',self.root/'a.zip')
        self.assertEqual(fcc.query(self.db,'detail','K1AB')['same_address']['state'],'ready')
    def test_read_only_uri_handles_reserved_characters(self):
        path=self.root/'file ?#é.sqlite';path.write_bytes(self.db.read_bytes())
        self.assertEqual(fcc.query(path,'search','K1AB')[0]['call'],'K1AB')
    def test_parser_fixtures(self):
        root=Path(__file__).parent/'fixtures'
        with zipfile.ZipFile(self.root/'fixture.zip','w') as z:
            for table in ('HD','EN','AM','HS','AD','VC'):z.writestr(table+'.dat',(root/(table+'.dat')).read_bytes())
        with zipfile.ZipFile(self.root/'fixture.zip') as z:
            self.assertEqual(next(fcc.records(z,'EN'))[7],'SAMPLE OPERATOR')
            self.assertEqual(next(fcc.records(z,'VC'))[5],'N0EX')
            self.assertEqual(next(fcc.address_records(z))[1],'123 EXAMPLE ST UNIT 2')
    def test_limits_and_malformed_rows_preserve_snapshot(self):
        before=hashlib.sha256(self.db.read_bytes()).digest()
        for content in [b'HD|1',b'HD|'+b'x'*70_000]:
            with zipfile.ZipFile(self.root/'bad.zip','w') as z:z.writestr('HD.dat',content)
            with self.assertRaises(ValueError):fcc.build(self.db,self.root/'bad.zip',self.root/'a.zip')
        for limit,value in [('MAX_ZIP_BYTES',1),('MAX_EXPANDED_BYTES',1),('MAX_ROWS',0),('MAX_MEMBER_BYTES',1),('MAX_MEMBERS',0)]:
            with patch.object(fcc,limit,value),self.assertRaises(ValueError):fcc.build(self.db,self.root/'l.zip',self.root/'a.zip')
        with patch.object(fcc,'MIN_FREE_BYTES',10**20),self.assertRaises(ValueError):fcc.build(self.db,self.root/'l.zip',self.root/'a.zip')
        self.assertEqual(before,hashlib.sha256(self.db.read_bytes()).digest())
        self.assertEqual(list(self.root.glob('fcc-*.sqlite')),[])
    def test_duplicate_and_unsupported_zip_members(self):
        with zipfile.ZipFile(self.root/'bad.zip','w') as z:
            z.writestr('HD.dat','');z.writestr('hd.dat','')
        with zipfile.ZipFile(self.root/'bad.zip') as z,self.assertRaises(ValueError):list(fcc.records(z,'HD'))
        with zipfile.ZipFile(self.root/'bad.zip','w',compression=zipfile.ZIP_BZIP2) as z:z.writestr('HD.dat','HD|1')
        with zipfile.ZipFile(self.root/'bad.zip') as z,self.assertRaises(ValueError):list(fcc.records(z,'HD'))
    def test_explicit_migration_and_fail_closed_legacy_query(self):
        c=self.connection()
        for index in fcc.CW_INDEXES:c.execute('DROP INDEX '+index)
        c.execute('ALTER TABLE licenses DROP COLUMN cw');c.commit();c.close()
        before=hashlib.sha256(self.db.read_bytes()).digest()
        with self.assertRaisesRegex(ValueError,'schema 2'):fcc.query(self.db,'available',sort='cw')
        self.assertEqual(before,hashlib.sha256(self.db.read_bytes()).digest())
        fcc.migrate_cw(self.db)
        self.assertEqual(fcc.query(self.db,'search','K1AB')[0]['cw'],fcc.cw_weight('K1AB'))
if __name__=='__main__': unittest.main()
