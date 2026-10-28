"""Kerää S-kauppojen alkoholituotteet Crawl4AI:lla ja jäsentää sivun tuotedatan."""

import argparse
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler


JUOMAT_URL = "https://www.s-kaupat.fi/tuotteet/alkoholi-ja-virvoitusjuomat"
HELSINKI_STORE_ID = "513971200"  # Prisma Kaari Kannelmäki
RYHMAT = {
    "oluet": "Oluet",
    "siiderit": "Siiderit",
    "lonkerot": "Väkevät",
    "alkoholijuomasekoitukset-ja-cocktailit": "Väkevät",
    "viinit-ja-muut-rypaletuotteet": "Viinit",
    "glogit-simat-ja-muut-kausijuomat": "Viinit",
}


def lue_alkoholi(nimi):
    match = re.search(r"(\d+(?:[,.]\d+)?)\s*(?:(?:-?\s*til\.?|vol)\s*[-–]?\s*)?%", nimi, re.I)
    return float(match.group(1).replace(",", ".")) if match else 0.0


def lue_tilavuus(nimi, perushinta, litrahinta):
    vertailutilavuus = perushinta / litrahinta if litrahinta > 0 else 0
    tilavuudet = re.findall(r"(\d+(?:[,.]\d+)?)\s*(ml|cl|l)\b", nimi, re.I)
    if tilavuudet:
        maara, yksikko = tilavuudet[-1]
        litrat = float(maara.replace(",", ".")) / {"ml": 1000, "cl": 100, "l": 1}[yksikko.lower()]
        pakkaus = re.search(r"(?:^|\s)(\d+)\s*(?:[x×]|-?\s*pack)", nimi, re.I)
        if pakkaus:
            litrat *= int(pakkaus.group(1))
        # Toimittajan nimessä voi olla tukkupakkaus, vaikka myyntiyksikkö on yksi pullo.
        if vertailutilavuus and abs(litrat - vertailutilavuus) > max(.002, litrat * .005):
            return round(vertailutilavuus, 3)
        return round(litrat, 3)
    return round(vertailutilavuus, 3)


def poimi_sivu(html, tyyppi, myymala_id, myymala_nimi):
    soup = BeautifulSoup(html, "lxml")
    next_data = soup.find("script", id="__NEXT_DATA__")
    if not next_data or not next_data.string:
        raise RuntimeError("S-kauppojen tuotedata puuttuu sivulta.")
    apollo = json.loads(next_data.string)["props"]["pageProps"]["apolloState"]
    teksti = soup.get_text(" ", strip=True)
    sivuja = re.search(r"\d+\s+tuotetta\s+Sivu\s+\d+\s*/\s*(\d+)", teksti)
    kortit = {a.get("data-product-id"): a for a in soup.select('article[data-product-id]')}
    tuotteet, puuttuvat_nimet, puuttuvat_linkit = [], 0, 0

    for avain, tuote in apollo.items():
        if not avain.startswith("Product:{") or tuote.get("storeId") != myymala_id:
            continue
        if not tuote.get("isAgeLimitedByAlcohol"):
            continue

        nimi = tuote.get("name", "").strip()
        alkoholi = lue_alkoholi(nimi)
        if not nimi:
            puuttuvat_nimet += 1
            continue

        hinta = float(tuote.get("price") or 0)
        pantti = float(tuote.get("depositPrice") or 0)
        perushinta = max(0, hinta - pantti)
        hinnoittelu = tuote.get("pricing") or {}
        litrahinta = float(tuote.get("comparisonPrice") or hinnoittelu.get("comparisonPrice") or 0)
        tilavuus = lue_tilavuus(nimi, perushinta, litrahinta)

        ean = str(tuote.get("ean") or tuote.get("id") or "")
        kortti = kortit.get(ean)
        kuva = kortti.find("img").get("src", "").split("?", 1)[0] if kortti and kortti.find("img") else ""
        if not kuva or "missing-product-image" in kuva:
            kuva = (((tuote.get("productDetails") or {}).get("productImages") or {}).get("mainImage") or {}).get("urlTemplate", "")
            kuva = kuva.replace("{MODIFIERS}", "w280h280@_q75").replace("{EXTENSION}", "webp")
        kuva = urljoin("https://www.s-kaupat.fi", kuva) if kuva else "https://www.s-kaupat.fi/icons/missing-product-image.svg"
        polku = kortti.select_one('a[href*="/tuote/"]') if kortti else None
        slug = tuote.get("slug")
        if polku and polku.get("href"):
            linkki = urljoin("https://www.s-kaupat.fi", polku.get("href").split("?", 1)[0])
        elif slug and ean:
            linkki = f"https://www.s-kaupat.fi/tuote/{slug}/{ean}"
        else:
            puuttuvat_linkit += 1
            continue

        tuotteet.append({
            "nimi": nimi,
            "hinta_eur": round(perushinta, 2),
            "tilavuus_litraa": tilavuus,
            "alkoholi_prosentti": alkoholi or None,
            "tyyppi": tyyppi,
            "linkki": linkki,
            "kuva_url": kuva,
            "myymälät_maara": 1,
            "vertailuhinta_eur_l": litrahinta,
            "myymala_id": myymala_id,
            "pantti_eur": round(pantti, 2),
            "lahde": "sryhma",
            "myymala_nimi": myymala_nimi,
            "linkki_sivulta": True,
        })

    return tuotteet, int(sivuja.group(1)) if sivuja else 1, puuttuvat_nimet, puuttuvat_linkit


async def main():
    parser = argparse.ArgumentParser(description="Kerää S-kauppojen alkoholituotteet.")
    parser.add_argument("--store-id", default=HELSINKI_STORE_ID, help="S-kauppojen myymälätunnus (oletus: Helsinki, Prisma Kaari)")
    parser.add_argument("--store-name", default="Prisma Kaari Kannelmäki, Helsinki", help="Myymälän nimi hintatiedon yhteydessä")
    args = parser.parse_args()

    async with AsyncWebCrawler() as crawler:
        kaikki, ohitetut = [], 0

        async def hae_sivu(url):
            for yritys in range(3):
                result = await crawler.arun(url=url, js=True, bypass_cache=True, timeout=30000)
                if getattr(result, "status_code", None) == 429:
                    raise RuntimeError("HTTP 429: S-kaupat rajoittaa pyyntöjä. Keruu pysäytetty.")
                next_data = BeautifulSoup(result.html or "", "lxml").find("script", id="__NEXT_DATA__")
                if result.success and next_data and next_data.string:
                    return result.html
                await asyncio.sleep(1 + yritys)
            raise RuntimeError(f"Sivun tuotedata ei latautunut kolmen yrityksen jälkeen: {url}")

        for slug, tyyppi in RYHMAT.items():
            aloitus = len(kaikki)
            url = f"{JUOMAT_URL}/{slug}?storeId={args.store_id}"
            tuotteet, sivuja, puuttuvat, ilman_linkkia = poimi_sivu(await hae_sivu(url), tyyppi, args.store_id, args.store_name)
            kaikki.extend(tuotteet)
            ohitetut += puuttuvat
            linkit_puuttuu = ilman_linkkia
            for page in range(2, sivuja + 1):
                page_url = f"{JUOMAT_URL}/{slug}?page={page}&storeId={args.store_id}"
                tuotteet, _, puuttuvat, ilman_linkkia = poimi_sivu(await hae_sivu(page_url), tyyppi, args.store_id, args.store_name)
                kaikki.extend(tuotteet)
                ohitetut += puuttuvat
                linkit_puuttuu += ilman_linkkia
            print(f"{slug}: {len(kaikki) - aloitus} tuotetta kerätty")

    uniikit = {tuote["linkki"]: tuote for tuote in kaikki}

    kohde = Path(__file__).with_name(f"s_ryhma_tuotteet_{args.store_id}.json")
    valiaikainen = kohde.with_suffix(".json.tmp")
    valiaikainen.write_text(json.dumps(list(uniikit.values()), ensure_ascii=False, indent=2), encoding="utf-8")
    valiaikainen.replace(kohde)
    print(f"Tallennettu {len(uniikit)} tuotetta: {kohde}; ilman nimeä ohitettu {ohitetut}, ilman tuotelinkkiä ohitettu {linkit_puuttuu}")


if __name__ == "__main__":
    asyncio.run(main())
