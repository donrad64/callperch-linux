# Third-party licensing

The root MIT license applies to CallPerch's original Linux application code and documentation. It does not replace licenses for dependencies, upstream notices, public FCC records, or any other project.

Runtime dependencies include Qt, PySide6-Essentials and Shiboken6 (6.8.3), with their applicable LGPL/GPL and third-party licenses, and Python under its PSF terms. Packaging uses PyInstaller and its dependencies under their respective licenses. Native packages retain replaceable shared Qt libraries.

See [release/linux/THIRD-PARTY-NOTICES.md](release/linux/THIRD-PARTY-NOTICES.md) for matching upstream source and build instructions. `release/linux/third-party-notices.zip` contains upstream Qt/PySide notices used in packaging. `release/linux/Python-LICENSE.txt` contains Python's license. Build tooling also collects installed distribution notices. No modifications are made to Qt, PySide, or Shiboken.

FCC databases and downloaded archives are excluded. Downloading public FCC records does not make their contents part of the application's MIT license.
