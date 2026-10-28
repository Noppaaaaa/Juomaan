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

    def test_incomplete_sources_do_not_advance_date(self):
        workflow = (ROOT / '.github/workflows/paivita-valikoimat.yml').read_text()
        step = workflow.split('- name: Päivitä aineiston tila ja päiväys', 1)[1]
        code = step.split("python - <<'PY'\n", 1)[1].split('\n          PY', 1)[0]
        import textwrap
        code = textwrap.dedent(code)
        for missing, done, total, status in [(5, 248, 1056, 'osittainen'), (0, 1056, 1056, 'valmis')]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'valikoima_tiedot.json').write_text('{"aineisto_paivitetty":"2026-01-01"}')
                (root / 'alko_keruu.json').write_text(json.dumps({'puuttuvat_tuotesivut': missing}))
                (root / 'k_ryhma_keruu.json').write_text(json.dumps({'myymaloita': total, 'kerattyja_myymaloita': done}))
                env = {**os.environ, 'ALKO_STATUS': 'success', 'S_STATUS': 'success', 'K_STATUS': 'success'}
                subprocess.run(['python3', '-c', code], cwd=tmp, env=env, check=True)
                data = json.loads((root / 'valikoima_tiedot.json').read_text())
                self.assertEqual(data['aineisto_paivitys_tila'], status)
                self.assertEqual(data['aineisto_paivitetty'] == '2026-01-01', status == 'osittainen')

if __name__ == '__main__':
    unittest.main()
