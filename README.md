# Juomaan.fi

Alko-, S-ryhmä- ja K-ryhmävalikoimien hintavertailu. Sivusto on GitHub Pagesissa.

## Aineistojen automaattinen päivitys

GitHub Actions päivittää Alkon, S-ryhmän ja K-ryhmän aineistot sunnuntaisin klo 04.17 Suomen aikaa. Ajon voi käynnistää myös GitHubin **Actions → Päivitä juomavalikoimat → Run workflow** -valikosta.

Keruut suoritetaan erillisissä, järjestetyissä töissä. Jos yksi keruu epäonnistuu, seuraavat silti käynnistyvät. Alkon ja S-ryhmän aineisto korvataan vain onnistuneen keruun jälkeen. K-ryhmän tuotteet päivittyvät myös osatuloksina keruun edetessä. S- ja K-ryhmän myymäläkohtaiset välitulokset säilyvät GitHub Actionsin välimuistissa, jotta aikarajan tai pyyntötauon keskeyttämä ajo voi jatkua myöhemmin.

Onnistuneet aineistopäivitykset tallentuvat `main`-haaraan ja käynnistävät GitHub Pagesin julkaisun. Jokaisesta ajosta tallentuu GitHub Actionsin yhteenveto ja 90 päivän ajan ladattava `paivitysraportti`-artefakti. Raporttia ei tallenneta sivuston tiedostoihin eikä näytetä sivustolla.

K-ryhmän palvelin voi asettaa pitkiä pyyntötaukoja. Keruu kunnioittaa niitä; siksi kaikkien myymälöiden päivitys voi vaatia useita viikkoajoja. Ajon tuloksesta näkee, onnistuiko kukin lähde.
