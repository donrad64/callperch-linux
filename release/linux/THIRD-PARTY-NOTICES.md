# CallPerch Linux third-party components

CallPerch includes unmodified Qt 6.8.3, PySide6-Essentials 6.8.3 and Shiboken6 6.8.3 shared libraries, distributed under their applicable LGPL/GPL and third-party terms. The accompanying directories contain upstream license and copyright notices, including the GNU LGPL v3 and GNU GPL v3 texts. Qt licensing does not grant an open-source license to CallPerch itself.

The shared libraries remain separate from the CallPerch executable under `/opt/callperch/_internal`. Users may replace them with compatible versions and reverse engineer the combined application for debugging modifications to these libraries, as permitted by their licenses. No modifications were made to Qt, PySide or Shiboken.

Matching upstream source and build instructions are freely available:

- Qt 6.8.3: https://download.qt.io/archive/qt/6.8/6.8.3/single/qt-everywhere-src-6.8.3.tar.xz
- PySide and Shiboken 6.8.3: https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/pyside-setup-everywhere-src-6.8.3.tar.xz
- Qt build instructions: https://doc.qt.io/qt-6.8/build-sources.html
- PySide/Shiboken build instructions: https://doc.qt.io/qtforpython-6.8/building_from_source/index.html

These packages use the upstream PyPI wheels. Qt/PySide notices were extracted from the matching official source archives because these older wheels omit notice files. PyInstaller notices are collected from the installed distribution. The embedded Python runtime retains Python's license under its applicable PSF terms: https://docs.python.org/3.12/license.html .
