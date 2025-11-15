This directory contains license texts for third-party Python packages
that are:

  - Actually imported by the application's source code under src/, and
  - Present either in the frozen runtime (_internal) or in the current
    Python environment (site-packages).

Detection logic:
  1. Parse src/ *.py files with the Python AST and list imported
     top-level modules (e.g., "PySide6", "requests", "numpy").
  2. Find distributions in the frozen environment (_internal) whose
     top-level modules intersect with the imported modules.
  3. Find distributions in the current Python environment whose
     top-level modules intersect with the imported modules.
  4. For each relevant distribution, collect license texts from:
     (a) Frozen environment (dist-info / package directories)
     (b) Current Python environment (site-packages)
     (c) Predefined official license URLs

THIRD_PARTY_LICENSES_SUMMARY.txt lists the detected packages and the
corresponding license files.

Note: Some components (e.g., Python runtime, Qt / Qt for Python
(PySide6), native libraries without explicit metadata) may still
require additional manual license files or notices. Please review and
adjust as needed.
