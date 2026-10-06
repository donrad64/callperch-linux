"""Platform-independent Linux preferences, callsign metrics, and reminder planning."""
import datetime as dt
import json
import os
import tempfile
from pathlib import Path

ALPHABET=dict(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',[
 ('Alfa',2),('Bravo',2),('Charlie',2),('Delta',2),('Echo',2),('Foxtrot',2),('Golf',1),('Hotel',2),('India',3),('Juliett',3),('Kilo',2),('Lima',2),('Mike',1),('November',3),('Oscar',2),('Papa',2),('Quebec',2),('Romeo',3),('Sierra',3),('Tango',2),('Uniform',3),('Victor',2),('Whiskey',2),('X-ray',2),('Yankee',2),('Zulu',2),('Zero',2),('One',1),('Two',1),('Three',1),('Four',2),('Five',1),('Six',1),('Seven',2),('Eight',1),('Niner',2)]))
ULS='https://wireless2.fcc.gov/UlsEntry/licManager/login.jsp'
STATUS={'A':'Active','E':'Expired','C':'Canceled','T':'Terminated'}
CLASSES={'E':'Extra','A':'Advanced','G':'General','T':'Technician','N':'Novice'}

def data_directory():
    configured=os.environ.get('XDG_DATA_HOME','')
    base=Path(configured) if configured and Path(configured).is_absolute() else Path.home()/'.local/share'
    return base/'callperch'

def read_settings(path=None):
    path=Path(path) if path else data_directory()/'settings.json'
    try:
        value=json.loads(path.read_text())
        if not isinstance(value,dict): value={}
    except (OSError,ValueError): value={}
    watches=value.get('watches',[])
    value['watches']=sorted(set(c.strip().upper() for c in watches if isinstance(c,str) and c.strip())) if isinstance(watches,list) else []
    value['alerts']=value.get('alerts',True) is True
    value['sort']=value.get('sort','date') if value.get('sort','date') in ('date','cw') else 'date'
    value['direction']=value.get('direction','asc') if value.get('direction','asc') in ('asc','desc') else 'asc'
    value['appearance']=value.get('appearance','system') if value.get('appearance','system') in ('system','light','dark') else 'system'
    return value

def save_settings(value,path=None):
    path=Path(path) if path else data_directory()/'settings.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='settings-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)

def phonetic(call):
    call=call.strip().upper()
    if not call or any(letter not in ALPHABET for letter in call): return None
    return dict(weight=sum(ALPHABET[c][1] for c in call),spoken=' '.join(ALPHABET[c][0] for c in call))

def due_reminders(dates, now, delivered):
    if now.hour<9: return []
    tomorrow=(now.date()+dt.timedelta(days=1)).isoformat()
    return [row for row in dates if row['estimate']==tomorrow and row['call']+'|'+tomorrow not in delivered]
