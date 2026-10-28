// One ordinary request per retailer; no challenge solving or retries.
const probes = [
  ['S-ryhmä', 'https://www.s-kaupat.fi/tuotteet/alkoholi-ja-virvoitusjuomat/oluet?storeId=513971200', {}],
  ['K-ryhmä', 'https://www.k-ruoka.fi/kr-api/v2/product-search/?offset=0&language=fi&categoryPath=juomat%2Foluet&storeId=K144&limit=1&discountFilter=false&isTrOffer=false', {method: 'POST', headers: {accept: 'application/json'}}],
];
let failed = false;
for (const [name, url, options] of probes) {
  try {
    const response = await fetch(url, {...options, signal: AbortSignal.timeout(30000)});
    const content = await response.text();
    let valid = false;
    if (response.ok && name === 'S-ryhmä') valid = content.includes('__NEXT_DATA__');
    if (response.ok && name === 'K-ryhmä') {
      try { const data = JSON.parse(content); valid = typeof data.totalHits === 'number'; } catch (_) {}
    }
    console.log(`${name}: HTTP ${response.status}, tuotedata ${valid}`);
    if (!valid) failed = true;
  } catch (error) {
    console.log(`${name}: ${error.name}: ${error.message}`);
    failed = true;
  }
}
if (failed) process.exitCode = 1;
