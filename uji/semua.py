"""Jalankan seluruh berkas uji: python3 uji/semua.py"""

import sys
import unittest
from pathlib import Path

if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    sys.path.insert(0, str(folder.parent))
    suite = unittest.TestLoader().discover(str(folder), pattern="uji_*.py")
    hasil = unittest.TextTestRunner(verbosity=1).run(suite)
    sys.exit(0 if hasil.wasSuccessful() else 1)
