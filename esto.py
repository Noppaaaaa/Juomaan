"""Keskeytä kaupan rajoittaessa ja kunnioita Retry-After-aikaa."""
import fcntl
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MARKER = ROOT / '.juomaan-odota-saakka.json'

class Rajoitus(RuntimeError):
    pass


def rajoita(status, retry_after=None, description=None):
    if status not in (403, 429):
        return
    now = datetime.now(timezone.utc)
    until = now + timedelta(minutes=30)
    if retry_after:
        try:
            value = str(retry_after).strip()
            requested = now + timedelta(seconds=max(0, int(value))) if value.isdigit() else parsedate_to_datetime(value).astimezone(timezone.utc)
            until = max(until, requested)
        except (ValueError, TypeError, OverflowError, AttributeError):
            pass
    lock = ROOT / '.juomaan-odotus.lock'
    with lock.open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        if MARKER.exists():
            try:
                previous = datetime.fromisoformat(json.loads(MARKER.read_text())['odota_saakka'])
                until = max(until, previous)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                pass
        with tempfile.NamedTemporaryFile('w', dir=ROOT, delete=False) as out:
            json.dump({'odota_saakka': until.isoformat(), 'status': status}, out)
            name = out.name
        os.replace(name, MARKER)
    reason = description or f'HTTP {status}: kauppa rajoittaa pyyntöjä'
    raise Rajoitus(f'{reason}; jatketaan aikaisintaan {until.isoformat()}.')


def tarkista_sivu(status, body='', headers=None):
    headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    rajoita(status, headers.get('retry-after'))
    text = (body or '')[:20000].lower()
    challenge = headers.get('cf-mitigated', '').lower() == 'challenge' or 'vercel security checkpoint' in text or '<title>just a moment' in text or text.strip() == 'just a moment...'
    if challenge:
        rajoita(403, headers.get('retry-after'), f'HTTP {status}: kaupan suojaustarkistus')
