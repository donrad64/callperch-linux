"""Optional user-session reminder runner, invoked by the packaged systemd timer."""
import fcntl
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path
from core import ULS,data_directory,read_settings,save_settings,due_reminders

def run(fcc):
    directory=data_directory();directory.mkdir(parents=True,exist_ok=True)
    # The open app and user timer may run together; one process owns delivery.
    with (directory/'reminders.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return 0
        return _run(fcc)

def _run(fcc):
    settings=read_settings();db=data_directory()/'fcc.sqlite'
    if not settings['alerts'] or not settings['watches'] or not db.exists(): return 0
    if sys.platform!='linux' or not shutil.which('notify-send'):
        print('Desktop notifications require Linux and libnotify (notify-send).',file=sys.stderr);return 1
    dates=fcc.query(db,'watchdates',term=','.join(settings['watches']))
    now=dt.datetime.now().astimezone()
    state_path=data_directory()/'reminders.json'
    state=read_settings(state_path);delivered=state.get('delivered',[])
    if not isinstance(delivered,list): delivered=[]
    for row in due_reminders(dates,now,delivered):
        command=['notify-send','--app-name=CallPerch','--expire-time=30000','--action=open=Open FCC ULS','--wait',
                 row['call']+' may be available tomorrow',
                 'Estimated apply date: '+row['estimate']+'. Verify eligibility and availability with the FCC.']
        try:
            result=subprocess.run(command,capture_output=True,text=True,timeout=45)
            if result.returncode: print(result.stderr,file=sys.stderr);continue
            if result.stdout.strip()=='open': subprocess.Popen(['xdg-open',ULS],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            # notify-send has posted its banner and is waiting for an action; do not repost hourly.
            pass
        delivered.append(row['call']+'|'+row['estimate'])
        state['delivered']=delivered[-512:];save_settings(state,state_path)
    return 0
