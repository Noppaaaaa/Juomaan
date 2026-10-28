import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SCRIPT = ROOT / 'aineiston_keräys_S.py'
STORE_FILE = ROOT / 's_ryhma_myymalat_verkkokauppa.json'

async def main():
    stores = json.loads(STORE_FILE.read_text(encoding='utf-8'))
    stores = [s for s in stores if s.get('brand') in {'abc', 'alepa', 'herkku', 'prisma', 's-market', 'sale'}]
    todo = [s for s in stores if not (ROOT / f"s_ryhma_tuotteet_{s['id']}.json").exists()
            or (ROOT / f"s_ryhma_tuotteet_{s['id']}.json").stat().st_mtime < SCRIPT.stat().st_mtime]
    print(f"Kaupat yhteensä: {len(stores)}, valmiina: {len(stores)-len(todo)}, kerätään: {len(todo)}", flush=True)
    sem = asyncio.Semaphore(2)
    done = 0
    errors = []
    async def run(store):
        nonlocal done
        async with sem:
            for attempt in range(2):
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, str(SCRIPT), '--store-id', store['id'],
                    '--store-name', f"{store['name']}, {store['city']}",
                    cwd=ROOT, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, stderr = await proc.communicate()
                if proc.returncode == 0 or attempt:
                    break
                await asyncio.sleep(5)
            done += 1
            kohde = ROOT / f"s_ryhma_tuotteet_{store['id']}.json"
            result = f"Tallennettu {len(json.loads(kohde.read_text(encoding='utf-8')))} tuotetta" if proc.returncode == 0 and kohde.exists() else f"VIRHE ({proc.returncode})"
            print(f"[{done}/{len(todo)}] {store['name']}: {result}", flush=True)
            if proc.returncode != 0:
                detail = (stderr or stdout).decode("utf-8", errors="replace").strip()[-2000:]
                errors.append(store["id"])
                print(f"  Virheen syy: {detail or 'ei virhetietoa'}", flush=True)
    await asyncio.gather(*(run(s) for s in todo))
    print('Myymäläkeruu valmis.', flush=True)
    if errors:
        raise SystemExit(f'Myymäläkeruu epäonnistui: {len(errors)} myymälää. Aineistoa ei julkaista.')

if __name__ == '__main__':
    asyncio.run(main())
