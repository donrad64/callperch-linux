"""Offline CW and phonetics through installed desktop audio tools."""
import math
import shutil
import struct
import sys
import tempfile
import wave
from pathlib import Path
from PySide6.QtCore import QObject,QProcess,Signal
import fcc

def cw_samples(call,wpm,sample_rate=22050):
    dot=1.2/max(5,min(50,wpm));samples=bytearray()
    def append(units,tone):
        count=int(sample_rate*dot*units);ramp=min(110,count//2)
        for i in range(count):
            envelope=min(1,min(i,count-1-i)/max(1,ramp))
            value=int(math.sin(2*math.pi*600*i/sample_rate)*10000*envelope) if tone else 0
            samples.extend(struct.pack('<h',value))
    for n,letter in enumerate(call):
        code=fcc.MORSE[letter]
        for i,mark in enumerate(code):
            append(1 if mark=='.' else 3,True)
            if i<len(code)-1: append(1,False)
        if n<len(call)-1: append(3,False)
    return samples

class Audio(QObject):
    error=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.process=None;self.directory=None
    def stop(self):
        if self.process:
            process=self.process;self.process=None;process.kill();process.waitForFinished(1000);process.deleteLater()
        if self.directory: self.directory.cleanup();self.directory=None
    def start(self,command,input_text=None):
        process=QProcess(self);self.process=process;process.setProgram(command[0]);process.setArguments(command[1:])
        def done(code,*_):
            if self.process is not process: return
            if code: self.error.emit('Audio playback failed. Check your sound device and installed audio tools.')
            self.stop()
        process.finished.connect(done)
        process.errorOccurred.connect(lambda _:done(-1))
        if input_text is not None:
            process.started.connect(lambda:(process.write(input_text.encode('utf-8')),process.closeWriteChannel()))
        process.start()
    def windows_command(self,mode):
        if getattr(sys,'frozen',False):return [str(Path(sys.executable).with_name('CallPerchEngine.exe')),mode]
        return [sys.executable,str(Path(__file__).resolve().parents[1]/'windows/engine.py'),mode]
    def play(self,call,wpm):
        self.stop();program='windows' if sys.platform=='win32' else next((shutil.which(p) for p in ('paplay','aplay','afplay') if shutil.which(p)),None)
        if not program: self.error.emit('CW playback needs paplay (pulseaudio-utils) or aplay (alsa-utils).');return
        self.directory=tempfile.TemporaryDirectory(prefix='callperch-audio-');path=Path(self.directory.name)/'cw.wav'
        try:
            with wave.open(str(path),'wb') as output:
                output.setnchannels(1);output.setsampwidth(2);output.setframerate(22050);output.writeframes(cw_samples(call,wpm))
            self.start(self.windows_command('--play-wav')+[str(path)] if sys.platform=='win32' else [program,str(path)])
        except OSError as error: self.stop();self.error.emit('Could not play CW: '+str(error))
    def speak(self,text):
        self.stop()
        if sys.platform=='win32':self.start(self.windows_command('--speak'),text);return
        program=shutil.which('espeak-ng') or shutil.which('espeak')
        if program: self.start([program,'-v','en-us','-s','150',text])
        elif sys.platform=='darwin' and shutil.which('say'): self.start([shutil.which('say'),'-r','150',text])
        else: self.error.emit('Spoken phonetics needs the local espeak-ng speech package.')
