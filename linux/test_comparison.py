import copy
import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from comparison import *
from comparison_audio import cw_samples
from PySide6.QtWidgets import QApplication,QComboBox,QMessageBox
from comparison_ui import ComparisonDialog
from unittest.mock import patch

class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.library=Library(Path(self.temp.name)/'comparisons.json')
        self.library.add('K8ZT');self.library.add('W0XXX');self.w=self.library.workspace
    def tearDown(self):self.temp.cleanup()
    def test_mac_reference_metrics_and_audio_timing(self):
        a=analysis('K8ZT')
        self.assertEqual((a['elements'],a['signal'],a['cwTime']),(13,29,47))
        self.assertAlmostEqual(a['cwTime']*1.2/20,2.82)
        # Segment rounding can differ by less than one sample per segment.
        self.assertLess(abs(len(cw_samples('K8ZT',20))/2/22050-2.82),.002)
        self.assertEqual(a['spoken'],'Kilo Eight Zulu Tango')
    def test_partial_ratings_never_give_advantage(self):
        initial=score(self.w,self.w['candidates'][0]);self.w['candidates'][0]['ratings']['appearance']=1
        self.assertEqual(score(self.w,self.w['candidates'][0]),initial)
        self.assertIn('appearance',pending_categories(self.w))
        self.w['candidates'][1]['ratings']['appearance']=10
        self.assertIn('appearance',scored_categories(self.w))
        self.w['weights']=dict.fromkeys(TITLES,0);self.assertIsNone(score(self.w,self.w['candidates'][0]))
        self.w['weights']['appearance']=3
        self.assertEqual([score(self.w,c) for c in self.w['candidates']],[1,10])
        self.w['candidates'][0]['ratings']['appearance']=10
        self.assertEqual([c['call'] for c in ranked(self.w)],['K8ZT','W0XXX'])
    def test_fixed_scales_and_initials(self):
        initial=score(self.w,self.w['candidates'][0]);self.library.add('N1A')
        self.assertEqual(score(self.w,self.w['candidates'][0]),initial)
        self.w['initials']='zt';self.assertEqual(score(self.w,self.w['candidates'][0]),initial)
        self.assertIn('requested letters ZT',explanation(self.w,self.w['candidates'][0]))
        self.assertEqual(preset('CW')['rhythm'],3);self.assertEqual(preset('SSB')['phonetics'],3)
    def test_validation_limit_and_roundtrip(self):
        for call in ['', 'K8ZT/P','K88ZT','K8','<script>','K8Å']:
            self.assertIsNotNone(self.library.add(call))
        self.assertIsNotNone(self.library.add(' k8zt '))
        for n in range(8):self.assertIsNone(self.library.add('N'+str(n)+'AB'))
        self.assertIsNotNone(self.library.add('K1ZZ'))
        self.w['name']='Favorite, "calls"';self.assertTrue(self.library.save())
        expected=copy.deepcopy(self.w);self.w['name']='Draft edit';self.library.persist()
        loaded=Library(self.library.path);self.assertEqual(loaded.saved[0],expected);self.assertEqual(loaded.workspace['name'],'Draft edit')
        output=Path(self.temp.name)/'test.csv';self.library.export(output)
        with output.open() as stream:rows=list(csv.reader(stream))
        self.assertEqual(len(rows),11);self.assertTrue(all(len(row)==len(rows[0]) for row in rows))
        self.assertIn('CW transmission time priority',rows[0])
    def test_corrupt_preferences(self):
        self.library.path.write_text('{')
        self.assertEqual(Library(self.library.path).workspace['candidates'],[])
        w=clean_workspace(dict(candidates=[None,dict(call='K8ZT',ratings={'appearance':True}),dict(call='k8zt'),dict(call='<bad>')],weights={'cwTime':100},wpm=-3))
        self.assertEqual(w['wpm'],5);self.assertEqual(w['weights']['cwTime'],3);self.assertEqual(w['candidates'],[dict(call='K8ZT',ratings={})])

class WindowsAudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_windows_audio_uses_isolated_helper(self):
        from comparison_audio import Audio
        audio=Audio()
        with patch.object(sys,'platform','win32'),patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable','/test/CallPerch.exe'),patch.object(audio,'start') as start:
            audio.speak('Kilo Eight Zulu Tango')
            self.assertEqual(start.call_args.args,([str(Path('/test/CallPerch.exe').with_name('CallPerchEngine.exe')),'--speak'],'Kilo Eight Zulu Tango'))
            audio.play('K8ZT',20)
            self.assertEqual(start.call_args.args[0][:2],[str(Path('/test/CallPerch.exe').with_name('CallPerchEngine.exe')),'--play-wav'])
            self.assertTrue(Path(start.call_args.args[0][-1]).exists())
        audio.stop()

class ComparisonUITests(unittest.TestCase):
    setUp=ComparisonTests.setUp
    tearDown=ComparisonTests.tearDown
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_workspace_controls_navigation_and_saved_copy(self):
        inspected=[];dialog=ComparisonDialog(None,self.library,['N1AB'],inspected.append)
        dialog.show();self.app.processEvents()
        dialog.change_preset(1);self.assertEqual(self.w['weights'],preset('CW'))
        dialog.preview.add('K8ZT');dialog.expanded.add('K8ZT');dialog.render();self.app.processEvents()
        rating=next(c for c in dialog.findChildren(QComboBox) if c.accessibleName()=='K8ZT Visual appearance')
        rating.activated.emit(3);self.app.processEvents();self.assertEqual(self.w['candidates'][0]['ratings']['appearance'],3)
        dialog.save_comparison();dialog.new();self.assertFalse(self.library.workspace['candidates'])
        dialog.open_saved(1);self.assertEqual(self.library.workspace['candidates'][0]['ratings']['appearance'],3)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):dialog.delete_saved()
        self.assertFalse(self.library.saved);self.assertEqual(len(self.library.workspace['candidates']),2)
        dialog.records('K8ZT');self.assertEqual(inspected,['K8ZT']);dialog.deleteLater();self.app.processEvents()

if __name__=='__main__':unittest.main()
