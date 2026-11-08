const vainViinat = document.getElementById('hinnasto').hasAttribute('data-viinat');
const haku = document.getElementById('haku');
const jarjestys = document.getElementById('jarjestys');
const tila = document.getElementById('tila');
const taulukko = document.getElementById('hinnasto');
const rivit = document.getElementById('rivit');
const lisaa = document.getElementById('lisaa');
const raha = new Intl.NumberFormat('fi-FI', { style: 'currency', currency: 'EUR' });
const koko = new Intl.NumberFormat('fi-FI', { maximumFractionDigits: 3 });
const aakkoset = new Intl.Collator('fi');
const normalisoi = arvo => arvo.toLocaleLowerCase('fi').normalize('NFD').replace(/\p{M}/gu, '');
const sivukoko = 30;
let tuotteet = [], osumat = [], naytetty = 0;

function naytaLisaa() {
    for (const tuote of osumat.slice(naytetty, naytetty + sivukoko)) {
        const rivi = rivit.insertRow();
        const linkki = document.createElement('a');
        linkki.href = tuote.linkki;
        linkki.textContent = tuote.nimi;
        rivi.insertCell().append(linkki);
        rivi.insertCell().textContent = koko.format(tuote.tilavuus_litraa) + ' l';
        if (vainViinat) rivi.insertCell().textContent = koko.format(tuote.vahvuus) + ' %';
        rivi.insertCell().textContent = raha.format(tuote.hinta);
        if (vainViinat) rivi.insertCell().textContent = raha.format(tuote.annoshinta);
        naytetty++;
    }
    taulukko.hidden = !naytetty;
    tila.textContent = osumat.length ? `Näytetään ${naytetty} / ${osumat.length} tuotetta.` : 'Hakua vastaavia tuotteita ei löytynyt.';
    if (lisaa === document.activeElement && naytetty >= osumat.length) rivit.lastElementChild?.querySelector('a').focus();
    lisaa.hidden = naytetty >= osumat.length;
}

function suodata() {
    const sanat = normalisoi(haku.value.trim()).split(/\s+/);
    osumat = tuotteet.filter(tuote => sanat.every(sana => tuote.hakuteksti.includes(sana)));
    if (jarjestys.value === 'annoshinta') osumat.sort((a, b) => a.annoshinta - b.annoshinta);
    if (jarjestys.value === 'hinta') osumat.sort((a, b) => a.hinta - b.hinta);
    rivit.replaceChildren();
    naytetty = 0;
    naytaLisaa();
}

async function lueJson(polku) {
    const vastaus = await fetch(polku);
    if (!vastaus.ok) throw new Error('HTTP ' + vastaus.status);
    return vastaus.json();
}

tila.textContent = 'Ladataan Alkon hintoja…';
const hinnastoPolku = vainViinat ? '/halvin-viina/hinnat.json' : '/alkon-hinnasto/hinnat.json';
lueJson(hinnastoPolku).then(({ tuotteet: aineisto, keratty }) => {
    tuotteet = aineisto.filter(tuote => tuote.nimi?.trim()
        && Number.isFinite(tuote.hinta_eur) && tuote.hinta_eur > 0
        && Number.isFinite(tuote.tilavuus_litraa) && tuote.tilavuus_litraa > 0
        && (!vainViinat || (tuote.tyyppi?.split(',').some(osa => osa.trim() === 'vodkat ja viinat')
            && Number.isFinite(tuote.alkoholi_prosentti) && tuote.alkoholi_prosentti > 0))
        && /^https:\/\/(?:www\.)?alko\.fi\//i.test(tuote.linkki))
        .map(tuote => {
            const hinta = Math.round((tuote.hinta_eur + (Number(tuote.pantti_eur) || 0)) * 100) / 100;
            return {
                nimi: tuote.nimi.trim(),
                linkki: tuote.linkki,
                tilavuus_litraa: tuote.tilavuus_litraa,
                vahvuus: tuote.alkoholi_prosentti,
                hinta,
                annoshinta: hinta / (tuote.tilavuus_litraa * tuote.alkoholi_prosentti / 1.5),
                hakuteksti: normalisoi(tuote.nimi + ' ' + (tuote.tyyppi || ''))
            };
        }).sort((a, b) => aakkoset.compare(a.nimi, b.nimi));
    haku.disabled = jarjestys.disabled = false;
    const otos = document.getElementById('otoksen-paivays');
    if (otos) otos.hidden = true;
    suodata();
    const paivays = new Date(keratty);
    if (Number.isFinite(paivays.getTime())) {
        const paiva = new Intl.DateTimeFormat('fi-FI', { timeZone: 'Europe/Helsinki' }).format(paivays);
        document.getElementById('paivitys').textContent = `Aineisto kerätty ${paiva}.`;
    }
}).catch(() => {
    tila.textContent = 'Hintoja ei voitu ladata. Päivitä sivu ja yritä uudelleen.';
});
haku.addEventListener('input', suodata);
jarjestys.addEventListener('change', suodata);
lisaa.addEventListener('click', naytaLisaa);
