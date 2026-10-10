"""Local callsign comparison, using the same fixed scales as the Mac app."""
import copy
import csv
import re
import uuid
from pathlib import Path
import fcc
from core import phonetic, read_settings, save_settings, data_directory

CATEGORIES = [('characters','Character count'),('cwTime','CW transmission time'),('phonetics','Phonetic syllables'),('appearance','Visual appearance'),('letterClarity','Letter clarity'),('phoneticClarity','Phonetic clarity'),('cwEmphasis','CW ending'),('ssbEmphasis','SSB ending'),('rhythm','CW rhythm')]
MEASURED = {key for key,_ in CATEGORIES[:3]}
TITLES = dict(CATEGORIES)

def normalize(text):
    call = text.strip().upper() if isinstance(text,str) else ''
    return call if re.fullmatch(r'[A-Z]{1,2}[0-9][A-Z]{1,3}',call) else None

def preset(name='Balanced'):
    weights = dict.fromkeys(TITLES,1)
    if name=='CW': weights.update(cwTime=3,rhythm=3,cwEmphasis=2,phonetics=0,phoneticClarity=0,ssbEmphasis=0)
    if name=='SSB': weights.update(phonetics=3,phoneticClarity=3,ssbEmphasis=2,cwTime=0,rhythm=0,cwEmphasis=0)
    return weights

def new_workspace():
    return dict(id=str(uuid.uuid4()),name='My comparison',analysisVersion=1,candidates=[],weights=preset(),wpm=20,initials='')

def clean_workspace(value):
    result=new_workspace()
    if not isinstance(value,dict): return result
    for key in ('id','name','initials'):
        if isinstance(value.get(key),str): result[key]=value[key][:200]
    if type(value.get('wpm')) is int: result['wpm']=min(50,max(5,value['wpm']))
    weights=value.get('weights',{})
    if isinstance(weights,dict):
        for key in TITLES:
            if type(weights.get(key)) is int: result['weights'][key]=min(3,max(0,weights[key]))
    candidates=value.get('candidates',[])
    if isinstance(candidates,list):
        for item in candidates:
            if not isinstance(item,dict): continue
            call=normalize(item.get('call'))
            if not call or any(c['call']==call for c in result['candidates']): continue
            ratings=item.get('ratings',{})
            ratings={k:v for k,v in ratings.items() if k in TITLES and k not in MEASURED and type(v) is int and 1<=v<=10} if isinstance(ratings,dict) else {}
            result['candidates'].append(dict(call=call,ratings=ratings))
            if len(result['candidates'])==10: break
    return result

def analysis(call):
    morse='   '.join(fcc.MORSE[c] for c in call)
    spoken=phonetic(call)
    return dict(characters=len(call),cwTime=fcc.cw_weight(call),phonetics=spoken['weight'],morse=morse,spoken=spoken['spoken'],elements=sum(c in '.-' for c in morse),signal=sum(1 if c=='.' else 3 if c=='-' else 0 for c in morse))

def guidance(call):
    notes=[]
    confusing=sorted(set(call)&set('BCDEGPTVZ'))
    if confusing: notes.append('Spoken English letter names worth checking: '+', '.join(confusing)+'. Try phonetics in noisy conditions.')
    if fcc.MORSE[call[-1]].endswith('-'): notes.append('Ends in a dah, a CW preference used by some operators.')
    if call.endswith('K'): notes.append('Final K also means “go ahead” in CW; listen for whether the ending feels distinct.')
    if call[-1] in 'BDGKPT': notes.append('Ends with a stop consonant in the English letter name. Listen before rating its SSB ending.')
    if set(call)&set('01IO'): notes.append('Check 0/O and 1/I in your preferred font and visual preview.')
    notes.append('These are listening and appearance prompts, not measured copy accuracy or eligibility checks.')
    return notes

def scored_categories(workspace):
    return [key for key in TITLES if workspace['weights'][key]>0 and (key in MEASURED or workspace['candidates'] and all(1<=c['ratings'].get(key,0)<=10 for c in workspace['candidates']))]

def pending_categories(workspace):
    scored=scored_categories(workspace)
    return [key for key in TITLES if workspace['weights'][key]>0 and key not in scored]

def score(workspace,candidate):
    metrics=analysis(candidate['call']);total=0;divisor=0
    ranges={'characters':(4,6),'cwTime':(25,100),'phonetics':(4,18)}
    for key in scored_categories(workspace):
        if key in MEASURED:
            low,high=ranges[key];value=min(10,max(1,1+9*(metrics[key]-low)/(high-low)))
        else: value=candidate['ratings'][key]
        weight=workspace['weights'][key];total+=value*weight;divisor+=weight
    return total/divisor if divisor else None

def ranked(workspace):
    return sorted(workspace['candidates'],key=lambda c:(score(workspace,c) if score(workspace,c) is not None else float('inf'),c['call']))

def explanation(workspace,candidate):
    call=candidate['call'];a=analysis(call);scored=scored_categories(workspace);personal=sum(k not in MEASURED for k in scored)
    text=f"{len(call)} characters, {a['cwTime']} CW time units, and {a['phonetics']} phonetic syllables. This comparison uses {len(scored)-personal} measured categories and {personal} personal ratings, weighted by your priorities."
    match=workspace['initials'].strip().upper()
    if match and match in call: text+=' It includes your requested letters '+match+'.'
    return text

class Library:
    def __init__(self,path=None):
        self.path=Path(path) if path else data_directory()/'comparisons.json'
        data=read_settings(self.path);self.workspace=clean_workspace(data.get('draft'))
        saved=data.get('saved',[])
        self.saved=[clean_workspace(w) for w in saved if isinstance(w,dict)] if isinstance(saved,list) else []
    def persist(self): save_settings(dict(draft=self.workspace,saved=self.saved),self.path)
    def add(self,text):
        call=normalize(text)
        if not call: return 'Enter 1–2 letters, one digit, and 1–3 suffix letters (for example K8ZT). This checks format only.'
        if any(c['call']==call for c in self.workspace['candidates']): return call+' is already in this comparison.'
        if len(self.workspace['candidates'])>=10: return 'Compare up to ten callsigns. Remove one before adding another.'
        self.workspace['candidates'].append(dict(call=call,ratings={}));self.persist()
        return None
    def save(self):
        if not self.workspace['name'].strip() or not self.workspace['candidates']: return False
        self.saved=[w for w in self.saved if w['id']!=self.workspace['id']]+[copy.deepcopy(self.workspace)];self.persist();return True
    def export(self,path):
        w=self.workspace
        header=['Callsign','Weighted score (lower is better)','Characters','CW elements','Signal-only weight','CW time units','Phonetic syllables','Scored categories','Pending categories','Explanation']+[title+' priority' for _,title in CATEGORIES]+[title+' personal rating' for key,title in CATEGORIES if key not in MEASURED]
        with open(path,'w',newline='',encoding='utf-8') as stream:
            writer=csv.writer(stream);writer.writerow(header)
            for c in ranked(w):
                a=analysis(c['call']);s=score(w,c)
                writer.writerow([c['call'],f'{s:.4f}' if s is not None else '',a['characters'],a['elements'],a['signal'],a['cwTime'],a['phonetics'],'; '.join(TITLES[k] for k in scored_categories(w)),'; '.join(TITLES[k] for k in pending_categories(w)),explanation(w,c)]+[w['weights'][k] for k in TITLES]+[c['ratings'].get(k,'') for k in TITLES if k not in MEASURED])
