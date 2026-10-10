#!/usr/bin/env python3
"""CallPerch Qt desktop port. The same executable hosts an isolated FCC engine process."""
import datetime as dt
import html
import json
import os
import sys
import tempfile
import shutil
import uuid
from pathlib import Path

ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fcc
from core import CLASSES,STATUS,ULS,data_directory,read_settings,save_settings,phonetic,due_reminders,snapshot_freshness,expiration_label,choice_label
if len(sys.argv)>1 and sys.argv[1]=='--engine':
    sys.argv=[sys.argv[0]]+sys.argv[2:];fcc.main();sys.exit(0)
if '--reminders' in sys.argv:
    from reminders import run
    sys.exit(run(fcc))

from PySide6.QtCore import Qt,QProcess,QTimer,QUrl
from PySide6.QtGui import QDesktopServices,QIcon,QPixmap,QFont,QColor,QFontDatabase
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QLineEdit,QSpinBox,QSplitter,QTableWidget,QTableWidgetItem,QTextBrowser,QMessageBox,QFileDialog,QCheckBox,QHeaderView,QButtonGroup,QGraphicsColorizeEffect,QDialog,QProgressBar,QSystemTrayIcon,QStackedLayout)

from appearance import stylesheet,palette
from visuals import coffee_icon,AppearanceSelector,LoadingOverlay
from comparison import Library
from comparison_ui import ComparisonDialog

MODES=[('Callsign search','search'),('Available estimates','available'),('Coming available','upcoming'),('Applications','contested'),('Watchlist','watchlist')]

def engine_command(arguments):
    if getattr(sys,'frozen',False) and sys.platform=='win32':
        return [str(Path(sys.executable).with_name('CallPerchEngine.exe')),'--engine',*arguments]
    return [sys.executable,'--engine',*arguments] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).resolve()),'--engine',*arguments]

def asset(name):
    return ROOT/'assets/branding'/name

class SyncProgressDialog(QDialog):
    def __init__(self,parent,cancel):
        super().__init__(parent)
        self.setWindowTitle('Syncing FCC');self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(480);self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint,False)
        self.running=True;self.cancel_requested=False;self.cancel=cancel
        layout=QVBoxLayout(self);layout.setContentsMargins(24,24,24,24);layout.setSpacing(16)
        self.heading=QLabel('Syncing FCC');self.heading.setStyleSheet('font-size: 22px; font-weight: bold;');layout.addWidget(self.heading)
        self.message=QLabel('Preparing FCC snapshot…');self.message.setWordWrap(True);self.message.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.message)
        self.progress=QProgressBar();self.progress.setRange(0,0);layout.addWidget(self.progress)
        self.help=QLabel('Downloading and indexing FCC records can take several minutes. Keep CallPerch open while records are being processed.');self.help.setWordWrap(True);layout.addWidget(self.help)
        self.button=QPushButton('Cancel Sync');self.button.clicked.connect(self.button_clicked);layout.addWidget(self.button)
    def button_clicked(self):
        if self.running:self.request_cancel()
        else:self.accept()
    def request_cancel(self):
        if self.cancel_requested:return
        self.cancel_requested=True;self.button.setText('Canceling…');self.button.setEnabled(False);self.cancel()
    def update_message(self,text):
        if self.running:self.message.setText(text)
    def finish(self,message):
        self.running=False;self.heading.setText('FCC sync finished');self.setWindowTitle('FCC sync finished')
        self.message.setText(message);self.progress.hide();self.help.hide();self.button.setText('Done');self.button.setEnabled(True);self.button.setDefault(True)
    def reject(self):
        if self.running:self.request_cancel()
        else:super().reject()
    def closeEvent(self,event):
        if self.running:self.request_cancel();event.ignore()
        else:event.accept()

class Window(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('CallPerch');self.resize(1320,850)
        self.setWindowIcon(QIcon(str(asset('callperch-logo.png'))))
        self.settings=read_settings();self.rows=[];self.selected=None;self.detail=None;self.process=None;self.notify_process=None;self.syncing=False;self.staging=None;self.cancelled=False;self.sync_dialog=None;self.expanded_timelines=set()
        self.snapshot_timestamp='';self.selected_license_id=None
        self.comparisons=Library();self.comparison_dialog=None
        self.tray=None
        if sys.platform=='win32':
            self.tray=QSystemTrayIcon(self.windowIcon(),self)
            self.tray.setToolTip('CallPerch')
            self.tray.messageClicked.connect(lambda:QDesktopServices.openUrl(QUrl(ULS)))
            self.tray.show()
        self.setMinimumSize(1000,650)
        central=QWidget();self.setCentralWidget(central);shell=QHBoxLayout(central);shell.setContentsMargins(0,0,0,0);shell.setSpacing(0)
        sidebar=QWidget();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(228);side=QVBoxLayout(sidebar);side.setContentsMargins(18,24,18,18);side.setSpacing(8);shell.addWidget(sidebar)
        self.logo=logo=QLabel();logo.setAlignment(Qt.AlignmentFlag.AlignCenter);logo.setPixmap(QPixmap(str(asset('callperch-logo.png'))).scaled(110,110,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));side.addWidget(logo)
        tagline=QLabel('AMATEUR RADIO INTELLIGENCE');tagline.setObjectName('muted');tagline.setStyleSheet('font-size: 10px; font-weight: bold;');side.addWidget(tagline)
        self.mode=QComboBox(self);self.mode.hide();self.navigation=QButtonGroup(self);self.nav_buttons=[]
        for index,(label,mode) in enumerate(MODES):
            self.mode.addItem(label,mode)
            button=QPushButton(label);button.setObjectName('navigation');button.setCheckable(True);self.navigation.addButton(button,index);side.addWidget(button);self.nav_buttons.append(button)
        self.nav_buttons[0].setChecked(True)
        self.navigation.idClicked.connect(self.navigate)
        self.compare_button=QPushButton('Compare callsigns');self.compare_button.setObjectName('primary');self.compare_button.clicked.connect(self.open_comparison);side.addWidget(self.compare_button)
        side.addStretch()
        self.snapshot=QLabel('No local snapshot loaded');self.snapshot.setWordWrap(True);self.snapshot.setObjectName('muted');side.addWidget(self.snapshot)
        self.sync_button=QPushButton('Sync FCC');self.sync_button.setObjectName('primary');self.sync_button.clicked.connect(self.sync);side.addWidget(self.sync_button)
        self.import_button=QPushButton('Import FCC ZIPs…');self.import_button.clicked.connect(self.import_files);side.addWidget(self.import_button)
        self.delete_button=QPushButton('Delete local data…');self.delete_button.clicked.connect(self.delete_local_data);side.addWidget(self.delete_button)
        appearance_label=QLabel('Appearance');appearance_label.setObjectName('muted');appearance_row=QHBoxLayout();appearance_row.addWidget(appearance_label)
        self.appearance=AppearanceSelector();self.appearance.setAccessibleName('Appearance')
        for label,value in [('System','system'),('Light','light'),('Dark','dark')]:self.appearance.addItem(label,value)
        self.appearance.setCurrentIndex(self.appearance.findData(self.settings['appearance']));self.appearance.setMinimumWidth(120);appearance_row.addWidget(self.appearance)
        self.appearance.currentIndexChanged.connect(self.appearance_changed)
        credit=QLabel('Created with love by <b>KR4GOJ</b>');credit.setObjectName('muted');side.addWidget(credit)
        self.coffee=coffee=QPushButton('Buy me a coffee  ↗');coffee.setObjectName('coffee');coffee.setIcon(coffee_icon());coffee.setToolTip('Support CallPerch on Buy Me a Coffee');coffee.clicked.connect(lambda:QDesktopServices.openUrl(QUrl('https://buymeacoffee.com/kr4goj')));side.addWidget(coffee)
        self.acknowledgments_link=QLabel();self.privacy_link=QLabel()
        self.acknowledgments_link.linkActivated.connect(lambda _:self.show_acknowledgments())
        self.privacy_link.linkActivated.connect(lambda _:QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT/'docs/privacy.html'))))
        for link,name in [(self.acknowledgments_link,'Acknowledgments'),(self.privacy_link,'Privacy policy')]:
            link.setAccessibleName(name);link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction);link.setFocusPolicy(Qt.FocusPolicy.StrongFocus);link.setStyleSheet('font-size: 11px;');side.addWidget(link)
        workspace=QWidget();layout=QVBoxLayout(workspace);layout.setContentsMargins(24,24,24,16);layout.setSpacing(14);shell.addWidget(workspace,1)
        self.heading=QLabel();self.heading.setObjectName('heading');header=QHBoxLayout();header.addWidget(self.heading,1);header.addLayout(appearance_row);layout.addLayout(header)
        self.subtitle=QLabel();self.subtitle.setObjectName('muted');self.subtitle.setWordWrap(True);layout.addWidget(self.subtitle)
        self.freshness_banner=QWidget();freshness_layout=QHBoxLayout(self.freshness_banner)
        self.freshness_text=QLabel();self.freshness_text.setWordWrap(True);freshness_layout.addWidget(self.freshness_text,1)
        self.freshness_sync=QPushButton('Sync FCC');self.freshness_sync.clicked.connect(self.sync);freshness_layout.addWidget(self.freshness_sync)
        dismiss=QPushButton('Dismiss');dismiss.clicked.connect(self.dismiss_freshness);freshness_layout.addWidget(dismiss)
        self.freshness_banner.hide();layout.addWidget(self.freshness_banner)
        self.controls=QWidget();bar=QHBoxLayout(self.controls)
        self.term=QLineEdit();self.term.setPlaceholderText('Callsign or licensee name');bar.addWidget(self.term,1)
        self.region=QComboBox();self.region.addItem('All regions',-1)
        for i in range(10):self.region.addItem('Region '+str(i),i)
        bar.addWidget(self.region)
        self.form=QComboBox();self.form.setAccessibleName('Callsign format');self.form.addItem('All formats','All')
        for form in ['1x2','2x1','2x2','1x3','2x3']:self.form.addItem(form,form)
        bar.addWidget(self.form)
        self.horizon=QSpinBox();self.horizon.setRange(1,3650);self.horizon.setValue(180);self.horizon.setSuffix(' days');bar.addWidget(self.horizon)
        self.sort=QComboBox();self.sort.addItem('Available date','date');self.sort.addItem('CW weight','cw');self.sort.setCurrentIndex(self.sort.findData(self.settings['sort']));bar.addWidget(self.sort)
        self.direction=QComboBox();self.direction.addItem('Ascending','asc');self.direction.addItem('Descending','desc');self.direction.setCurrentIndex(self.direction.findData(self.settings['direction']));bar.addWidget(self.direction)
        self.search=QPushButton('Search');self.search.setObjectName('primary');self.search.clicked.connect(self.refresh);self.search.setFixedWidth(100);bar.addWidget(self.search);bar.addStretch();bar.addSpacing(24)
        self.uls_link=QLabel();self.uls_link.setAccessibleName('FCC ULS login');self.uls_link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction);self.uls_link.setFocusPolicy(Qt.FocusPolicy.StrongFocus);self.uls_link.setStyleSheet('font-size: 12px;');self.uls_link.linkActivated.connect(lambda _:QDesktopServices.openUrl(QUrl(ULS)));bar.addWidget(self.uls_link);layout.addWidget(self.controls)
        self.alerts=QCheckBox('One-day reminders');self.alerts.setChecked(self.settings['alerts']);self.alerts.toggled.connect(self.save);bar.insertWidget(0,self.alerts)
        if sys.platform=='win32':self.alerts.setToolTip('Reminders are checked while CallPerch is open, after 9 AM on the day before estimated release. Click a notification to open FCC ULS.')
        self.status=QLabel('Loading local FCC snapshot…');self.status.setWordWrap(True);layout.addWidget(self.status)
        results=QWidget();results_stack=QStackedLayout(results);results_stack.setContentsMargins(0,0,0,0);results_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        split=QSplitter();results_stack.addWidget(split)
        self.loading=LoadingOverlay(cancel=self.cancel_operation);self.cancel_button=self.loading.cancel_button;results_stack.addWidget(self.loading);results_stack.setCurrentWidget(self.loading);self.loading.hide();layout.addWidget(results,1)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['','Callsign','License details','Dates / requests']);self.table.verticalHeader().hide();self.table.setShowGrid(False);self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents);self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch);self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed);self.table.setColumnWidth(0,42);self.table.itemSelectionChanged.connect(self.selection_changed);split.addWidget(self.table)
        details=QWidget();details.setMinimumWidth(280);dl=QVBoxLayout(details);self.detail_title=QLabel('Callsign details');self.detail_title.setStyleSheet('font-size: 18px; font-weight: bold;');detail_header=QHBoxLayout();detail_header.addWidget(self.detail_title,1);self.watch_button=QPushButton('☆');self.watch_button.setObjectName('star');self.watch_button.setFixedSize(36,36);self.watch_button.setEnabled(False);self.watch_button.clicked.connect(lambda:self.toggle_watch());detail_header.addWidget(self.watch_button);dl.addLayout(detail_header);self.add_compare_button=QPushButton('Add to comparison');self.add_compare_button.clicked.connect(self.add_to_comparison);self.add_compare_button.setEnabled(False);dl.addWidget(self.add_compare_button);self.historical=QCheckBox('Include historical address matches');self.historical.toggled.connect(self.render_detail);dl.addWidget(self.historical)
        self.reveal_address=QCheckBox('Show public FCC mailing address');self.reveal_address.toggled.connect(self.render_detail);dl.addWidget(self.reveal_address)
        self.browser=QTextBrowser();self.browser.setOpenLinks(False);self.browser.anchorClicked.connect(self.open_link);dl.addWidget(self.browser);split.addWidget(details);split.setSizes([850,400])
        footer=QLabel('Weekly snapshots and estimated dates are not FCC decisions. Address matches use recorded mailing addresses. '+('Windows reminders require CallPerch to stay open.' if sys.platform=='win32' else 'Reminders while closed require the optional Linux user timer.'));footer.setWordWrap(True);layout.addWidget(footer)
        self.term.returnPressed.connect(self.refresh);self.mode.currentIndexChanged.connect(self.mode_changed)
        # Filter edits are staged until Search / Refresh is pressed.
        self.mode_changed(refresh=False);self.empty_detail()
        QApplication.styleHints().colorSchemeChanged.connect(self.system_appearance_changed)
        self.apply_appearance()
        self.timer=QTimer(self);self.timer.timeout.connect(self.check_reminders);self.timer.timeout.connect(self.update_freshness);self.timer.start(60*60*1000)
        self.freshness_timer=QTimer(self);self.freshness_timer.timeout.connect(self.update_freshness);self.freshness_timer.start(60000)
        QApplication.instance().applicationStateChanged.connect(self.update_freshness)
        QTimer.singleShot(0,self.load_stats)

    def show_acknowledgments(self):
        dialog=QDialog(self);dialog.setWindowTitle('Acknowledgments');dialog.resize(520,420)
        layout=QVBoxLayout(dialog)
        text=QLabel('Thank you to the operators whose ideas, feedback, and testing help improve CallPerch.<br><br><b>Fin (NC4FG)</b><br>For feedback that helped shape the callsign comparison workspace.<br><br><b>Ben (KO4B)</b><br>For feedback that helped shape the repeated callsign switching feature.<br><br><b>Michael (KZ4LY)</b><br>For his help with Linux support, testing, and troubleshooting.<br><br><b>Anthony A. Luscre (K8ZT)</b><br>For “Choosing Your Ideal Vanity Call Sign,” which inspired the callsign comparison criteria.<br><a href="https://www.k8zt.com/rules-orgs/vanity-callsign">Read Anthony’s article</a>')
        text.setWordWrap(True);text.setOpenExternalLinks(True);layout.addWidget(text)
        done=QPushButton('Done');done.clicked.connect(dialog.accept);layout.addWidget(done);dialog.exec()

    def update_freshness(self,*_):
        info=snapshot_freshness(self.snapshot_timestamp,dt.datetime.now().astimezone(),self.settings.get('snapshot_dismissed_version',''),self.settings.get('snapshot_dismissed_day',''))
        self.freshness_banner.setVisible(info is not None)
        if info:
            self.freshness_text.setText(info['message'])
            self.freshness_banner.setStyleSheet('background-color: '+('#5b3e20' if self.dark else '#fff0db')+'; border-radius: 8px;'+(' border: 1px solid #c47a20;' if info['very_old'] else ''))
        self.freshness_sync.setEnabled(self.process is None and not self.syncing)

    def dismiss_freshness(self):
        self.settings.update(snapshot_dismissed_version=self.snapshot_timestamp,snapshot_dismissed_day=dt.datetime.now().astimezone().date().isoformat())
        self.save();self.update_freshness()

    def open_comparison(self):
        if self.process is not None or self.syncing:return
        if self.comparison_dialog:self.comparison_dialog.raise_();self.comparison_dialog.activateWindow();return
        dialog=ComparisonDialog(self,self.comparisons,self.settings['watches'],self.inspect);self.comparison_dialog=dialog
        def finished(*_):self.comparison_dialog=None;dialog.deleteLater()
        dialog.finished.connect(finished);dialog.show()

    def add_to_comparison(self):
        if not self.selected or self.process is not None or self.syncing:return
        try:error=self.comparisons.add(self.selected)
        except OSError as error:self.set_status('Could not save comparison: '+str(error));return
        if error:self.set_status(error);return
        self.open_comparison()

    def appearance_changed(self,*_):
        self.save();self.apply_appearance()

    def system_appearance_changed(self,scheme):
        if self.appearance.currentData()=='system':self.apply_appearance(scheme)

    def apply_appearance(self,scheme=None):
        if scheme is None:scheme=QApplication.styleHints().colorScheme()
        system_dark=scheme==Qt.ColorScheme.Dark
        if scheme==Qt.ColorScheme.Unknown:
            system_dark=QApplication.palette().color(QApplication.palette().ColorRole.Window).lightness()<128
        self.dark=self.appearance.currentData()=='dark' or self.appearance.currentData()=='system' and system_dark
        self.setPalette(palette(self.dark));self.setStyleSheet(stylesheet(self.dark));self.update_freshness()
        # Tint the transparent brand artwork so it remains legible on a dark sidebar.
        if self.dark:
            effect=QGraphicsColorizeEffect(self.logo);effect.setColor(QColor('#a9cfff'));effect.setStrength(.85);self.logo.setGraphicsEffect(effect)
        else:self.logo.setGraphicsEffect(None)
        link='#8bc1ff' if self.dark else '#2166b5'
        for widget,title,target in [(self.acknowledgments_link,'Acknowledgments','acknowledgments'),(self.privacy_link,'Privacy policy','privacy'),(self.uls_link,'FCC ULS login ↗',ULS)]:
            widget.setText(f'<a style="color:{link};text-decoration:none;" href="{target}">{title}</a>')
        self.browser.document().setDefaultStyleSheet(f'a {{ color: {link}; }} .morse {{ font-family: monospace; font-size: 18px; }}')
        if self.detail:self.render_detail()
        else:self.empty_detail()

    def navigate(self,index):
        if self.process is not None:
            self.nav_buttons[self.mode.currentIndex()].setChecked(True);return
        self.mode.setCurrentIndex(index)

    def selection_changed(self):
        row=self.table.currentRow()
        if self.table.selectedItems() and 0<=row<len(self.rows):self.choose(row,0)

    def empty_detail(self):
        self.detail_title.setText('Callsign details');self.watch_button.hide();self.add_compare_button.setEnabled(False)
        self.browser.setHtml('<h2>Select a callsign</h2><p>Choose a result to see its license, estimated availability, applications and FCC history.</p><p>Click the star beside a callsign to save it to your watchlist.</p>')

    def save(self,*_):
        self.settings.update(appearance=self.appearance.currentData(),alerts=self.alerts.isChecked(),sort=self.sort.currentData(),direction=self.direction.currentData());save_settings(self.settings)

    def database(self):
        own=data_directory()/'fcc.sqlite'
        if own.exists():return own
        for path in [ROOT/'backend/fcc.sqlite',ROOT/'data/fcc.sqlite']:
            if path.exists():return path
        return own

    def mode_changed(self,*_,refresh=True):
        mode=self.mode.currentData();availability=mode in ('available','upcoming')
        self.term.setPlaceholderText('Receipt date YYYY-MM-DD (optional)' if mode=='contested' else 'Callsign or licensee name')
        self.term.setEnabled(mode in ('search','contested'));self.sort.setEnabled(availability);self.direction.setEnabled(availability);self.horizon.setEnabled(mode=='upcoming')
        self.heading.setText(self.mode.currentText());self.nav_buttons[self.mode.currentIndex()].setChecked(True)
        self.subtitle.setText({'search':'Find a callsign or licensee in your local FCC snapshot.','available':'Explore callsigns with estimated release dates in the past.','upcoming':'Find callsigns approaching their estimated availability date.','contested':'Review pending and returned callsign requests.','watchlist':'Keep your favorite callsigns and track estimated availability.'}[mode])
        self.term.setVisible(mode in ('search','contested'));self.region.setVisible(mode!='watchlist');self.form.setVisible(mode!='watchlist');self.horizon.setVisible(mode=='upcoming');self.sort.setVisible(availability);self.direction.setVisible(availability)
        self.alerts.setVisible(mode=='watchlist');self.search.setText('Search' if mode=='search' else 'Refresh')
        if refresh:self.refresh()

    def set_status(self,message):
        self.status.setText(message)
        if self.sync_dialog:self.sync_dialog.update_message(message)
    def show_sync_progress(self):
        dialog=SyncProgressDialog(self,self.cancel_operation);self.sync_dialog=dialog
        def dismissed(*_):
            if self.sync_dialog is dialog:self.sync_dialog=None
            dialog.deleteLater()
        dialog.finished.connect(dismissed)
        dialog.show()
    def finish_sync_progress(self,message):
        if self.sync_dialog:self.sync_dialog.finish(message)

    def run(self,arguments,callback,mutating=False):
        if self.process is not None:return
        modes={'search':'Filtering callsigns…','available':'Loading available estimates…','upcoming':'Loading coming callsigns…','contested':'Loading applications…','detail':'Loading callsign details…','stats':'Loading FCC snapshot…','watchdates':'Loading reminder dates…'}
        self.loading.message=modes.get(arguments[1] if len(arguments)>1 else '', 'Loading…');self.loading.setAccessibleName(self.loading.message)
        self.loading.setVisible(not mutating);self.loading.raise_();self.loading.update()
        self.cancelled=False;self.cancel_button.setEnabled(True);self.delete_button.setEnabled(False)
        self.controls.setEnabled(False);self.table.setEnabled(False);self.sync_button.setEnabled(False);self.import_button.setEnabled(False);self.watch_button.setEnabled(False);self.compare_button.setEnabled(False);self.add_compare_button.setEnabled(False)
        process=QProcess(self);self.process=process;output=bytearray()
        db=data_directory()/'fcc.sqlite' if mutating else self.database()
        staging_file=db.parent/('fcc-import-'+uuid.uuid4().hex+'.sqlite') if mutating else None
        staging_args=['--staging',str(staging_file)] if staging_file else []
        command=engine_command(['--db',str(db),*staging_args,*arguments]);process.setProgram(command[0]);process.setArguments(command[1:])
        def receive_output():
            chunk=bytes(process.readAllStandardOutput())
            if len(output)+len(chunk)>16*1024*1024:self.cancel_operation();return
            output.extend(chunk)
        process.readyReadStandardOutput.connect(receive_output)
        def progress():
            message=bytes(process.readAllStandardError()).decode('utf-8',errors='replace').strip()
            if message:self.set_status(message)
        process.readyReadStandardError.connect(progress)
        watchdog=QTimer(process);watchdog.setSingleShot(True);watchdog.timeout.connect(lambda:self.cancel_operation(timed_out=True));watchdog.start(1800*1000 if mutating else 120*1000)
        finished=False
        def complete(code,status=None):
            nonlocal finished
            if finished:return
            finished=True;watchdog.stop();self.cancel_button.setEnabled(False);self.delete_button.setEnabled(True);output.extend(bytes(process.readAllStandardOutput()));self.process=None
            self.controls.setEnabled(True);self.table.setEnabled(True);self.sync_button.setEnabled(True);self.import_button.setEnabled(True);self.watch_button.setEnabled(self.selected is not None)
            sync_message="FCC sync complete. Your updated snapshot is ready."
            try:
                if self.cancelled:raise ValueError("Operation canceled or timed out. Previous snapshot preserved.")
                result=json.loads(output)
                if code!=0 or isinstance(result,dict) and 'error' in result:raise ValueError(result.get('error','FCC engine failed'))
                callback(result)
            except (ValueError,TypeError) as error:
                self.set_status(str(error));sync_message="FCC sync canceled. Previous snapshot preserved." if self.cancelled else "FCC sync failed. Previous snapshot preserved.\n"+str(error)
            if mutating:
                self.syncing=False;self.finish_sync_progress(sync_message);self.cleanup_staging()
                staging_file.unlink(missing_ok=True);Path(str(staging_file)+'-journal').unlink(missing_ok=True)
            self.compare_button.setEnabled(not self.syncing and self.process is None);self.add_compare_button.setEnabled(self.selected is not None and not self.syncing and self.process is None)
            if self.process is None:self.loading.hide()
            process.deleteLater()
        process.finished.connect(complete)
        process.errorOccurred.connect(lambda error:complete(-1) if error==QProcess.ProcessError.FailedToStart else None)
        process.start()

    def load_stats(self):
        def loaded(stats):
            self.snapshot_timestamp=stats['synced'];self.update_freshness()
            self.snapshot.setText(f"{stats['licenses']:,} licenses · {stats['applications']:,} pending / returned applications · Imported {stats['synced'][:10]}");self.set_status(f"{stats['licenses']:,} licenses ready. Search for a callsign or choose a section.");self.check_reminders()
        self.run(['query','stats'],loaded)

    def refresh(self,*_):
        if self.process is not None:return
        self.save();self.selected=None;self.detail=None;self.empty_detail();self.watch_button.setEnabled(False)
        mode=self.mode.currentData()
        if mode=='watchlist':
            calls=list(self.settings['watches']);rows=[]
            def next_call():
                if not calls:self.show_rows(rows);return
                call=calls.pop(0)
                def loaded(result):
                    if result['licenses']: rows.extend(result['licenses'][:1])
                    else:
                        digit,shape=fcc.shape(call)
                        rows.append(dict(id='unassigned:'+call,call=call,status='Unknown',grant_date='',expires='',region=digit,format=shape,estimate='',name='No license record in snapshot',city='',state='',operator_class='',applicants=0))
                    next_call()
                self.run(['query','detail','--term',call],loaded)
            next_call();return
        arguments=['query',mode,'--term',self.term.text() if mode in ('search','contested') else '', '--region',str(self.region.currentData()),'--format',self.form.currentData(),'--horizon',str(self.horizon.value()),'--sort',self.sort.currentData(),'--direction',self.direction.currentData()]
        self.run(arguments,self.show_rows)

    def show_rows(self,rows):
        self.table.blockSignals(True);self.table.clearSelection();self.rows=rows;self.table.setRowCount(len(rows))
        for index,row in enumerate(rows):
            call=row['call'];metrics=phonetic(call)
            date=row['estimate'] if self.mode.currentData() in ('available','upcoming') else row['expires']
            label='Est. available' if self.mode.currentData() in ('available','upcoming') else ('Expired' if row['expires'] and row['expires']<dt.date.today().isoformat() else 'Expires')
            values=[call, f"{row['name']}\n{row['city']}, {row['state']} · {CLASSES.get(row['operator_class'],row['operator_class'])} · {STATUS.get(row['status'],row['status'])}\nCW: {fcc.cw_weight(call)} units · Phonetic: {metrics['weight'] if metrics else '—'} syllables",f"{label} {date or '—'}\n{row['applicants']} pending / returned"+(f"\nEstimated available since {row['estimate']}" if row.get('available')==1 else '')]
            star=QPushButton('★' if call in self.settings['watches'] else '☆');star.setObjectName('star');star.setAccessibleName('Toggle watchlist for '+call);star.clicked.connect(lambda checked=False,call=call:self.toggle_watch(call));self.table.setCellWidget(index,0,star)
            for column,value in enumerate(values,1):
                item=QTableWidgetItem(str(value))
                if column==1:
                    font=QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont);font.setPointSize(15);font.setBold(True);item.setFont(font)
                if metrics:item.setToolTip('CW: '+'   '.join(fcc.MORSE[letter] for letter in call))
                self.table.setItem(index,column,item)
            self.table.setRowHeight(index,88)
        self.table.blockSignals(False);self.update_star()
        self.set_status(f'{len(rows)} results · maximum 500 for search and availability')
        if not rows and self.mode.currentData()=='search' and self.term.text().strip():self.inspect(self.term.text().strip().upper())

    def choose(self,row,column):self.inspect(self.rows[row]['call'],self.rows[row].get('id',''))
    def inspect(self,call,license_id=''):
        self.selected_license_id=license_id
        self.expanded_timelines.clear()
        self.reveal_address.setChecked(False);self.selected=call;self.historical.setChecked(False)
        def loaded(result):self.detail=result;self.render_detail();self.update_star()
        self.run(['query','detail','--term',call]+(['--license-id',license_id] if license_id and not license_id.startswith('unassigned:') else []),loaded)
    def update_star(self):
        self.add_compare_button.setEnabled(self.selected is not None and self.process is None and not self.syncing)
        self.watch_button.setVisible(self.selected is not None)
        self.watch_button.setEnabled(self.selected is not None and self.process is None)
        self.watch_button.setText('★' if self.selected in self.settings['watches'] else '☆')
        self.watch_button.setToolTip(('Remove from' if self.selected in self.settings['watches'] else 'Add to')+' watchlist')
        self.watch_button.setAccessibleName('Toggle watchlist for '+(self.selected or 'selected callsign'))
        for index,row in enumerate(self.rows):
            button=self.table.cellWidget(index,0)
            if button:
                watched=row['call'] in self.settings['watches'];button.setText('★' if watched else '☆');button.setToolTip(('Remove '+row['call']+' from' if watched else 'Add '+row['call']+' to')+' watchlist')
    def toggle_watch(self,call=None):
        call=call or self.selected
        if not call or self.process is not None:return
        watches=self.settings['watches']
        if call in watches:watches.remove(call)
        else:watches.append(call)
        self.save()
        # Keep the displayed watchlist stable until its next explicit refresh.
        self.update_star();self.check_reminders()
    def render_detail(self,*_):
        if not self.detail:return
        esc=lambda value:html.escape(str(value))
        return_color='#ffb15b' if self.dark else '#a34b00'
        self.detail_title.setText(self.selected or 'Callsign details')
        d=self.detail;blocks=[f'<p><a href="{ULS}">FCC ULS login</a> · <a href="https://wireless2.fcc.gov/UlsApp/UlsSearch/searchLicense.jsp">Search official FCC ULS</a></p>']
        metrics=phonetic(self.selected)
        if metrics:blocks.append(f"<p>Phonetic: {metrics['weight']} syllables · CW: {fcc.cw_weight(self.selected)} units<br>{esc(metrics['spoken'])}</p>")
        if metrics:
            morse='   '.join(fcc.MORSE[letter] for letter in self.selected.strip().upper())
            blocks.append(f'<h3>CW · dit / dah</h3><p class="morse">{esc(morse).replace("   ","&nbsp;&nbsp;&nbsp;")}</p><p><small>Dot = dit · dash = dah · spaces separate letters.</small></p>')
        if d['licenses']:
            l=d['licenses'][0]
            if l.get('available')==1:blocks.append(f"<p style='color:green'><b>Available</b> · since {esc(l['estimate'])}</p>")
            blocks.append(f"<h3>{esc(l['name'])}</h3><p>{esc(STATUS.get(l['status'],l['status']))} · {esc(CLASSES.get(l['operator_class'],l['operator_class']))}<br>Granted {esc(l['grant_date'])}<br>{esc(expiration_label(l))}<br>Canceled {esc(l.get('cancel_date',''))}<br>Estimated release {esc(l['estimate'])}</p>")
        else:blocks.append('<p>No license record in this snapshot. This does not establish availability.</p>')
        previous=d.get('previous_callsigns',{})
        blocks.append('<h3>Previous callsigns for this licensee</h3>')
        for record in previous.get('matches',[]):
            blocks.append(f"<p><a href=\"license:{esc(record['id'])}:{esc(record['call'])}\">{esc(record['call'])}</a> · {esc(STATUS.get(record['status'],record['status']))}<br>{esc(('Canceled '+record['cancel_date']) if record.get('cancel_date') else expiration_label(record))}</p>")
        for call in previous.get('unresolved',[]):blocks.append(f'<p>{esc(call)} · FCC-recorded previous callsign; status unavailable in this snapshot.</p>')
        if not previous.get('matches') and not previous.get('unresolved'):
            blocks.append('<p>'+{'needs_sync':'Sync FCC to load callsign history.','identity_unavailable':'FCC holder identity unavailable; previous callsigns cannot be linked.'}.get(previous.get('state'),'No earlier callsigns found in this snapshot.')+'</p>')
        blocks.append('<p><small>Linked by individual FCC holder identity or a recorded callsign change, not by mailing address. Snapshot history may be incomplete.</small></p>')
        address=d.get('same_address',{});blocks.append('<h3>Other callsigns at this address</h3>')
        if address.get('state')=='ready':
            a=address['address'];lines=[a['attention'],a['street'],'PO Box '+a['po_box'] if a['po_box'] else '',f"{a['city']}, {a['state']} {a['zip']}"]
            if self.reveal_address.isChecked():blocks.append('<p>'+'<br>'.join(esc(line) for line in lines if line)+'</p>')
            if address.get('truncated'):blocks.append('<p>Showing the first 500 matching records.</p>')
            matches=[r for r in address['matches'] if r['current'] or self.historical.isChecked()]
            for r in matches:blocks.append(f"<p><a href=\"call:{esc(r['call'])}\">{esc(r['call'])}</a> · {esc(r['name'])}<br>{esc(STATUS.get(r['status'],r['status']))} · {esc(CLASSES.get(r['operator_class'],r['operator_class']))}</p>")
            if not matches:blocks.append('<p>No other matching callsigns in this view.</p>')
            blocks.append('<p><small>Exact mailing address, ignoring case and whitespace. Units, PO boxes, attention, and full ZIP remain distinct. This does not establish shared residence.</small></p>')
        else:blocks.append('<p>'+{'missing':'Sync FCC to add full addresses.','incomplete':'The FCC address is incomplete and cannot be matched.','unknown':'No license address found.'}.get(address.get('state'),'No address data.')+'</p>')
        switching=d.get('switching',{'state':'needs_sync','holders':[]})
        blocks.append('<h3>Repeated callsign switching</h3><p><small>Flags at least two returns across four or more assignments linked by individual FRN. This pattern does not establish intent or a rule violation.</small></p>')
        if switching['state']=='needs_sync':blocks.append('<p>Sync FCC to enable detection in this older snapshot.</p>')
        elif switching['state']=='identity_unavailable':blocks.append('<p>Individual holder FRN unavailable; detection cannot be assessed.</p>')
        elif not switching['holders']:blocks.append('<p>No qualifying pattern found in this snapshot. Incomplete history can hide earlier switches.</p>')
        for holder in switching['holders']:
            expanded=holder['frn'] in self.expanded_timelines
            blocks.append(f"<h4>{esc(holder['name'])}</h4><p>FRN {esc(holder['frn'])} · {esc(holder['returns'])} returns · {esc(holder['early_returns'])} before ordinary release</p>")
            blocks.append(f"<p><a href=\"timeline:{esc(holder['frn'])}\">{'▼' if expanded else '▶'} Assignment timeline · {'Collapse' if expanded else 'Expand'}</a></p>")
            if expanded:
                for event in holder['timeline']:
                    blocks.append(f"<p><a href=\"call:{esc(event['call'])}\">{esc(event['call'])}</a> · Granted {esc(event['grant_date'])}")
                    if event['cancel_date']:blocks.append(f"<br>Canceled {esc(event['cancel_date'])}")
                    if event['before_release']:blocks.append(f'<br><span style="font-size: 11px; color: {return_color};">Return before ordinary two-year release estimate</span>')
                    elif event['return_to_call']:blocks.append('<br><span style="font-size: 11px;">Return to previously held callsign</span>')
                    blocks.append('</p>')
            if holder['truncated']:blocks.append('<p>Timeline limited to 2,000 records; counts are partial.</p>')
        blocks.append('<h3>Applications requesting this callsign</h3><p><small>Distinct pending/returned application IDs are not unique people or eligible competitors.</small></p>')
        for r in d['applications']:blocks.append(f"<p>{esc(r['name'] or r['file'])}<br>File {esc(r['file'])} · {esc(choice_label(r))} · Received {esc(r['received'])} · FCC status {esc(r['status'])}</p>")
        if not d['applications']:blocks.append('<p>No requests in this snapshot.</p>')
        blocks.append('<h3>FCC history</h3>')
        blocks.extend(f"<p>{esc(e['date'])} · {esc(e['kind'])} · {esc(e['event'])}</p>" for e in d['history'])
        self.browser.setHtml(''.join(blocks))
    def open_link(self,url):
        if url.scheme()=='timeline':
            frn=url.toString()[len('timeline:'):]
            holders=(self.detail or {}).get('switching',{}).get('holders',[])
            if not any(holder['frn']==frn for holder in holders):return
            scroll=self.browser.verticalScrollBar().value()
            if frn in self.expanded_timelines:self.expanded_timelines.remove(frn)
            else:self.expanded_timelines.add(frn)
            self.render_detail();self.browser.verticalScrollBar().setValue(scroll)
        elif url.scheme()=='license':
            parts=url.toString().split(':',2)
            if len(parts)==3:self.inspect(parts[2],parts[1])
        elif url.scheme()=='call':self.inspect(url.toString()[5:])
        elif url.scheme()=='https':QDesktopServices.openUrl(url)
    def cleanup_staging(self):
        if self.staging:self.staging.cleanup();self.staging=None
    def cancel_operation(self,*_,timed_out=False):
        self.cancelled=True
        self.cancel_button.setEnabled(False)
        if self.process:self.process.kill()
        self.set_status('Operation timed out.' if timed_out else 'Canceling…')
    def delete_local_data(self):
        if self.process or self.notify_process or self.syncing:return
        if QMessageBox.question(self,'Delete local data?','Delete downloaded FCC data, preferences, watchlist and saved comparisons? The bundled snapshot remains. The optional reminder timer may remain installed but has no watchlist to notify.')!=QMessageBox.StandardButton.Yes:return
        root=data_directory()
        if root.exists():shutil.rmtree(root)
        self.comparisons=Library()
        self.settings=read_settings();self.appearance.blockSignals(True);self.appearance.setCurrentIndex(self.appearance.findData(self.settings['appearance']));self.appearance.blockSignals(False);self.apply_appearance();self.settings['alerts']=False;self.alerts.setChecked(False)
        # Do not recreate preferences during deletion.
        if root.exists():shutil.rmtree(root)
        self.snapshot_timestamp='';self.update_freshness();self.rows=[];self.selected=None;self.detail=None;self.table.setRowCount(0);self.browser.clear();self.set_status('Local data deleted.')
    def sync(self):
        if self.process is not None or self.syncing:return
        if QMessageBox.question(self,'Sync FCC takes time','Downloading and indexing FCC archives needs at least 12 GiB free and can take several minutes. Start sync?')!=QMessageBox.StandardButton.Yes:return
        # Keep downloads on the database filesystem, rather than a small RAM-backed /tmp.
        root=data_directory()
        try:
            root.mkdir(parents=True,exist_ok=True)
            fcc.check_disk(root/'fcc.sqlite')
            staging=tempfile.TemporaryDirectory(prefix='fcc-sync-',dir=root)
        except (ValueError,OSError) as error:
            message=f'Cannot prepare FCC sync in {root}: {error}'
            self.set_status(message);QMessageBox.warning(self,'Cannot start FCC sync',message);return
        self.compare_button.setEnabled(False);self.add_compare_button.setEnabled(False)
        self.syncing=True;self.cancelled=False;self.staging=staging
        self.show_sync_progress();self.download_archive(0)
    def download_archive(self,index):
        names=['l_amat.zip','a_amat.zip'];target=Path(self.staging.name)/names[index]
        self.set_status('Downloading '+names[index]+'…')
        self.controls.setEnabled(False);self.sync_button.setEnabled(False);self.import_button.setEnabled(False);self.delete_button.setEnabled(False);self.cancel_button.setEnabled(True)
        process=QProcess(self);self.process=process;errors=bytearray()
        curl=str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/curl.exe') if sys.platform=='win32' else 'curl'
        process.setProgram(curl);process.setArguments(['--disable','--fail','--location','--proto','=https','--proto-redir','=https','--max-filesize',str(fcc.MAX_ZIP_BYTES),'--connect-timeout','30','--max-time','1800','--output',str(target),'https://data.fcc.gov/download/pub/uls/complete/'+names[index]])
        process.readyReadStandardError.connect(lambda:errors.extend(bytes(process.readAllStandardError())[-4096:]))
        timer=QTimer(process);timer.setSingleShot(True);timer.timeout.connect(lambda:self.cancel_operation(timed_out=True));timer.start(1800*1000)
        finished=False
        def complete(code,status=None):
            nonlocal finished
            if finished:return
            finished=True;timer.stop();self.process=None;process.deleteLater()
            if code!=0 or self.cancelled or not target.exists() or target.stat().st_size>fcc.MAX_ZIP_BYTES:
                self.syncing=False;self.cleanup_staging();self.cancel_button.setEnabled(False);self.delete_button.setEnabled(True);self.controls.setEnabled(True);self.sync_button.setEnabled(True);self.import_button.setEnabled(True)
                message='FCC sync canceled. Previous snapshot preserved.' if self.cancelled else 'FCC download failed. Previous snapshot preserved.'
                self.compare_button.setEnabled(True);self.add_compare_button.setEnabled(self.selected is not None)
                self.set_status(message);self.finish_sync_progress(message);return
            if index==0:self.download_archive(1)
            else:self.run(['import',str(Path(self.staging.name)/names[0]),str(target)],lambda result:self.load_stats(),mutating=True)
        process.finished.connect(complete);process.errorOccurred.connect(lambda error:complete(-1) if error==QProcess.ProcessError.FailedToStart else None);process.start()
    def import_files(self):
        if self.process is not None or self.syncing:return
        files,_=QFileDialog.getOpenFileNames(self,'Choose l_amat.zip and a_amat.zip','','ZIP archives (*.zip)')
        by_name={Path(f).name.lower():f for f in files}
        if not files:return
        if len(files)!=2 or not all(name in by_name for name in ('l_amat.zip','a_amat.zip')):
            QMessageBox.warning(self,'Choose both archives','Select l_amat.zip and a_amat.zip together.');return
        self.syncing=True;self.show_sync_progress();self.set_status('Importing FCC archives…');self.run(['import',by_name['l_amat.zip'],by_name['a_amat.zip']],lambda result:self.load_stats(),mutating=True)
    def check_reminders(self):
        if sys.platform=='win32':
            if not self.settings['alerts'] or self.process is not None or self.syncing or self.tray is None:return
            if not QSystemTrayIcon.isSystemTrayAvailable() or not QSystemTrayIcon.supportsMessages():return
            def deliver(rows):
                state_path=data_directory()/'reminders.json'
                state=read_settings(state_path);delivered=state.get('delivered',[])
                if not isinstance(delivered,list):delivered=[]
                due=due_reminders(rows,dt.datetime.now().astimezone(),delivered)
                if not due:return
                calls=', '.join(row['call'] for row in due)
                self.tray.showMessage('Callsigns may be available tomorrow',calls+'. Verify eligibility and availability with the FCC. Click to open FCC ULS.',QSystemTrayIcon.MessageIcon.Information,30000)
                delivered.extend(row['call']+'|'+row['estimate'] for row in due)
                state['delivered']=delivered[-512:];save_settings(state,state_path)
            if self.settings['watches']:self.run(['query','watchdates','--term',','.join(self.settings['watches'])],deliver)
            return
        if not self.settings['alerts'] or sys.platform!='linux' or self.notify_process is not None:return
        process=QProcess(self);self.notify_process=process
        command=[sys.executable,'--reminders'] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).resolve()),'--reminders']
        process.setProgram(command[0]);process.setArguments(command[1:])
        def finished(*_):self.notify_process=None;process.deleteLater()
        process.finished.connect(finished);process.start()
    def closeEvent(self,event):
        if self.process is not None:
            QMessageBox.information(self,'Operation in progress','Wait for the current FCC operation to finish before closing CallPerch.');event.ignore();return
        if self.comparison_dialog:self.comparison_dialog.reject()
        self.save();event.accept()

if __name__=='__main__':
    app=QApplication(sys.argv);app.setApplicationName('CallPerch');app.setOrganizationName('KR4GOJ');app.setStyle('Fusion')
    window=Window();window.show()
    if '--smoke-test' in sys.argv:
        QTimer.singleShot(500,window.open_comparison)
        QTimer.singleShot(2000,app.quit)
    sys.exit(app.exec())
