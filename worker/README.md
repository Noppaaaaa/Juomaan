# juomaan.fi äänestys-backend (Cloudflare Worker + D1)

Tämä on pieni API, joka tallentaa käyttäjien äänet juomien "dokattavuudesta"
(maku/alkoholi-suhde). Staattinen sivu (GitHub Pages) kutsuu tätä `fetch`illä.

- Jokaisella käyttäjällä (selaimen `clientId`) on **3 ääntä**.
- Yhden juoman voi äänestää **kerran**.
- Frontend osaa lajitella äänimäärän mukaan.

## Käyttöönotto (kertaalleen)

Tarvitset ilmaisen Cloudflare-tilin.

```bash
npm install -g wrangler
wrangler login

# 1) Luo D1-tietokanta ja KOPIOI tulostuva database_id wrangler.tomliin
wrangler d1 create juomaan_aanet

# 2) Luo taulu (sekä paikallisesti että pilveen)
wrangler d1 execute juomaan_aanet --remote --file=./schema.sql

# 3) Julkaise worker
wrangler deploy
```

`wrangler deploy` tulostaa workerin osoitteen, esim.
`https://juomaan-aanet.<tili>.workers.dev`.

## Kytkeminen sivuun

Avaa `index.html` ja etsi rivi:

```js
const AANI_API = ""; // <-- liitä tähän workerin osoite
```

Liitä workerin osoite, esim.:

```js
const AANI_API = "https://juomaan-aanet.<tili>.workers.dev";
```

Jos jätät sen tyhjäksi, sivu olettaa että API on samalla domainilla
osoitteessa `/api/votes` (toimii, jos otat käyttöön `wrangler.toml`:n
`[[routes]]`-osion ja reitität `juomaan.fi/api/*` workeriin).

Jos API:a ei ole määritetty tai se ei vastaa, sivu toimii normaalisti –
äänestysnapit ovat vain pois käytöstä.

## Testaus paikallisesti

```bash
wrangler dev          # ajaa workerin paikallisesti (oletus :8787)
# GET  http://localhost:8787/api/votes
# POST http://localhost:8787/api/votes  body: {"clientId":"test","key":"Olut||4.7||2.99"}
```
