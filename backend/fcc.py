#!/usr/bin/env python3
"""FCC ULS snapshot index. Standard library only; JSON command interface."""
import argparse, calendar, datetime as dt, json, os, re, sqlite3, sys, tempfile, zipfile, shutil, signal
from pathlib import Path
from functools import lru_cache
DEFAULT = Path(os.environ.get('CALLPERCH_DB', str(Path.home() / 'Library/Application Support/CallPerch/fcc.sqlite' if sys.platform=='darwin' else Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local'))) / 'CallPerch/fcc.sqlite' if sys.platform=='win32' else Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share'))) / 'callperch/fcc.sqlite')))
PENDING = ('1','2','R')  # Pending, pending/returned, returned; retain FCC codes in details.

def iso(value):
    if len(value)!=10 or value[2]!='/' or value[5]!='/': return ''
    try: return dt.date(int(value[6:10]),int(value[:2]),int(value[3:5])).isoformat()
    except ValueError: return ''

def release(value):
    if not value: return ''
    d = dt.date.fromisoformat(value)
    year = d.year + 2
    return (d.replace(year=year, day=min(d.day, calendar.monthrange(year,d.month)[1])) + dt.timedelta(days=1)).isoformat()

def shape(call):
    m = re.fullmatch(r'([A-Z]+)([0-9])([A-Z]+)',call)
    return (int(m[2]), f'{len(m[1])}x{len(m[3])}') if m else (-1,'Other')

# Same ITU dot-time convention as CallsignMetrics.swift; no trailing gap.
MORSE = dict(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
    ['.-','-...','-.-.','-..','.','..-.','--.','....','..','.---','-.-','.-..',
     '--','-.','---','.--.','--.-','.-.','...','-','..-','...-','.--','-..-','-.--','--..',
     '-----','.----','..---','...--','....-','.....','-....','--...','---..','----.']))
CHARACTER_UNITS = {letter: sum(1 if mark=='.' else 3 for mark in code)+len(code)-1 for letter,code in MORSE.items()}

@lru_cache(maxsize=8192)
def cw_weight(call):
    call=call.strip().upper()
    if not call or any(letter not in CHARACTER_UNITS for letter in call): return None
    return sum(CHARACTER_UNITS[letter] for letter in call)+3*(len(call)-1)

CW_INDEXES = ('license_cw_v2_asc','license_cw_v2_desc')
MAX_ZIP_BYTES = 1024**3
MAX_EXPANDED_BYTES = 16*1024**3
MAX_MEMBER_BYTES = 8*1024**3
MAX_LINE_BYTES = 64*1024
MAX_ROWS = 20_000_000
MAX_MEMBERS = 128
MIN_FREE_BYTES = 12*1024**3

def check_disk(db):
    directory=Path(db).parent
    directory.mkdir(parents=True,exist_ok=True)
    free=shutil.disk_usage(directory).free
    if free < MIN_FREE_BYTES:
        raise ValueError(f'FCC import needs at least 12 GiB free; {free/1024**3:.1f} GiB available')

def validate_zip(z):
    if Path(z.filename).stat().st_size > MAX_ZIP_BYTES: raise ValueError('ZIP exceeds 1 GiB limit')
    members=z.infolist()
    if len(members)>MAX_MEMBERS: raise ValueError('Too many ZIP members')
    if sum(m.file_size for m in members)>MAX_EXPANDED_BYTES: raise ValueError('ZIP expands beyond 16 GiB limit')
    seen=set()
    for m in members:
        name=m.filename.lower()
        if name in seen: raise ValueError('Duplicate ZIP member')
        seen.add(name)
        if m.file_size>MAX_MEMBER_BYTES: raise ValueError('ZIP member exceeds 8 GiB limit')
        if m.flag_bits & 1: raise ValueError('Encrypted FCC archives are unsupported')
        if m.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED): raise ValueError('Unsupported ZIP compression')
        if m.file_size and m.file_size/max(1,m.compress_size)>1000: raise ValueError('Excessive ZIP compression ratio')

def create_cw_indexes(c):
    c.execute('CREATE INDEX IF NOT EXISTS license_format ON licenses(format,region,estimate)')
    for direction,index in zip(('ASC','DESC'),CW_INDEXES):
        c.execute(f'CREATE INDEX IF NOT EXISTS {index} ON licenses(cw IS NULL,cw {direction},estimate,call,id)')

def migrate_cw(db):
    # Explicit maintenance command only; query must never migrate or write.
    with sqlite3.connect(db) as c:
        c.create_function('cw_weight',1,cw_weight,deterministic=True)
        c.execute('BEGIN IMMEDIATE')
        if 'cw' not in {r[1] for r in c.execute('PRAGMA table_info(licenses)')}:
            c.execute('ALTER TABLE licenses ADD COLUMN cw INTEGER')
        for index in ('license_cw_v1_asc','license_cw_v1_desc'): c.execute('DROP INDEX IF EXISTS '+index)
        c.execute('UPDATE licenses SET cw=cw_weight(call)')
        create_cw_indexes(c)
        c.execute("INSERT OR REPLACE INTO metadata VALUES('schema','2')")

def records(z, table, required=True):
    validate_zip(z)
    names=[n for n in z.namelist() if n.lower()==table.lower()+'.dat']
    if not names:
        if required: raise ValueError(f'Missing FCC {table}.dat')
        return
    minimum={'HD':10,'AD':11,'VC':6,'EN':21,'AM':6,'HS':6}[table]
    with z.open(names[0]) as stream:
        count=0;total=0
        while True:
            line=stream.readline(MAX_LINE_BYTES+1)
            if not line: break
            count+=1;total+=len(line)
            if len(line)>MAX_LINE_BYTES: raise ValueError(f'{table} line exceeds 64 KiB limit')
            if count>MAX_ROWS or total>MAX_MEMBER_BYTES: raise ValueError(f'{table} exceeds import limits')
            row=line.decode('latin1').rstrip('\r\n').split('|')
            if row[0]!=table or len(row)<minimum or not row[1]: raise ValueError(f'Invalid {table} record schema')
            yield row

ADDRESS_SCHEMA = """CREATE TABLE IF NOT EXISTS addresses(
    id TEXT PRIMARY KEY,street TEXT,city TEXT,state TEXT,zip TEXT,po_box TEXT,attention TEXT,address_key TEXT);
    CREATE INDEX IF NOT EXISTS address_exact ON addresses(address_key);"""

def address_key(street, city, state, postal, po_box, attention):
    # Conservative exact matching: keep punctuation, unit numbers, and full ZIP.
    parts=[' '.join(value.split()).upper() for value in (street,city,state,postal,po_box,attention)]
    if not (parts[0] or parts[4]) or not all(parts[i] for i in (1,2,3)): return ''
    return json.dumps(parts,separators=(',',':'))

def address_records(z):
    for r in records(z,'EN'):
        if len(r)>20 and r[5]=='L':
            values=[r[i].strip() for i in (15,16,17,18,19,20)]
            yield (r[1],*values,address_key(*values))

def import_addresses(db, archive):
    # Enrich an existing snapshot atomically; do not replace license/application data.
    if not Path(db).exists(): raise ValueError('No FCC snapshot to enrich')
    check_disk(db)
    with sqlite3.connect(db) as c, zipfile.ZipFile(archive) as z:
        c.executescript(ADDRESS_SCHEMA)
        c.executescript(SWITCH_SCHEMA)
        c.execute('BEGIN')
        c.execute('DELETE FROM addresses')
        c.executemany('INSERT OR REPLACE INTO addresses VALUES(?,?,?,?,?,?,?,?)',address_records(z))
        if not c.execute('SELECT count(*) FROM addresses').fetchone()[0]:
            raise ValueError('No licensee addresses found')
        c.execute("INSERT OR REPLACE INTO metadata VALUES('addresses_synced',?)",(dt.datetime.now(dt.timezone.utc).isoformat(),))

def same_address(c, licenses):
    result=dict(state='missing',address=None,matches=[])
    if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='addresses'").fetchone():
        return result
    if not licenses: return dict(result,state='unknown')
    address=c.execute('SELECT * FROM addresses WHERE id=?',(licenses[0]['id'],)).fetchone()
    if not address or not address['address_key']: return dict(result,state='incomplete',address=dict(address) if address else None)
    today=dt.date.today().isoformat()
    # Only each callsign's latest assignment: an older holder's address must not leak into a new assignment.
    matches=[dict(r) for r in c.execute(SELECT+""" JOIN addresses ad ON ad.id=l.id
        WHERE ad.address_key=? AND l.call<>?
        AND l.id=(SELECT latest.id FROM licenses latest WHERE latest.call=l.call ORDER BY latest.grant_date DESC,latest.id DESC LIMIT 1)
        ORDER BY CASE WHEN l.status='A' AND l.expires>=? THEN 0 ELSE 1 END,l.call,l.id LIMIT 501""",
        (address['address_key'],licenses[0]['call'],today))]
    for item in matches: item['current']=item['status']=='A' and item['expires']>=today
    return dict(state='ready',address={key:address[key] for key in ('street','city','state','zip','po_box','attention')},matches=matches[:500],truncated=len(matches)>500)

SWITCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS holder_identity(kind TEXT,id TEXT,frn TEXT,applicant_type TEXT,PRIMARY KEY(kind,id));
CREATE INDEX IF NOT EXISTS holder_frn ON holder_identity(kind,frn);
CREATE TABLE IF NOT EXISTS amateur_changes(kind TEXT,id TEXT,relationship TEXT,previous_call TEXT,trustee TEXT,PRIMARY KEY(kind,id));
"""

def import_switch_identity(c, z, kind):
    c.executemany('INSERT OR REPLACE INTO holder_identity VALUES(?,?,?,?)',
        ((kind,r[1],r[22].strip(),r[23].strip()) for r in records(z,'EN') if len(r)>23 and r[5]=='L'))
    c.executemany('INSERT OR REPLACE INTO amateur_changes VALUES(?,?,?,?,?)',
        ((kind,r[1],r[14].strip(),r[15].strip().upper(),r[9].strip()) for r in records(z,'AM') if len(r)>15))

def previous_callsigns(c, selected):
    result=dict(state='needs_sync',matches=[],unresolved=[])
    tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'holder_identity','amateur_changes'} <= tables: return result
    if not selected: return dict(result,state='unknown')
    identity=c.execute("SELECT frn,applicant_type FROM holder_identity WHERE kind='L' AND id=?",(selected['id'],)).fetchone()
    change=c.execute("SELECT previous_call FROM amateur_changes WHERE kind='L' AND id=?",(selected['id'],)).fetchone()
    previous=change['previous_call'] if change else ''
    valid=identity and identity['frn'] not in ('','0000000000') and identity['applicant_type']=='I'
    matches=[]
    if valid:
        matches=[dict(r) for r in c.execute(SELECT+""" JOIN holder_identity i ON i.kind='L' AND i.id=l.id
            WHERE i.frn=? AND i.applicant_type='I' AND l.call<>? AND l.grant_date<>'' AND l.grant_date<=?
            ORDER BY l.grant_date DESC,l.id DESC LIMIT 200""",(identity['frn'],selected['call'],selected['grant_date']))]
    unresolved=[previous] if previous and previous!=selected['call'] and not any(r['call']==previous for r in matches) else []
    return dict(state='ready' if valid or previous else 'identity_unavailable',matches=matches,unresolved=unresolved)

def repeated_switching(c, call):
    if not c.execute("SELECT 1 FROM sqlite_master WHERE name='holder_identity' AND type='table'").fetchone():
        return dict(state='needs_sync',holders=[])
    holders=[]
    identities=c.execute("""SELECT DISTINCT i.frn FROM licenses l CROSS JOIN holder_identity i ON i.id=l.id
        WHERE i.kind='L' AND l.call=? AND i.frn<>'' AND i.frn<>'0000000000' AND i.applicant_type='I'""",(call,)).fetchall()
    for identity in identities:
        rows=[dict(r) for r in c.execute("""SELECT l.id,l.call,l.grant_date,l.cancel_date,l.status,e.name
            FROM holder_identity i JOIN licenses l ON l.id=i.id
            LEFT JOIN entities e ON e.kind='L' AND e.id=l.id
            LEFT JOIN amateur_changes m ON m.kind='L' AND m.id=l.id
            WHERE i.kind='L' AND i.frn=? AND i.applicant_type='I'
            AND coalesce(m.trustee,'')<>'Y' AND l.status IN ('A','C','E') AND l.grant_date<>''
            ORDER BY l.grant_date,l.id LIMIT 2001""",(identity['frn'],))]
        truncated=len(rows)>2000; rows=rows[:2000]
        timeline=[]; seen={}; returns=0; early=0; ambiguous=False
        for record in rows:
            if timeline and record['grant_date']==timeline[-1]['grant_date'] and record['call']!=timeline[-1]['call']:
                ambiguous=True
            if timeline and record['call']==timeline[-1]['call']:
                # A renewal is not a switch; keep its newer cancellation information.
                timeline[-1]=dict(record,return_to_call=False,before_release=False)
                seen[record['call']]=record
                continue
            prior=seen.get(record['call']); returned=prior is not None
            before=bool(prior and prior['cancel_date'] and record['grant_date']>=prior['cancel_date'] and record['grant_date']<release(prior['cancel_date']))
            returns+=int(returned); early+=int(before)
            timeline.append(dict(record,return_to_call=returned,before_release=before)); seen[record['call']]=record
        if returns>=2 and len(timeline)>=4 and not ambiguous:
            holders.append(dict(frn=identity['frn'],name=rows[-1]['name'] or '',returns=returns,
                early_returns=early,truncated=truncated,timeline=timeline))
    return dict(state='ready' if identities else 'identity_unavailable',holders=holders)

def build(db, license_zip, application_zip, staging_path=None):
    db = Path(db); check_disk(db)
    if staging_path:
        staging=str(staging_path); fd=os.open(staging,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    else: fd, staging = tempfile.mkstemp(prefix='fcc-',suffix='.sqlite',dir=db.parent)
    os.close(fd)
    try:
        c=sqlite3.connect(staging)
        c.executescript('''
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
        CREATE TABLE licenses(id TEXT PRIMARY KEY,call TEXT,status TEXT,grant_date TEXT,expires TEXT,region INTEGER,format TEXT,estimate TEXT,cancel_date TEXT,cw INTEGER);
        CREATE TABLE entities(kind TEXT,id TEXT,name TEXT,city TEXT,state TEXT,PRIMARY KEY(kind,id));
        CREATE TABLE amateurs(kind TEXT,id TEXT,class TEXT,PRIMARY KEY(kind,id));
        CREATE TABLE applications(id TEXT PRIMARY KEY,file TEXT,purpose TEXT,status TEXT,received TEXT);
        CREATE TABLE choices(id TEXT,rank INTEGER,call TEXT,PRIMARY KEY(id,rank));
        CREATE TABLE history(kind TEXT,id TEXT,date TEXT,event TEXT);
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
        ''')
        c.executescript(ADDRESS_SCHEMA)
        c.executescript(SWITCH_SCHEMA)
        for kind, archive in [('L',license_zip),('A',application_zip)]:
            print(f'Indexing {kind} archive…',file=sys.stderr,flush=True)
            with zipfile.ZipFile(archive) as z:
                import_switch_identity(c,z,kind)
                if kind=='L':
                    def licenses():
                        for r in records(z,'HD'):
                            if len(r)<9 or r[6] not in ('HA','HV'): raise ValueError('Unexpected amateur HD schema')
                            region,form=shape(r[4]); expiration=iso(r[8])
                            # Ordinary termination estimate; special relationships/death still require review.
                            canceled=iso(r[9])
                            candidates=[d for d in [expiration,canceled if r[5]=='C' else ''] if d]
                            estimate=release(min(candidates)) if candidates and r[5] in ('A','E','C') else ''
                            yield (r[1],r[4],r[5],iso(r[7]),expiration,region,form,estimate,canceled,cw_weight(r[4]))
                    c.executemany('INSERT OR REPLACE INTO licenses VALUES(?,?,?,?,?,?,?,?,?,?)', licenses())
                else:
                    c.executemany('INSERT OR REPLACE INTO applications VALUES(?,?,?,?,?)',
                        ((r[1],r[2],r[4],r[5],iso(r[10])) for r in records(z,'AD') if len(r)>10))
                    def choices():
                        for r in records(z,'VC'):
                            if len(r)<6 or not r[4].isdigit():
                                raise ValueError('Unexpected FCC VC schema; import stopped to avoid incorrect counts')
                            # Invalid callsign strings are real historical applicant choices, not schema failures.
                            yield (r[1],int(r[4]),'|'.join(r[5:]).strip().upper())
                    c.executemany('INSERT OR REPLACE INTO choices VALUES(?,?,?)',choices())
                if kind=='L':
                    c.executemany('INSERT OR REPLACE INTO addresses VALUES(?,?,?,?,?,?,?,?)',address_records(z))
                c.executemany('INSERT OR REPLACE INTO entities VALUES(?,?,?,?,?)',
                    ((kind,r[1],r[7],r[16],r[17]) for r in records(z,'EN') if len(r)>17 and r[5]=='L'))
                c.executemany('INSERT OR REPLACE INTO amateurs VALUES(?,?,?)',
                    ((kind,r[1],r[5]) for r in records(z,'AM') if len(r)>5))
                c.executemany('INSERT INTO history VALUES(?,?,?,?)',
                    ((kind,r[1],iso(r[4]),r[5]) for r in records(z,'HS') if len(r)>5))
            c.commit()
        c.executescript('''CREATE INDEX license_call ON licenses(call); CREATE INDEX license_region ON licenses(region,estimate); CREATE INDEX license_estimate ON licenses(estimate);
        CREATE INDEX choice_call ON choices(call); CREATE INDEX history_id ON history(kind,id);
        CREATE INDEX app_status ON applications(status);
        CREATE TABLE counts AS SELECT v.call,count(DISTINCT a.id) applicants FROM choices v JOIN applications a ON a.id=v.id
        WHERE a.status IN ('1','2','R') GROUP BY v.call;
        CREATE UNIQUE INDEX count_call ON counts(call);''')
        if not c.execute('SELECT count(*) FROM licenses').fetchone()[0]: raise ValueError('No amateur licenses found')
        if not c.execute('SELECT count(*) FROM applications').fetchone()[0]: raise ValueError('No applications found')
        create_cw_indexes(c)
        c.execute("INSERT INTO metadata VALUES('schema','2')")
        c.execute('INSERT INTO metadata VALUES(?,?)',('synced',dt.datetime.now(dt.timezone.utc).isoformat()))
        c.execute('INSERT INTO metadata VALUES(?,?)',('source','FCC complete weekly archives; imported snapshot, not real-time'))
        c.commit(); c.close(); os.replace(staging,db)
    finally:
        if 'c' in locals(): c.close()
        if os.path.exists(staging): os.unlink(staging)

def connect(db):
    if not Path(db).exists(): raise ValueError('No FCC database yet. Use Sync FCC or import both FCC archives.')
    # Percent-encode the path without importing Python's networking stack.
    safe=b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~/'
    uri='file:'+''.join(chr(byte) if byte in safe else '%'+format(byte,'02X') for byte in str(Path(db).resolve()).replace('\\','/').encode('utf-8'))+'?mode=ro'
    c=sqlite3.connect(uri,uri=True); c.row_factory=sqlite3.Row; c.execute('PRAGMA query_only=ON'); c.execute('PRAGMA case_sensitive_like=ON'); return c

COUNT = "coalesce((SELECT applicants FROM counts n WHERE n.call=l.call),0)"
SELECT = f'''SELECT l.*,coalesce(e.name,'') name,coalesce(e.city,'') city,coalesce(e.state,'') state,
coalesce(m.class,'') operator_class,{COUNT} applicants,
(l.status IN ('A','E','C') AND l.estimate<>'' AND l.estimate<=date('now','localtime')
 AND l.id=(SELECT x.id FROM licenses x WHERE x.call=l.call ORDER BY x.grant_date DESC,x.id DESC LIMIT 1)
 AND NOT EXISTS (SELECT 1 FROM licenses x WHERE x.call=l.call AND x.status='A' AND x.expires>=date('now','localtime'))) available
FROM licenses l
LEFT JOIN entities e ON e.kind='L' AND e.id=l.id LEFT JOIN amateurs m ON m.kind='L' AND m.id=l.id'''

def query(db, mode, term='', region=-1, form='All', horizon=180, sort='date', direction='asc', license_id=''):
    if sort not in ('date','cw') or direction not in ('asc','desc'): raise ValueError('Invalid sort option')
    c=connect(db)
    if 'cw' not in {r[1] for r in c.execute('PRAGMA table_info(licenses)')}:
        c.close(); raise ValueError('Snapshot needs a fresh FCC sync (schema 2 required)')
    try:
        return query_connection(c,mode,term,region,form,horizon,sort,direction,license_id)
    finally: c.close()

def query_connection(c,mode,term,region,form,horizon,sort,direction,license_id=""):
    if mode=='stats':
        return dict(synced=c.execute("SELECT value FROM metadata WHERE key='synced'").fetchone()[0],
            licenses=c.execute('SELECT count(*) FROM licenses').fetchone()[0],
            applications=c.execute("SELECT count(*) FROM applications WHERE status IN ('1','2','R')").fetchone()[0],source='FCC weekly snapshot')
    if mode=='watchdates':
        dates=[]
        today=dt.date.today().isoformat()
        for call in sorted(set(v.strip().upper() for v in term.split(',') if v.strip())):
            # Same suppression rules as availability views, without the 500-result limit.
            row=c.execute("""SELECT l.call,l.estimate FROM licenses l WHERE l.call=?
                AND l.status IN ('A','E','C') AND l.estimate>?
                AND NOT EXISTS (SELECT 1 FROM licenses x WHERE x.call=l.call AND x.status='A' AND x.expires>=?)
                AND NOT EXISTS (SELECT 1 FROM licenses x WHERE x.call=l.call AND x.grant_date>l.grant_date)
                ORDER BY l.grant_date DESC,l.estimate DESC LIMIT 1""",(call,today,today)).fetchone()
            if row: dates.append(dict(row))
        return dates
    if mode=='detail':
        call=term.upper().strip()
        licenses=[dict(r) for r in c.execute(SELECT+' WHERE l.call=? ORDER BY l.grant_date DESC,l.id DESC LIMIT 200',(call,))]
        if license_id:
            selected_row=c.execute(SELECT+' WHERE l.call=? AND l.id=?',(call,license_id)).fetchone()
            selected=dict(selected_row) if selected_row else None
            if selected is None: raise ValueError('Selected license record is not present for this callsign')
            licenses=[selected]+[record for record in licenses if record['id']!=license_id]
        apps=[dict(r) for r in c.execute('''SELECT a.*,min(v.rank) rank,group_concat(DISTINCT v.rank) ranks,coalesce(e.name,'') name FROM choices v
        JOIN applications a ON a.id=v.id LEFT JOIN entities e ON e.kind='A' AND e.id=a.id
        WHERE v.call=? GROUP BY a.id ORDER BY a.received DESC,a.id LIMIT 200''',(call,))]
        history=[dict(r) for r in c.execute('''SELECT h.* FROM history h WHERE (h.kind='L' AND h.id IN (SELECT id FROM licenses WHERE call=?))
        OR (h.kind='A' AND h.id IN (SELECT id FROM choices WHERE call=?)) ORDER BY h.date DESC LIMIT 200''',(call,call))]
        if license_id: history=[event for event in history if event['kind']!='L' or event['id']==license_id]
        return dict(licenses=licenses,applications=apps,history=history,same_address=same_address(c,licenses),switching=repeated_switching(c,call),previous_callsigns=previous_callsigns(c,licenses[0] if licenses else None))
    clauses=[]; args=[]
    if mode=='search':
        term=term.strip().upper()
        if not term: return []
        clauses.append("l.call LIKE ? ESCAPE '\\'" if any(ch.isdigit() for ch in term) else "(l.call LIKE ? ESCAPE '\\' OR upper(e.name) LIKE ? ESCAPE '\\')")
        escaped=term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        args.extend([escaped+'%'] if any(ch.isdigit() for ch in term) else [escaped+'%','%'+escaped+'%'])
    elif mode in ('upcoming','available'):
        today=dt.date.today(); end=today+dt.timedelta(days=horizon)
        clauses += ["l.status IN ('A','E','C')",'l.estimate>=?','l.estimate<=?',"NOT EXISTS (SELECT 1 FROM licenses x WHERE x.call=l.call AND x.status='A' AND x.expires>=?)"]
        args += [today.isoformat() if mode=='upcoming' else '1900-01-01',end.isoformat() if mode=='upcoming' else today.isoformat(),today.isoformat()]
        # Reassignment to another license overrides the older record's estimate.
        clauses.append('NOT EXISTS (SELECT 1 FROM licenses x WHERE x.call=l.call AND x.grant_date>l.grant_date)')
    elif mode=='contested':
        filters=[]; params=[]
        if region>=0: filters.append("n.call GLOB ?"); params.append('*'+str(region)+'*')
        results=[]
        source='counts'
        if term:
            date=dt.date.fromisoformat(term).isoformat()
            source="(SELECT v.call,count(DISTINCT a.id) applicants FROM choices v JOIN applications a ON a.id=v.id WHERE a.status IN ('1','2','R') AND a.received=? GROUP BY v.call)"
            params.insert(0,date)
        sql="SELECT n.call,n.applicants,l.* FROM "+source+" n LEFT JOIN licenses l ON l.id=(SELECT x.id FROM licenses x WHERE x.call=n.call ORDER BY x.grant_date DESC,x.id DESC LIMIT 1)"
        if filters: sql+=' WHERE '+' AND '.join(filters)
        for r in c.execute(sql+' ORDER BY n.applicants DESC,n.call',params):
            digit,pattern=shape(r['call'])
            if form!='All' and pattern!=form: continue
            if r['id']:
                item=dict(c.execute(SELECT+' WHERE l.id=?',(r['id'],)).fetchone())
            else:
                item=dict(id='unassigned:'+r['call'],call=r['call'],status='Unknown',grant_date='',expires='',region=digit,format=pattern,estimate='',name='No license record in snapshot',city='',state='',operator_class='',applicants=r['applicants'])
            item['applicants']=r['applicants']
            results.append(item)
            if len(results)==500: break
        return results
    else: raise ValueError('Unknown query')
    if region>=0: clauses.append('l.region=?'); args.append(region)
    if form!='All': clauses.append('l.format=?'); args.append(form)
    if mode in ('upcoming','available'):
        order=('l.cw IS NULL,l.cw '+direction+',l.estimate' if sort=='cw'
               else 'l.estimate '+direction+',l.cw IS NULL,l.cw')+',l.call,l.id'
    else: order='applicants DESC,l.call,l.id'
    # Sort the full matching dataset before selecting the 500 rows shown in the app.
    selection=SELECT
    if sort=='cw' and mode=='available' and region<0 and form=='All':
        # Traverse weights in order, stopping after 500 eligible rows instead of sorting hundreds of thousands.
        index=CW_INDEXES[direction=='desc']
        selection=SELECT.replace('FROM licenses l','FROM licenses l INDEXED BY '+index)
    elif mode=='upcoming' and region<0:
        selection=SELECT.replace('FROM licenses l','FROM licenses l INDEXED BY license_estimate')
    return [dict(r) for r in c.execute(selection+' WHERE '+' AND '.join(clauses)+' ORDER BY '+order+' LIMIT 500',args)]

def main():
    def interrupted(signum, frame): raise KeyboardInterrupt("FCC operation canceled")
    signal.signal(signal.SIGTERM, interrupted)
    p=argparse.ArgumentParser(); p.add_argument('--db',default=str(DEFAULT)); p.add_argument('--bundled-fallback',action='store_true'); p.add_argument('--staging'); sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('migrate-cw')
    imp=sub.add_parser('import'); imp.add_argument('licenses'); imp.add_argument('applications')
    addr=sub.add_parser('import-addresses'); addr.add_argument('archive')
    q=sub.add_parser('query'); q.add_argument('mode',choices=['stats','search','upcoming','available','contested','detail','watchdates']); q.add_argument('--license-id',default=''); q.add_argument('--term',default=''); q.add_argument('--region',type=int,default=-1); q.add_argument('--format',default='All'); q.add_argument('--horizon',type=int,default=180); q.add_argument('--sort',choices=['date','cw'],default='date'); q.add_argument('--direction',choices=['asc','desc'],default='asc')
    a=p.parse_args()
    try:
        if a.command=='migrate-cw': migrate_cw(a.db); result={'ok':True}
        elif a.command=='import-addresses': import_addresses(a.db,a.archive); result={'ok':True}
        elif a.command=='import': build(a.db,a.licenses,a.applications,a.staging); result={'ok':True}
        else:
            query_db = a.db
            bundled = Path(__file__).with_name('fcc.sqlite')
            if (a.bundled_fallback or query_db == str(DEFAULT)) and not Path(query_db).exists() and bundled.exists(): query_db = str(bundled)
            result=query(query_db,a.mode,a.term,a.region,a.format,a.horizon,a.sort,a.direction,a.license_id)
        print(json.dumps(result))
    except KeyboardInterrupt:
        print(json.dumps({"error":"FCC operation canceled; previous snapshot preserved"})); sys.exit(1)
    except Exception as e: print(json.dumps({'error':str(e)})); sys.exit(1)
if __name__=='__main__': main()
