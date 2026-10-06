import os,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from PySide6.QtWidgets import QApplication
from callperch import Window
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import test_fcc as fixtures
from core import phonetic,due_reminders,read_settings,save_settings
import datetime as dt

class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.prior=os.environ.get('XDG_DATA_HOME');os.environ['XDG_DATA_HOME']=self.temp.name
        self.fixture=fixtures.FCCTests();self.fixture.setUp()
        # Ordinary UI tests must not launch Linux-only desktop notification helpers.
        save_settings({'watches':[], 'alerts':False})
        self.window=Window();self.window.database=lambda:self.fixture.db
    def tearDown(self):
        if self.window.process is not None:self.window.process.kill();self.window.process.waitForFinished()
        if self.window.notify_process is not None:self.window.notify_process.kill();self.window.notify_process.waitForFinished()
        self.window.timer.stop();self.window.deleteLater();self.app.processEvents();self.fixture.tearDown();self.temp.cleanup()
        if self.prior is None:os.environ.pop('XDG_DATA_HOME',None)
        else:os.environ['XDG_DATA_HOME']=self.prior
    def wait(self,predicate):
        end=time.monotonic()+15
        while not predicate() and time.monotonic()<end:self.app.processEvents();time.sleep(.01)
        self.assertTrue(predicate(),self.window.status.text())
    def test_live_engine_query_and_address_render(self):
        self.wait(lambda:self.window.process is None and 'licenses' in self.window.status.text())
        self.window.term.setText('K1AB');self.window.refresh()
        self.wait(lambda:self.window.process is None and bool(self.window.rows))
        self.assertEqual(self.window.rows[0]['call'],'K1AB')
        self.window.choose(0,0);self.wait(lambda:self.window.detail is not None)
        self.assertIn('Other callsigns at this address',self.window.browser.toPlainText())
        self.window.toggle_watch();self.assertIn('K1AB',read_settings()['watches'])
        self.window.toggle_watch();self.assertNotIn('K1AB',read_settings()['watches'])
    def test_switching_timeline_from_engine(self):
        self.wait(lambda:self.window.process is None)
        c=self.fixture.connection()
        for i,(call,date,cancel) in enumerate([('K1AB','2018-01-01','2019-01-01'),('N1AB','2019-01-01','2020-01-01'),('K1AB','2020-01-01','2021-01-01'),('N1AB','2021-01-01','')],200):
            c.execute('INSERT INTO licenses VALUES(?,?,?,?,?,?,?,?,?,?)',(str(i),call,'C',date,'2030-01-01',1,'1x2','',cancel,40))
            c.execute('INSERT INTO entities VALUES(?,?,?,?,?)',('L',str(i),'<TEST HOLDER>','TEST CITY','MA'))
            c.execute('INSERT INTO holder_identity VALUES(?,?,?,?)',('L',str(i),'1234567890','I'))
        c.commit();c.close()
        self.window.inspect('K1AB');self.wait(lambda:self.window.detail is not None)
        from PySide6.QtCore import QUrl
        text=self.window.browser.toPlainText()
        self.assertIn('Assignment timeline · Expand',text)
        self.assertNotIn('Granted 2018-01-01',text)
        self.window.browser.anchorClicked.emit(QUrl('timeline:1234567890'))
        text=self.window.browser.toPlainText()
        for expected in ['Repeated callsign switching','<TEST HOLDER>','FRN 1234567890','2 returns','2 before ordinary release','Granted 2020-01-01','Canceled 2019-01-01','Assignment timeline']:
            self.assertIn(expected,text)
        self.assertIn('call:N1AB',self.window.browser.toHtml())
        self.assertIn('does not establish intent',text)
        self.window.render_detail()
        self.assertIn('Granted 2018-01-01',self.window.browser.toPlainText())
        self.window.browser.anchorClicked.emit(QUrl('timeline:1234567890'))
        self.assertNotIn('Granted 2018-01-01',self.window.browser.toPlainText())
        self.assertIn('Assignment timeline · Expand',self.window.browser.toPlainText())
        self.window.browser.anchorClicked.emit(QUrl('timeline:1234567890'))
        self.window.inspect('N1AB');self.wait(lambda:self.window.process is None)
        self.assertNotIn('Granted 2018-01-01',self.window.browser.toPlainText())

    def test_switching_snapshot_states(self):
        self.wait(lambda:self.window.process is None)
        self.window.selected='K1AB'
        for state,expected in [('needs_sync','Sync FCC'),('identity_unavailable','cannot be assessed'),('ready','No qualifying pattern')]:
            self.window.detail={'licenses':[],'applications':[],'history':[],'switching':{'state':state,'holders':[]}}
            self.window.render_detail();self.assertIn(expected,self.window.browser.toPlainText())

    def test_sync_dialog_import_success_and_done(self):
        from unittest.mock import patch
        import shutil
        self.wait(lambda:self.window.process is None)
        paths=[]
        for source,name in [('l.zip','l_amat.zip'),('a.zip','a_amat.zip')]:
            path=Path(self.temp.name)/name;shutil.copy2(self.fixture.root/source,path);paths.append(str(path))
        with patch('callperch.QFileDialog.getOpenFileNames',return_value=(paths,'')):
            self.window.import_files()
        dialog=self.window.sync_dialog
        self.assertTrue(dialog.isVisible());self.assertTrue(dialog.isModal());self.assertTrue(dialog.running)
        self.assertEqual(dialog.progress.minimum(),0);self.assertEqual(dialog.progress.maximum(),0)
        self.wait(lambda:not dialog.running)
        self.assertIn('complete',dialog.message.text());self.assertEqual(dialog.button.text(),'Done')
        self.assertTrue(dialog.isVisible());self.assertFalse(self.window.syncing)
        dialog.button.click();self.app.processEvents()
        self.assertFalse(self.window.syncing)

    def test_sync_dialog_failed_import_preserves_snapshot(self):
        from unittest.mock import patch
        self.wait(lambda:self.window.process is None)
        paths=[]
        for name in ['l_amat.zip','a_amat.zip']:
            path=Path(self.temp.name)/name;path.write_bytes(b'not a zip');paths.append(str(path))
        with patch('callperch.QFileDialog.getOpenFileNames',return_value=(paths,'')):
            self.window.import_files()
        dialog=self.window.sync_dialog;self.wait(lambda:not dialog.running)
        self.assertIn('failed',dialog.message.text());self.assertIn('preserved',dialog.message.text())
        self.assertTrue(dialog.isVisible());dialog.button.click()

    def test_sync_dialog_cancel_stops_import(self):
        from unittest.mock import patch
        import callperch
        self.wait(lambda:self.window.process is None)
        paths=[]
        for name in ['l_amat.zip','a_amat.zip']:
            path=Path(self.temp.name)/name;path.write_bytes(b'synthetic');paths.append(str(path))
        with patch('callperch.QFileDialog.getOpenFileNames',return_value=(paths,'')), patch.object(callperch,'engine_command',return_value=[sys.executable,'-c','import time;time.sleep(30)']):
            self.window.import_files()
            dialog=self.window.sync_dialog;dialog.button.click()
            self.wait(lambda:self.window.process is None)
        self.assertFalse(dialog.running);self.assertFalse(self.window.syncing)
        self.assertIn('canceled',dialog.message.text());self.assertTrue(dialog.isVisible());dialog.button.click()

    def test_sync_dialog_close_requests_cancel_once(self):
        from callperch import SyncProgressDialog
        requests=[];dialog=SyncProgressDialog(self.window,lambda:requests.append(True));dialog.show()
        dialog.update_message('Downloading l_amat.zip…')
        self.assertIn('Downloading',dialog.message.text())
        dialog.reject();dialog.reject();self.assertEqual(requests,[True]);self.assertTrue(dialog.isVisible())
        self.assertFalse(dialog.button.isEnabled())
        dialog.finish('FCC sync canceled. Previous snapshot preserved.')
        dialog.update_message('Unrelated search status')
        self.assertIn('canceled',dialog.message.text());dialog.button.click();self.assertFalse(dialog.isVisible())

    def test_sidebar_navigation_and_keyboard_selection(self):
        self.wait(lambda:self.window.process is None and 'licenses' in self.window.status.text())
        self.window.nav_buttons[2].click()
        self.assertEqual(self.window.mode.currentData(),'upcoming')
        self.assertTrue(self.window.term.isHidden())
        self.assertFalse(self.window.horizon.isHidden())
        self.wait(lambda:self.window.process is None)
        self.window.nav_buttons[0].click()
        self.wait(lambda:self.window.process is None)
        self.window.term.setText('K1AB');self.window.refresh()
        self.wait(lambda:self.window.process is None and bool(self.window.rows))
        self.window.table.selectRow(0)
        self.wait(lambda:self.window.detail is not None)
        self.assertEqual(self.window.selected,'K1AB')

    def test_availability_filters_wait_for_refresh(self):
        from unittest.mock import patch
        self.wait(lambda:self.window.process is None and 'licenses' in self.window.status.text())
        for mode in ('available','upcoming'):
            self.window.mode.setCurrentIndex(self.window.mode.findData(mode))
            self.wait(lambda:self.window.process is None)
            with patch.object(self.window,'run') as engine:
                self.window.region.setCurrentIndex(3)
                self.window.form.setCurrentIndex(2)
                self.window.sort.setCurrentIndex(1)
                self.window.direction.setCurrentIndex(1)
                self.window.horizon.setValue(90)
                self.app.processEvents()
                engine.assert_not_called()
                self.window.search.click()
                engine.assert_called_once()
                arguments=engine.call_args.args[0]
                self.assertEqual(arguments[:2],['query',mode])
                for flag,value in [('--region','2'),('--format','2x1'),('--sort','cw'),('--direction','desc'),('--horizon','90')]:
                    self.assertEqual(arguments[arguments.index(flag)+1],value)
            self.window.region.setCurrentIndex(0);self.window.form.setCurrentIndex(0)
            self.window.sort.setCurrentIndex(0);self.window.direction.setCurrentIndex(0)
            self.window.horizon.setValue(180)

    def test_row_stars_save_and_remove_watchlist_entries(self):
        self.wait(lambda:self.window.process is None and 'licenses' in self.window.status.text())
        self.window.term.setText('K1AB');self.window.refresh()
        self.wait(lambda:self.window.process is None and bool(self.window.rows))
        self.window.table.cellWidget(0,0).click()
        self.assertIn('K1AB',read_settings()['watches'])
        self.assertEqual(self.window.table.cellWidget(0,0).text(),'★')
        self.window.mode.setCurrentIndex(self.window.mode.findData('watchlist'))
        self.wait(lambda:self.window.process is None and bool(self.window.rows))
        self.window.table.cellWidget(0,0).click()
        self.assertNotIn('K1AB',read_settings()['watches'])
        self.assertEqual(self.window.rows,[])

    def test_morse_notation_and_saved_appearance(self):
        from PySide6.QtCore import Qt
        self.window.selected='K1AB';self.window.detail={'licenses':[],'applications':[],'history':[],'same_address':{'state':'unknown'}}
        self.window.render_detail()
        self.assertIn('-.-   .----   .-   -...',self.window.browser.toPlainText().replace('\xa0',' '))
        self.window.appearance.setCurrentIndex(self.window.appearance.findData('dark'))
        self.assertTrue(self.window.dark)
        self.assertEqual(read_settings()['appearance'],'dark')
        self.window.system_appearance_changed(Qt.ColorScheme.Light)
        self.assertTrue(self.window.dark)
        self.window.appearance.setCurrentIndex(self.window.appearance.findData('light'))
        self.assertFalse(self.window.dark)
        self.window.appearance.setCurrentIndex(self.window.appearance.findData('system'))
        self.window.system_appearance_changed(Qt.ColorScheme.Dark)
        self.assertTrue(self.window.dark)
        self.window.system_appearance_changed(Qt.ColorScheme.Light)
        self.assertFalse(self.window.dark)
        self.assertEqual(read_settings()['appearance'],'system')

    def test_unassigned_watch_remains_inspectable(self):
        self.wait(lambda:self.window.process is None and 'licenses' in self.window.status.text())
        self.window.settings['watches']=['N7ZZ']
        self.window.mode.setCurrentIndex(self.window.mode.findData('watchlist'))
        self.wait(lambda:self.window.process is None and bool(self.window.rows))
        self.assertEqual(self.window.rows[0]['call'],'N7ZZ')
        self.window.choose(0,0);self.wait(lambda:self.window.detail is not None)
        self.assertIn('No license record',self.window.browser.toPlainText())
    def test_escaped_untrusted_fcc_text(self):
        self.window.selected='K1AB';self.window.detail={'licenses':[],'applications':[{'name':'<script>unsafe</script>','file':'1','rank':1,'received':'2026-01-01','status':'1'}],'history':[],'same_address':{'state':'incomplete'}}
        self.window.render_detail();self.assertIn('<script>unsafe</script>',self.window.browser.toPlainText())
        self.assertIn('incomplete',self.window.browser.toPlainText())
    def test_delete_removes_only_test_local_data(self):
        self.wait(lambda:self.window.process is None and 'licenses' in self.window.status.text())
        from unittest.mock import patch
        from core import data_directory
        from PySide6.QtWidgets import QMessageBox
        root=data_directory();root.mkdir(parents=True,exist_ok=True);(root/'fcc.sqlite').write_text('synthetic test data')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):self.window.delete_local_data()
        self.assertFalse(root.exists());self.assertEqual(self.window.rows,[])
        self.assertTrue(self.fixture.db.exists())
    def test_delete_waits_for_reminder_helper(self):
        self.wait(lambda:self.window.process is None and 'licenses' in self.window.status.text())
        from unittest.mock import patch
        from core import data_directory
        from PySide6.QtWidgets import QMessageBox
        root=data_directory();(root/'fcc.sqlite').write_text('synthetic test data')
        self.window.notify_process=object()
        try:
            with patch.object(QMessageBox,'question') as confirmation:
                self.window.delete_local_data()
                confirmation.assert_not_called()
            self.assertTrue((root/'fcc.sqlite').exists())
        finally:self.window.notify_process=None
    def test_address_hidden_until_explicit_reveal(self):
        self.fixture.seed_addresses();self.window.selected='K1AB'
        self.window.detail=fixtures.fcc.query(self.fixture.db,'detail','K1AB');self.window.render_detail()
        self.assertNotIn('123 MAIN ST',self.window.browser.toPlainText())
        self.window.reveal_address.setChecked(True)
        self.assertIn('123 MAIN ST',self.window.browser.toPlainText())
    def test_cancel_stops_helper(self):
        self.wait(lambda:self.window.process is None and 'licenses' in self.window.status.text())
        from PySide6.QtCore import QProcess,QTimer
        import callperch
        prior=callperch.engine_command
        callperch.engine_command=lambda arguments:[sys.executable,'-c','import time;time.sleep(30)']
        try:
            self.window.run(['query','stats'],lambda result:self.fail('Canceled operation returned success'))
            self.window.cancel_operation()
            self.wait(lambda:self.window.process is None)
            self.assertIn('canceled',self.window.status.text())
        finally:callperch.engine_command=prior
    def test_portable_metrics_and_reminders(self):
        self.assertEqual(phonetic('KR4GOJ')['weight'],13)
        self.assertIsNone(phonetic('K1?'))
        dates=[{'call':'K1AB','estimate':'2026-10-05'}]
        self.assertEqual(due_reminders(dates,dt.datetime(2026,10,4,8),[]),[])
        self.assertEqual(due_reminders(dates,dt.datetime(2026,10,4,9),[]),dates)
        self.assertEqual(due_reminders(dates,dt.datetime(2026,10,4,10),['K1AB|2026-10-05']),[])
    def test_preferences_validation_and_atomic_save(self):
        path=Path(self.temp.name)/'settings.json';path.write_text('{broken')
        self.assertEqual(read_settings(path)['watches'],[])
        save_settings({'watches':[' k1ab ','K1AB',3],'sort':'bad','appearance':'invalid'},path)
        self.assertEqual(read_settings(path)['watches'],['K1AB']);self.assertEqual(read_settings(path)['sort'],'date');self.assertEqual(read_settings(path)['appearance'],'system')

if __name__=='__main__':unittest.main()
