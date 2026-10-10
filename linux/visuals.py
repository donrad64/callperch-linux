"""Resolution-independent desktop artwork with deliberate type hierarchy."""
from PySide6.QtCore import Qt,QRectF,QSize,QPointF
from PySide6.QtGui import QColor,QFont,QIcon,QPainter,QPen,QPixmap,QPolygonF,QPalette
from PySide6.QtWidgets import QWidget,QComboBox,QPushButton

class CallsignPreview(QWidget):
    def __init__(self,call,kind,parent=None):
        super().__init__(parent);self.call=call;self.kind=kind
        self.setMinimumSize(180,160);self.setMaximumHeight(200)
        self.setAccessibleName(('QSL card' if kind=='qsl' else 'License plate')+' appearance preview for '+call)
    def sizeHint(self):return QSize(360,180)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r=QRectF(self.rect()).adjusted(1,1,-1,-1)
        qsl=self.kind=='qsl'
        p.setPen(QPen(QColor('#31516a' if qsl else '#c8c3ad'),1))
        p.setBrush(QColor('#19394e' if qsl else '#f7f3e5'));p.drawRoundedRect(r,12,12)
        def label(text,rect,size,color,weight=QFont.Weight.Normal,family=None):
            font=QFont(family or self.font().family());font.setPixelSize(int(size));font.setWeight(weight)
            p.setFont(font);p.setPen(QColor(color));p.drawText(rect,Qt.AlignmentFlag.AlignCenter,text)
        width=r.width();height=r.height()
        small=max(10,min(12,width/28))
        if qsl:
            label('QSL  /  CONFIRMING OUR CONTACT',QRectF(r.x()+16,r.y()+17,width-32,20),small,'#a9c4d3',QFont.Weight.Medium)
            label(self.call,QRectF(r.x()+16,r.y()+47,width-32,height-99),min(56,(width-40)/(len(self.call)*.7)),'#ffffff',QFont.Weight.Bold)
            p.setPen(QPen(QColor('#496777'),1));p.drawLine(int(r.x()+24),int(r.bottom()-39),int(r.right()-24),int(r.bottom()-39))
            label('AMATEUR RADIO STATION',QRectF(r.x()+16,r.bottom()-31,width-32,18),small,'#a9c4d3',QFont.Weight.Medium)
        else:
            inner=r.adjusted(10,10,-10,-10);p.setPen(QPen(QColor('#aaa68f'),1));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRoundedRect(inner,7,7)
            label('AMATEUR RADIO',QRectF(r.x()+20,r.y()+22,width-40,20),small,'#6b685b',QFont.Weight.DemiBold)
            label(self.call,QRectF(r.x()+20,r.y()+48,width-40,height-88),min(58,(width-50)/(len(self.call)*.65)),'#202b33',QFont.Weight.Bold,'Bahnschrift' if __import__('sys').platform=='win32' else self.font().family())
            # Mounting holes make this a plate sample rather than a second QSL card.
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#b7b29e'))
            for x in [r.x()+24,r.right()-24]:p.drawEllipse(QRectF(x-2,r.y()+22,4,4))
        p.end()

def coffee_icon():
    pixmap=QPixmap(48,48);pixmap.fill(Qt.GlobalColor.transparent)
    p=QPainter(pixmap);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor('#70461c'),3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap));p.setBrush(QColor('#fff8e9'))
    p.drawRoundedRect(QRectF(9,15,24,23),5,5);p.setBrush(Qt.BrushStyle.NoBrush);p.drawArc(QRectF(27,19,13,14),-90*16,180*16)
    p.drawLine(8,41,35,41);p.drawLine(16,5,16,10);p.drawLine(25,5,25,10);p.end()
    return QIcon(pixmap)


class AppearanceSelector(QComboBox):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setStyleSheet('QComboBox { padding-right: 28px; } QComboBox::drop-down { border: none; width: 24px; } QComboBox::down-arrow { image: none; }')
    def paintEvent(self,event):
        super().paintEvent(event)
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x=self.width()-17;y=self.height()/2
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(self.palette().color(QPalette.ColorRole.ButtonText))
        p.drawPolygon(QPolygonF([QPointF(x-4,y-2),QPointF(x+4,y-2),QPointF(x,y+2)]));p.end()

class LoadingOverlay(QWidget):
    """Animated progress over stale results during an asynchronous FCC query."""
    def __init__(self,parent=None,cancel=None):
        from PySide6.QtCore import QTimer
        super().__init__(parent);self.message='Loading…';self.angle=0
        self.timer=QTimer(self);self.timer.setInterval(70);self.timer.timeout.connect(self.advance)
        self.setAccessibleName(self.message)
        self.cancel_button=QPushButton('Cancel',self);self.cancel_button.setAccessibleName('Cancel current FCC query');self.cancel_button.clicked.connect(cancel or (lambda:None))
        self.cancel_button.setEnabled(False)
    def resizeEvent(self,event):
        self.cancel_button.setGeometry(int(self.width()/2-75),int(self.height()/2+66),150,36)
        super().resizeEvent(event)
    def advance(self):self.angle=(self.angle+30)%360;self.update()
    def showEvent(self,event):self.timer.start();super().showEvent(event)
    def hideEvent(self,event):self.timer.stop();super().hideEvent(event)
    def paintEvent(self,event):
        import math
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        background=self.palette().color(QPalette.ColorRole.Window);background.setAlpha(235);p.fillRect(self.rect(),background)
        color=self.palette().color(QPalette.ColorRole.Link)
        cx=self.width()/2;cy=self.height()/2-20
        for tick in range(12):
            shade=QColor(color);shade.setAlpha(35+int(220*tick/11))
            p.setPen(QPen(shade,3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
            a=math.radians(self.angle+tick*30)
            p.drawLine(QPointF(cx+math.cos(a)*11,cy+math.sin(a)*11),QPointF(cx+math.cos(a)*20,cy+math.sin(a)*20))
        p.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        font=self.font();font.setPixelSize(15);font.setWeight(QFont.Weight.Medium);p.setFont(font)
        p.drawText(QRectF(12,cy+34,self.width()-24,40),Qt.AlignmentFlag.AlignCenter,self.message);p.end()
