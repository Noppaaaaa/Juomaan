# Juomaan.fi

Alko-, S-ryhmä- ja K-ryhmävalikoimien hintavertailu. Sivusto on GitHub Pagesissa.

## Aineistojen automaattinen päivitys

GitHub Actions päivittää Alkon, S-ryhmän ja K-ryhmän aineistot sunnuntaisin klo 04.17 Suomen aikaa. Ajon voi käynnistää myös GitHubin **Actions → Päivitä juomavalikoimat → Run workflow** -valikosta.

Keruut suoritetaan erillisissä, järjestetyissä töissä. Jos yksi keruu epäonnistuu, seuraavat silti käynnistyvät. Alkon ja S-ryhmän aineisto korvataan vain onnistuneen keruun jälkeen. K-ryhmän tuotteet päivittyvät myös osatuloksina keruun edetessä. S- ja K-ryhmän myymäläkohtaiset välitulokset säilyvät GitHub Actionsin välimuistissa, jotta aikarajan tai pyyntötauon keskeyttämä ajo voi jatkua myöhemmin.

Onnistuneet aineistopäivitykset tallentuvat `main`-haaraan ja käynnistävät GitHub Pagesin julkaisun. Jokaisesta ajosta tallentuu GitHub Actionsin yhteenveto ja 90 päivän ajan ladattava `paivitysraportti`-artefakti. Raporttia ei tallenneta sivuston tiedostoihin eikä näytetä sivustolla.

K-ryhmän palvelin voi asettaa pitkiä pyyntötaukoja. Keruu kunnioittaa niitä; siksi kaikkien myymälöiden päivitys voi vaatia useita viikkoajoja. Ajon tuloksesta näkee, onnistuiko kukin lähde.

## Äänien säilyminen aineistopäivityksessä

Ennen uuden valikoiman julkaisua `paivita_aanet_historia.py` hakee aktiiviset ääniavaimet ja liittää vanhat avaimet edellisten valikoimien tuotekuvauksiin Git-historiasta. Sivusto siirtää äänten näytön saman kaupan tuotteeseen ensin ja etsii sen jälkeen S-, Alko- ja K-ryhmän järjestyksessä täsmäävän nimen tai saman kuvan URL-tunnisteen. Jos mikään tuote ei täsmää, ääni jätetään siirtämättä. Äänten varsinaista tietokantaa ei muuteta.
