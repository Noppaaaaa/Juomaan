# Juomaan.fi

Alko-, S-ryhmä- ja K-ryhmävalikoimien hintavertailu. Sivusto on GitHub Pagesissa.

## Aineiston päivitys

Aineisto päivitetään Macilla yksityisen [Juomaan-päivitysrepon](https://github.com/Noppaaaaa/juomaan-paivitys-private/actions) **Päivitä Juomaan Macilla** -workflow'lla. Valitse Actions-sivulla workflow, paina **Run workflow** ja käynnistä ajo. Macin pitää olla päällä, hereillä, kirjautuneena ja verkossa.

Workflow kerää Alkon, S-ryhmän ja K-ryhmän aineiston järjestyksessä, säilyttää valmiit välimuistit uusintayrityksiä varten ja näyttää vaiheet sekä lokit GitHubissa. Sivuston päivityspäivä muuttuu vasta, kun keruu, kattavuustarkistukset ja julkaisu onnistuvat.

## Äänien säilyminen aineistopäivityksessä

Ennen uuden valikoiman julkaisua `paivita_aanet_historia.py` hakee aktiiviset ääniavaimet ja liittää vanhat avaimet edellisten valikoimien tuotekuvauksiin Git-historiasta. Sivusto siirtää äänten näytön saman kaupan tuotteeseen ensin ja etsii sen jälkeen S-, Alko- ja K-ryhmän järjestyksessä täsmäävän nimen tai saman kuvan URL-tunnisteen. Jos mikään tuote ei täsmää, ääni jätetään siirtämättä. Äänten varsinaista tietokantaa ei muuteta.
