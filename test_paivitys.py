import asyncio
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent

class UpdateTests(unittest.TestCase):
    def test_store_failure_stops_and_surfaces_diagnostics(self):
        spec = importlib.util.spec_from_file_location('s_stores', ROOT / 'aineiston_keräys_S_kaikki.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module.ROOT = root
            module.SCRIPT = root / 'collector.py'
            module.STORE_FILE = root / 'stores.json'
            module.STORE_FILE.write_text(json.dumps([{'id': str(i), 'name': 'Test', 'city': 'X', 'brand': 'sale'} for i in range(10)]))
            module.SCRIPT.write_text('from pathlib import Path\nimport sys\nwith Path("calls").open("a") as f: f.write("x")\nprint("HTTP 429",file=sys.stderr)\nsys.exit(1)\n')
            output = io.StringIO()
            with contextlib.redirect_stdout(output), self.assertRaises(SystemExit):
                asyncio.run(module.main())
            self.assertIn('HTTP 429', output.getvalue())
            self.assertLessEqual(len((root / 'calls').read_text()), 2)

if __name__ == '__main__':
    unittest.main()
