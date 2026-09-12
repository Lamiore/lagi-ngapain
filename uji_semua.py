"""Jalankan seluruh berkas uji: python3 uji_semua.py"""

import sys
import unittest
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    suite = unittest.TestLoader().discover(str(Path(__file__).parent), pattern="uji_*.py")
    hasil = unittest.TextTestRunner(verbosity=1).run(suite)
    sys.exit(0 if hasil.wasSuccessful() else 1)
