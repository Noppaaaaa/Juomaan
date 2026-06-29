# Alkon tuotteiden keräys – suora JSON-poiminta (ei tekoälyä)
# Vaihe 1: tuotteet listaussivuilta (nopea, perustiedot).
# Vaihe 2: jokaisen tuotteen oma sivu -> tarkka pantti (deposit-kenttä).
# Varautuminen Alkon botin/WAF:n estoon: eston tunnistus, uudelleenyritys + backoff,
# adaptiivinen hidastus, user-agent-kierto ja jatkaminen keskeytyksen jälkeen.

import sys
import os
import subprocess

if __name__ == "__main__":
    if not os.environ.get("ALKO_SCRAPER_SUBPROCESS"):
        env = os.environ.copy()
        env["ALKO_SCRAPER_SUBPROCESS"] = "1"
        cmd = f'start cmd /k "python {sys.argv[0]}"'
        subprocess.Popen(cmd, shell=True, env=env)
        sys.exit(0)

    import asyncio
    import json
    import time
    import re
    import random
    from crawl4ai import AsyncWebCrawler

    # ---- Asetukset ----
    BASE_URL = "https://www.alko.fi/tuotteet/olut/kaikki-oluet"  # sivutus kattaa koko katalogin
    CONCURRENCY = 5          # montako sivua haetaan yhtä aikaa
    BATCH = 12               # montako sivua/tuotetta per kierros
    STOP_AFTER_EMPTIES = 12  # peräkkäiset AIDOSTI tyhjät sivut -> katalogi loppui
    PAGE_CAP = 5000          # turvaraja

    # Estonsiedon asetukset
    MAX_RETRIES = 5          # yritykset per sivu ennen luovuttamista
    BACKOFF_BASE = 2.0       # backoff-kerroin (2,4,8,16 s ...)
    BACKOFF_MAX = 45.0       # yhden odotuksen yläraja
    JITTER = (0.3, 1.2)      # satunnaisviive ennen jokaista hakua (s)
    BLOCK_COOLDOWN = 60.0    # jäähdyttely kun koko erä estyy (s)
    DELAY_MIN = 0.0          # adaptiivisen lisäviiveen rajat (s)
    DELAY_MAX = 8.0

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    ]

    BLOCK_MARKERS = [
        "Azure WAF", "JS Challenge", "Just a moment", "Verifying you are human",
        "Attention Required", "Checking your browser", "captcha", "Access Denied",
        "Request blocked", "cf-browser-verification", "_Incapsula_",
    ]

    # ---- Näytön ohjaus ----
    display_lock = asyncio.Lock()
    status_message = ""
    aloitus_aika = None
    kaikki_keratyt_tuotteet = []
    spinner_index = 0
    spinner_chars = ['|', '/', '-', '\\']
    estoja_yhteensa = 0
    current_delay = DELAY_MIN

    # ---- JSON-poiminta sivun rakenteesta ----
    # Tuotetiedot ovat sivun React-datassa muodossa  \"avain\":arvo
    Q = r'\\"'

    def _s(key):
        return re.compile(Q + re.escape(key) + Q + r':' + Q + r'(.*?)' + Q)

    def _n(key):
        return re.compile(Q + re.escape(key) + Q + r':(-?\d+(?:\.\d+)?)')

    P_ID    = _s('productId')
    P_NAME  = _s('name')
    P_CAT   = _s('category')
    P_IMG   = _s('imageUrlSmall')
    P_VAL   = _n('valueInCents')
    P_SIZE  = _n('containerSizeLitres')
    P_ALC   = _n('alcoholPercentage')
    P_STORE = _n('storeAvailability')
    P_HREF  = re.compile(r'href="(/fi/tuotteet/(\d+)/[^"]+)"')
    P_DEPOSIT = _n('deposit')          # tarkka pantti tuotesivulta
    P_PID_IN_URL = re.compile(r'/tuotteet/(\d+)')

    def _dec(x):
        try:
            return x.encode('utf-8').decode('unicode_escape').encode('latin-1').decode('utf-8')
        except Exception:
            return x

    def parse_products(html):
        if not html:
            return []
        linkit = {}
        for m in P_HREF.finditer(html):
            linkit.setdefault(m.group(2), "https://www.alko.fi" + m.group(1))

        out = []
        idxs = [m.start() for m in P_ID.finditer(html)]
        if not idxs:
            return out
        idxs.append(len(html))
        for a, b in zip(idxs, idxs[1:]):
            chunk = html[a:b]
            pid_m = P_ID.search(chunk)
            name_m = P_NAME.search(chunk)
            if not pid_m or not name_m:
                continue
            pid = pid_m.group(1)
            nimi = _dec(name_m.group(1))

            def num(p, d=0.0):
                m = p.search(chunk)
                return float(m.group(1)) if m else d

            def txt(p, d=""):
                m = p.search(chunk)
                return _dec(m.group(1)) if m else d

            linkki = linkit.get(pid, f"https://www.alko.fi/fi/tuotteet/{pid}")
            out.append({
                "nimi": nimi,
                "hinta_eur": round(num(P_VAL) / 100.0, 2),
                "tilavuus_litraa": num(P_SIZE),
                "alkoholi_prosentti": num(P_ALC),
                "tyyppi": txt(P_CAT),
                "linkki": linkki,
                "kuva_url": txt(P_IMG),
                "myymälät_maara": int(num(P_STORE)),
                "pantti_eur": arvioi_pantti(nimi, num(P_SIZE), txt(P_CAT)),
            })
        return out

    def poimi_pantti(html):
        """Tuotesivulla on täsmälleen yksi deposit-kenttä (päätuote).
        Jos kenttää ei ole -> tuote ei ole pantillinen -> 0.0 €."""
        m = P_DEPOSIT.search(html)
        return round(float(m.group(1)), 2) if m else 0.0

    PANTILLISET_TYYPIT = {
        "Oluet", "Siiderit", "Juomasekoitukset",
        "Alkoholittomat oluet", "Alkoholittomat siiderit",
        "Panimotuotteet",
    }

    def arvioi_pantti(nimi, tilavuus_litraa, tyyppi):
        """Arvioi pantin tuotetyypin, tilavuuden ja pakkauskoon perusteella."""
        if tyyppi not in PANTILLISET_TYYPIT:
            return 0.0
        n = nimi.lower()
        if any(x in n for x in ("kartonkitölkki", "kartonkitolkki", "hanapakkaus", "viinipussi")):
            return 0.0
        if tilavuus_litraa <= 0:
            return 0.0
        mp = re.search(r'(\d+)\s*-?\s*pack', n)
        lkm = int(mp.group(1)) if mp else 1
        yks = tilavuus_litraa / lkm
        pantti = 0.10 if yks <= 0.35 else 0.20 if yks <= 0.5 else 0.40
        return round(pantti * lkm, 2)

    # ---- Vastauksen luokittelu ----
    def luokittele_lista(html, status_code):
        if status_code in (403, 429, 503, 502, 520, 521, 522):
            return "block"
        if not html or len(html) < 5000:
            return "block"
        if any(m.lower() in html.lower() for m in BLOCK_MARKERS):
            return "block"
        if "productId" in html:
            return "ok"
        return "empty"

    def luokittele_detail(pid):
        def f(html, status_code):
            if status_code in (403, 429, 503, 502, 520, 521, 522):
                return "block"
            if not html or len(html) < 5000:
                return "block"
            if any(m.lower() in html.lower() for m in BLOCK_MARKERS):
                return "block"
            # päätuotteen on renderöidyttävä, muuten yritetään uudelleen
            if not pid or f'\\"productId\\":\\"{pid}\\"' in html:
                return "ok"
            return "block"
        return f

    # ---- Yleinen haku estonsiedolla ----
    async def hae_html(crawler, sem, url, tarkista, kuvaus=""):
        global estoja_yhteensa, current_delay, status_message
        for yritys in range(1, MAX_RETRIES + 1):
            async with sem:
                await asyncio.sleep(random.uniform(*JITTER) + current_delay)
                try:
                    result = await crawler.arun(
                        url=url,
                        user_agent=random.choice(USER_AGENTS),
                        js=True,
                        bypass_cache=True,
                        timeout=60000,
                    )
                    html = result.html or ""
                    status_code = getattr(result, "status_code", None) or 200
                except Exception:
                    html, status_code = "", 0

            tila = tarkista(html, status_code)
            if tila == "ok":
                current_delay = max(DELAY_MIN, current_delay - 0.5)
                return "ok", html
            if tila == "empty":
                return "empty", html

            estoja_yhteensa += 1
            current_delay = min(DELAY_MAX, current_delay + 1.0)
            if yritys < MAX_RETRIES:
                viive = min(BACKOFF_MAX, BACKOFF_BASE ** yritys) + random.uniform(0, 1.5)
                status_message = f"{kuvaus}: esto (yritys {yritys}/{MAX_RETRIES}) – odotetaan {viive:.0f}s"
                await paivita_naytto()
                await asyncio.sleep(viive)

        return "block", ""

    # ---- Näyttö ----
    async def paivita_naytto():
        global spinner_index
        async with display_lock:
            if aloitus_aika is None:
                return
            spinner_char = spinner_chars[spinner_index % len(spinner_chars)]
            kulunut = time.time() - aloitus_aika
            maara = len(kaikki_keratyt_tuotteet)
            rivi = (f"{spinner_char} [Aikaa {kulunut/60:.1f} min | {maara} tuotetta | "
                    f"estoja {estoja_yhteensa}] {status_message}")
            sys.stdout.write("\r" + rivi + " " * 20)
            sys.stdout.flush()

    async def spinner_kello_looppi():
        global spinner_index
        while True:
            await paivita_naytto()
            spinner_index += 1
            await asyncio.sleep(0.2)

    def lisaa_tuotteet(tuotteet, nahdyt_idt):
        for t in tuotteet:
            avain = t["linkki"] or t["nimi"]
            if avain in nahdyt_idt:
                continue
            nahdyt_idt.add(avain)
            kaikki_keratyt_tuotteet.append(t)

    def tallenna(polku):
        with open(polku, "w", encoding="utf-8") as f:
            json.dump(kaikki_keratyt_tuotteet, f, ensure_ascii=False, indent=4)

    # =========================================================================
    async def main():
        global aloitus_aika, kaikki_keratyt_tuotteet, status_message

        dir_path = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(dir_path, "alko_tuotteet.json")
        temp_file_path = os.path.join(dir_path, "kesken.json")

        kaikki_keratyt_tuotteet = []
        nahdyt_idt = set()

        # Jatkaminen: lataa keskeneräinen tulos jos edellinen ajo katkesi
        if os.path.exists(temp_file_path):
            try:
                with open(temp_file_path, "r", encoding="utf-8") as f:
                    vanhat = json.load(f)
                if isinstance(vanhat, list) and vanhat:
                    for t in vanhat:
                        avain = t.get("linkki") or t.get("nimi")
                        if avain and avain not in nahdyt_idt:
                            nahdyt_idt.add(avain)
                            kaikki_keratyt_tuotteet.append(t)
                    print(f"Jatketaan edellisestä ajosta: {len(kaikki_keratyt_tuotteet)} tuotetta valmiina.")
            except Exception:
                pass

        aloitus_aika = time.time()
        asyncio.create_task(spinner_kello_looppi())

        async with AsyncWebCrawler() as crawler:
            sem = asyncio.Semaphore(CONCURRENCY)

            # ---------- VAIHE 1: listaussivut ----------
            empties_in_row = 0
            sivu = 1
            while sivu <= PAGE_CAP and empties_in_row < STOP_AFTER_EMPTIES:
                sivut = list(range(sivu, sivu + BATCH))
                status_message = f"VAIHE 1 – haetaan sivut {sivut[0]}–{sivut[-1]}..."
                await paivita_naytto()

                tulokset = await asyncio.gather(*(
                    hae_html(crawler, sem, f"{BASE_URL}?page={p}", luokittele_lista, f"Sivu {p}")
                    for p in sivut
                ))
                for tila, html in tulokset:
                    if tila == "ok":
                        lisaa_tuotteet(parse_products(html), nahdyt_idt)
                        empties_in_row = 0
                    elif tila == "empty":
                        empties_in_row += 1
                    # block: ei lasketa lopuksi

                tallenna(temp_file_path)
                status_message = f"VAIHE 1 – sivuun {sivut[-1]} asti, {len(kaikki_keratyt_tuotteet)} tuotetta"
                await paivita_naytto()
                sivu += BATCH

            # ---------- VAIHE 2: pantti tuotesivuilta ----------
            async def hae_pantti(t):
                pid_m = P_PID_IN_URL.search(t.get("linkki", ""))
                pid = pid_m.group(1) if pid_m else ""
                tila, html = await hae_html(crawler, sem, t["linkki"],
                                            luokittele_detail(pid), f"Tuote {pid}")
                if tila == "ok":
                    t["pantti_eur"] = poimi_pantti(html)
                    return "ok"
                return "block"   # jätetään pantti_eur Noneksi -> loppukierros/uusinta

            kesken = [t for t in kaikki_keratyt_tuotteet if t.get("pantti_eur") is None]
            yhteensa = len(kesken)
            tehty = 0
            i = 0
            while i < len(kesken):
                era = kesken[i:i + BATCH]
                status_message = f"VAIHE 2 – pantit {tehty}/{yhteensa}"
                await paivita_naytto()

                tulokset = await asyncio.gather(*(hae_pantti(t) for t in era))
                tehty += len(era)
                era_estoja = sum(1 for x in tulokset if x == "block")

                tallenna(temp_file_path)
                if era_estoja >= max(1, BATCH // 2):
                    status_message = f"VAIHE 2 – paljon estoja ({era_estoja}/{len(era)}), jäähdytellään {BLOCK_COOLDOWN:.0f}s"
                    await paivita_naytto()
                    await asyncio.sleep(BLOCK_COOLDOWN)
                i += BATCH

            # ---------- Loppukierros: pantti yhä hakematta ----------
            yha = [t for t in kaikki_keratyt_tuotteet if t.get("pantti_eur") is None]
            if yha:
                status_message = f"Uusintayritys {len(yha)} tuotteen pantille..."
                await paivita_naytto()
                await asyncio.sleep(BLOCK_COOLDOWN)
                for t in yha:
                    await hae_pantti(t)
                    tallenna(temp_file_path)

            # mahdolliset epäonnistuneet -> 0.0 (ei jätetä Nonea ulos)
            for t in kaikki_keratyt_tuotteet:
                if t.get("pantti_eur") is None:
                    t["pantti_eur"] = 0.0

        tallenna(file_path)
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

        kokonais_aika = (time.time() - aloitus_aika) / 60
        status_message = "Valmis!"
        await paivita_naytto()
        print(f"\nKokonaisaika: {kokonais_aika:.1f} min, "
              f"tuotteita yhteensä: {len(kaikki_keratyt_tuotteet)}, "
              f"estoja matkalla: {estoja_yhteensa}")

    asyncio.run(main())
