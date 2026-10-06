"""Shared application colors for the Linux light and dark appearances."""
from PySide6.QtGui import QColor,QPalette

LIGHT_STYLE = '\n            QMainWindow, QWidget { background: #f7f9fc; color: #182c46; font-size: 13px; }\n            QWidget#sidebar { background: #edf2f8; border-right: 1px solid #dce3ec; }\n            QLabel { background: transparent; }\n            QPushButton#star { background: transparent; border: none; color: #b07808; font-size: 23px; padding: 2px; }\n            QLabel#heading { font-size: 28px; font-weight: bold; }\n            QLabel#muted { color: #65758b; }\n            QPushButton { background: white; border: 1px solid #d8e0eb; border-radius: 7px; padding: 8px 12px; }\n            QPushButton:hover { background: #e8f1ff; border-color: #9cbce8; }\n            QPushButton:checked, QPushButton#primary { background: #2166b5; color: white; border-color: #2166b5; }\n            QPushButton:disabled { color: #93a0af; background: #f0f3f7; }\n            QPushButton#navigation { text-align: left; padding: 12px; border: none; background: transparent; }\n            QPushButton#navigation:checked { color: #164c86; background: #d8e8fb; font-weight: bold; }\n            QLineEdit, QComboBox, QSpinBox { background: white; border: 1px solid #d8e0eb; border-radius: 6px; padding: 7px; }\n            QTableWidget, QTextBrowser { background: white; border: 1px solid #dce3ec; border-radius: 8px; }\n            QTableWidget::item { padding: 10px; border-bottom: 1px solid #edf1f6; }\n            QTableWidget::item:selected { background: #e0edfc; color: #153e70; }\n            QHeaderView::section { background: #edf2f8; color: #65758b; border: none; padding: 10px; }\n            QCheckBox { spacing: 8px; }\n            QSplitter::handle { background: #dce3ec; width: 1px; }\n        '

DARK_COLORS = {
    '#f7f9fc':'#17202d', '#182c46':'#e5edf8', '#edf2f8':'#202c3c',
    '#dce3ec':'#38495f', '#b07808':'#f1bf57', '#65758b':'#abbad0',
    '#d8e0eb':'#40526b', '#e8f1ff':'#2d4260', '#9cbce8':'#729ad0',
    '#2166b5':'#2878cf', '#93a0af':'#7b8ba2', '#f0f3f7':'#253144',
    '#164c86':'#d8eaff', '#d8e8fb':'#304c70', '#edf1f6':'#2c3b50',
    '#e0edfc':'#304c70', '#153e70':'#e0edff',
}

def stylesheet(dark):
    import re
    style=LIGHT_STYLE
    if dark:
        style=re.sub(r'#[0-9a-f]{6}',lambda match:DARK_COLORS.get(match[0],match[0]),style)
        style=style.replace('background: white','background: #202c3c')
    return style

def palette(dark):
    result=QPalette()
    colors={'Window': '#17202d' if dark else '#f7f9fc',
            'Base': '#202c3c' if dark else '#ffffff',
            'AlternateBase': '#253144' if dark else '#edf2f8',
            'Text': '#e5edf8' if dark else '#182c46',
            'WindowText': '#e5edf8' if dark else '#182c46',
            'Button': '#202c3c' if dark else '#ffffff',
            'ButtonText': '#e5edf8' if dark else '#182c46',
            'Highlight': '#304c70' if dark else '#e0edfc',
            'HighlightedText': '#e0edff' if dark else '#153e70',
            'Link': '#8bc1ff' if dark else '#2166b5',
            'ToolTipBase': '#202c3c' if dark else '#ffffff',
            'ToolTipText': '#e5edf8' if dark else '#182c46'}
    for role,color in colors.items():result.setColor(getattr(QPalette.ColorRole,role),QColor(color))
    for role in ('Text','WindowText','ButtonText'):
        result.setColor(QPalette.ColorGroup.Disabled,getattr(QPalette.ColorRole,role),QColor('#7b8ba2' if dark else '#93a0af'))
    return result
