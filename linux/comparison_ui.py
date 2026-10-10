"""Qt callsign comparison workspace."""
import copy
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLineEdit,QComboBox,QSpinBox,QScrollArea,QWidget,QFrame,QFileDialog,QMessageBox,QGridLayout)
from comparison import (CATEGORIES,MEASURED,TITLES,preset,new_workspace,normalize,analysis,score,ranked,explanation,pending_categories,scored_categories,guidance)
from comparison_audio import Audio
from visuals import CallsignPreview

class ComparisonDialog(QDialog):
    def __init__(self,parent,library,watches,inspect):
        super().__init__(parent);self.library=library;self.inspect=inspect;self.expanded=set();self.preview=set()
        self.setWindowTitle('Compare callsigns');self.setWindowModality(Qt.WindowModality.ApplicationModal);self.resize(1180,820);self.setMinimumSize(960,650)
        self.audio=Audio(self);self.audio.error.connect(self.show_message)
        outer=QVBoxLayout(self);outer.setContentsMargins(24,24,24,24);outer.setSpacing(12)
        heading=QLabel('Choose your next callsign');heading.setStyleSheet('font-size:24px;font-weight:bold;');outer.addWidget(heading)
        outer.addWidget(QLabel('Compare what you can measure, then rate what matters to you.'))
        row=QHBoxLayout();outer.addLayout(row)
        self.name=QLineEdit();self.name.setPlaceholderText('Comparison name');self.name.setAccessibleName('Comparison name');self.name.textEdited.connect(lambda text:self.edit('name',text));row.addWidget(self.name,1)
        self.button(row,'Save comparison',self.save_comparison)
        self.saved=QComboBox();self.saved.setAccessibleName('Open saved comparison');self.saved.activated.connect(self.open_saved);row.addWidget(self.saved,1)
        self.button(row,'New',self.new);self.delete_button=self.button(row,'Delete saved…',self.delete_saved);self.button(row,'Export CSV…',self.export)
        row=QHBoxLayout();outer.addLayout(row)
        self.input=QLineEdit();self.input.setPlaceholderText('Callsign, e.g. K8ZT');self.input.setAccessibleName('Candidate callsign');self.input.returnPressed.connect(self.add);row.addWidget(self.input,1);self.button(row,'Add',self.add)
        self.watches=QComboBox();self.watches.setAccessibleName('Add from watchlist');self.watches.addItem('Add from watchlist')
        for call in watches:self.watches.addItem(call,call)
        self.watches.activated.connect(self.add_watch);row.addWidget(self.watches)
        row.addWidget(QLabel('CW WPM'));self.wpm=QSpinBox();self.wpm.setRange(5,50);self.wpm.setAccessibleName('CW words per minute');self.wpm.valueChanged.connect(lambda value:self.edit('wpm',value));row.addWidget(self.wpm);self.button(row,'Stop audio',self.audio.stop)
        self.message=QLabel();self.message.setWordWrap(True);self.message.setTextFormat(Qt.TextFormat.PlainText);outer.addWidget(self.message);self.message.hide()
        body=QHBoxLayout();outer.addLayout(body,1)
        priorities=QWidget();layout=QVBoxLayout(priorities);layout.setContentsMargins(0,0,12,0);priorities.setMinimumWidth(230)
        label=QLabel('Your priorities');label.setStyleSheet('font-weight:bold;font-size:17px;');layout.addWidget(label)
        self.presets=QComboBox();self.presets.addItems(['Balanced','CW','SSB','Custom']);self.presets.activated.connect(self.change_preset);layout.addWidget(self.presets)
        hint=QLabel('0 ignores a category; 3 gives it the most weight. Priorities preserve your ratings.');hint.setWordWrap(True);layout.addWidget(hint)
        self.weights={}
        for key,title in CATEGORIES:
            row=QHBoxLayout();label=QLabel(title+(' · measured' if key in MEASURED else ''));label.setWordWrap(True);row.addWidget(label,1)
            spin=QSpinBox();spin.setRange(0,3);spin.setAccessibleName(title+' priority');spin.valueChanged.connect(lambda value,key=key:self.set_weight(key,value));row.addWidget(spin);layout.addLayout(row);self.weights[key]=spin
        self.initials=QLineEdit();self.initials.setPlaceholderText('Initials or letters to match');self.initials.setAccessibleName('Initials or letters to match');self.initials.textEdited.connect(lambda text:self.edit('initials',text));layout.addWidget(self.initials)
        label=QLabel('Matching letters appear in explanations and do not change scores. Listen first, then rate clarity, endings, and rhythm.');label.setWordWrap(True);layout.addWidget(label);layout.addStretch()
        priority_scroll=QScrollArea();priority_scroll.setWidgetResizable(True);priority_scroll.setWidget(priorities);priority_scroll.setFixedWidth(275);body.addWidget(priority_scroll)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);body.addWidget(self.scroll,1)
        link_color='#8bc1ff' if self.palette().color(self.palette().ColorRole.Window).lightness()<128 else '#2166b5'
        credit=QLabel('Inspired by <a style="color:LINK_COLOR" href="https://www.k8zt.com/rules-orgs/vanity-callsign">K8ZT’s callsign guide</a>.'.replace('LINK_COLOR',link_color));credit.setObjectName('muted');credit.setStyleSheet('font-size: 12px;');credit.setWordWrap(True);credit.setOpenExternalLinks(True)
        credit.setToolTip('Anthony A. Luscre (K8ZT), Choosing Your Ideal Vanity Call Sign. CallPerch uses its own scoring scales and adjustable priorities.')
        outer.addWidget(credit)
        note=QLabel('Saved locally. Scores reflect your preferences; confirm eligibility and availability with the FCC.');note.setObjectName('muted');note.setStyleSheet('font-size: 12px;');note.setWordWrap(True);outer.addWidget(note)
        row=QHBoxLayout();row.addStretch();done=self.button(row,'Done',self.accept);done.setDefault(False);outer.addLayout(row)
        self.load_controls();self.render()
    @staticmethod
    def button(layout,title,callback):
        button=QPushButton(title);button.setAutoDefault(False);button.clicked.connect(callback);layout.addWidget(button);return button
    def show_message(self,text):self.message.setText(text);self.message.setVisible(bool(text))
    def persist(self):
        try:self.library.persist();return True
        except OSError as error:self.show_message('Could not save comparison: '+str(error));return False
    def edit(self,key,value,render=True):
        self.library.workspace[key]=value;self.persist()
        if render:self.render()
    def load_controls(self):
        w=self.library.workspace
        for widget,value in [(self.name,w['name']),(self.initials,w['initials'])]:widget.blockSignals(True);widget.setText(value);widget.blockSignals(False)
        self.wpm.blockSignals(True);self.wpm.setValue(w['wpm']);self.wpm.blockSignals(False)
        for key,widget in self.weights.items():widget.blockSignals(True);widget.setValue(w['weights'][key]);widget.blockSignals(False)
        self.update_preset();self.update_saved()
    def update_preset(self):
        name=next((n for n in ['Balanced','CW','SSB'] if preset(n)==self.library.workspace['weights']),'Custom')
        self.presets.setCurrentText(name)
    def update_saved(self):
        self.saved.clear();self.saved.addItem('Open saved comparison')
        for w in self.library.saved:self.saved.addItem(w['name'],w['id'])
        self.delete_button.setEnabled(any(w['id']==self.library.workspace['id'] for w in self.library.saved))
    def set_weight(self,key,value):
        self.library.workspace['weights'][key]=value;self.update_preset();self.persist();self.render()
    def change_preset(self,index):
        name=self.presets.itemText(index)
        if name=='Custom':return
        self.library.workspace['weights']=preset(name);self.load_controls();self.persist();self.render()
    def add(self):
        try:error=self.library.add(self.input.text())
        except OSError as error:self.show_message('Could not save comparison: '+str(error));self.render();return
        self.show_message(error or '')
        if error is None:self.preview.add(normalize(self.input.text()));self.input.clear();self.render()
    def add_watch(self,index):
        call=self.watches.itemData(index)
        if call:self.input.setText(call);self.add()
        self.watches.setCurrentIndex(0)
    def save_comparison(self):
        try:ok=self.library.save();self.show_message('Saved on this computer.' if ok else 'Add a callsign and enter a comparison name before saving.');self.update_saved()
        except OSError as error:self.show_message('Could not save comparison: '+str(error))
    def open_saved(self,index):
        identifier=self.saved.itemData(index)
        item=next((w for w in self.library.saved if w['id']==identifier),None)
        if item:self.audio.stop();self.library.workspace=copy.deepcopy(item);self.expanded.clear();self.preview.clear();self.persist();self.load_controls();self.render();self.show_message('')
    def new(self):
        self.audio.stop();self.library.workspace=new_workspace();self.expanded.clear();self.preview.clear();self.persist();self.load_controls();self.render();self.show_message('')
    def delete_saved(self):
        if QMessageBox.question(self,'Delete saved comparison?','Delete the saved copy? Your current draft will be retained.')!=QMessageBox.StandardButton.Yes:return
        self.library.saved=[w for w in self.library.saved if w['id']!=self.library.workspace['id']];self.persist();self.update_saved();self.show_message('Saved copy deleted. Current draft retained.')
    def export(self):
        if not self.library.workspace['candidates']:self.show_message('Add a callsign before exporting.');return
        path,_=QFileDialog.getSaveFileName(self,'Export comparison','CallPerch comparison.csv','CSV files (*.csv)')
        if not path:return
        try:self.library.export(path);self.show_message('Comparison exported.')
        except OSError as error:self.show_message('Could not export: '+str(error))
    def remove(self,call):
        self.audio.stop();self.library.workspace['candidates']=[c for c in self.library.workspace['candidates'] if c['call']!=call];self.persist();self.render()
    def rate(self,candidate,key,value):
        if value:candidate['ratings'][key]=value
        else:candidate['ratings'].pop(key,None)
        self.persist();self.render()
    def toggle(self,collection,call):
        if call in collection:collection.remove(call)
        else:collection.add(call)
        self.render()
    def records(self,call):self.accept();self.inspect(call)
    def render(self):
        position=self.scroll.verticalScrollBar().value();old=self.scroll.takeWidget()
        if old:old.deleteLater()
        content=QWidget();layout=QVBoxLayout(content);layout.setSpacing(14);w=self.library.workspace
        def text(value,parent=layout,style=None):
            label=QLabel(value);label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True)
            if style:label.setStyleSheet(style)
            parent.addWidget(label);return label
        text(f"Ranking · lower scores are better · {len(w['candidates'])} / 10",style='font-size:18px;font-weight:bold;')
        text('Fixed 1–10 scales: 4–6 characters, 25–100 CW time units, 4–18 syllables; values outside these ranges are capped. Personal ratings use 1 (best) to 10 (least preferred). These are product choices, not performance measurements.')
        pending=pending_categories(w)
        if pending:text('Provisional ranking. Not scored until every candidate is rated: '+', '.join(TITLES[k] for k in pending)+'.')
        if not scored_categories(w):text('Enable a measured category or rate an enabled personal category for every candidate to rank calls.')
        if not w['candidates']:text('Add candidates or choose them from your watchlist. Comparison does not confirm availability; inspect FCC records before applying.')
        for rank,c in enumerate(ranked(w),1):
            call=c['call'];a=analysis(call);s=score(w,c)
            card=QFrame();card.setFrameShape(QFrame.Shape.StyledPanel);cl=QVBoxLayout(card);layout.addWidget(card)
            row=QHBoxLayout();cl.addLayout(row);label=QLabel(f"{rank if s is not None else '—'}   {call}");label.setStyleSheet('font-size:23px;font-weight:bold;');row.addWidget(label,1)
            row.addWidget(QLabel(f'{s:.2f} / 10' if s is not None else 'Unranked'));self.button(row,'FCC records',lambda checked=False,call=call:self.records(call));self.button(row,'Remove',lambda checked=False,call=call:self.remove(call))
            text(explanation(w,c),cl)
            text(f"{a['elements']} CW elements · {a['signal']} signal-only units · {a['cwTime']*1.2/w['wpm']:.2f} seconds at {w['wpm']} WPM",cl)
            row=QHBoxLayout();cl.addLayout(row);self.button(row,'Play CW',lambda checked=False,call=call:self.audio.play(call,self.library.workspace['wpm']));self.button(row,'Speak phonetics',lambda checked=False,spoken=a['spoken']:self.audio.speak(spoken));row.addStretch()
            text(a['spoken'],cl);label=text(a['morse'],cl,f"font-family:'{QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()}';font-size:16px;");label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row=QHBoxLayout();cl.addLayout(row);self.button(row,('Hide' if call in self.expanded else 'Show')+' personal ratings and guidance',lambda checked=False,call=call:self.toggle(self.expanded,call));self.button(row,('Hide' if call in self.preview else 'Show')+' visual previews',lambda checked=False,call=call:self.toggle(self.preview,call));row.addStretch()
            if call in self.expanded:
                grid=QGridLayout();cl.addLayout(grid)
                for n,(key,title) in enumerate([(k,t) for k,t in CATEGORIES if k not in MEASURED]):
                    combo=QComboBox();combo.setAccessibleName(call+' '+title);combo.addItem('Unrated',0)
                    for value in range(1,11):combo.addItem(str(value)+(' · best' if value==1 else ' · least preferred' if value==10 else ''),value)
                    combo.setCurrentIndex(c['ratings'].get(key,0));combo.activated.connect(lambda value,c=c,key=key:self.rate(c,key,value));grid.addWidget(QLabel(title),n,0);grid.addWidget(combo,n,1)
                for note in guidance(call):text(note,cl)
            if call in self.preview:
                row=QHBoxLayout();cl.addLayout(row)
                row.addWidget(CallsignPreview(call,'qsl'),1);row.addWidget(CallsignPreview(call,'plate'),1)
                caption=text('QSL card and plate appearance previews · Illustrations only; plate requirements vary.',cl,'font-size:12px;');caption.setObjectName('muted')
        layout.addStretch();self.scroll.setWidget(content)
        QTimer.singleShot(0,lambda:self.scroll.verticalScrollBar().setValue(position) if self.scroll.widget() is content else None)
    def done(self,result):
        self.audio.stop();super().done(result)
    def closeEvent(self,event):
        self.audio.stop();super().closeEvent(event)
