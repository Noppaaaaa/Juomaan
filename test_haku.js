// Run with: node test_haku.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync(`${__dirname}/index.html`, 'utf8');
const start = html.indexOf("let hakuTermi='");
const end = html.indexOf('function getFilteredData()', start);
const context = vm.createContext({});
vm.runInContext('let tuoteData=[],kaikkiTuotteet=[];\n' + html.slice(start, end), context);
function search(query, products, catalog=products) {
    context.query = query;
    context.catalog = catalog;
    context.products = products;
    return vm.runInContext(`
        tuoteData=products;
        kaikkiTuotteet=catalog;
        hakuSanasto=null;
        hakuTokens=normalisoiHaku(query).split(' ').filter(Boolean);
        laskeHakuOsumat();
        tuoteData.filter(t=>t._osuma);
    `, context);
}
const spirits = {nimi:'Koskenkorva Viina', tyyppi:'Väkevät'};
const wine = {nimi:'Esimerkin punaviini', tyyppi:'Viinit'};
const products = [spirits, wine];
assert.deepEqual(Array.from(search('viina', products)), [spirits]);
assert.deepEqual(Array.from(search('viini', products)), [wine]);
assert.deepEqual(Array.from(search('viinat', [{nimi:'Viinat', tyyppi:'Väkevät'}, wine])).map(t=>t.nimi), ['Viinat']);
assert.deepEqual(Array.from(search('koskenkora', products)), [spirits]);
assert.deepEqual(Array.from(search('KOSKENKORVA VIINA', products)), [spirits]);
assert.deepEqual(Array.from(search('', products)), products);
assert.equal(search('xyzxyzxyzxyz', products).length, 0);
assert.deepEqual(Array.from(search('vakevat', products)), [spirits]);

// A recognized word remains literal even when no local product matches it.
assert.equal(search('viina', [wine], products).length, 0);
assert.equal(search('viini', [spirits], products).length, 0);
// Correct each token separately: a typo must not loosen the other query words.
const koskenkorvaWine = {nimi:'Koskenkorva Viini', tyyppi:'Viinit'};
assert.deepEqual(Array.from(search('koskenkora viina', [...products, koskenkorvaWine])), [spirits]);
for (const query of ['koskenkovra', 'koskenkorav', 'koskenkorvaa']) {
    assert.deepEqual(Array.from(search(query, products)), [spirits], query);
}
function correct(token, words) {
    context.token=token;
    context.words=words;
    return vm.runInContext('korjaaHakuToken(token,words)', context);
}
assert.equal(correct('gni', ['gin']), 'gin');
assert.equal(correct('rom', ['rum']), 'rom');
assert.equal(correct('viino', ['viina','viini']), 'viino'); // Ambiguous.
assert.equal(correct('viino', ['viini','viina']), 'viino');
assert.equal(correct('viina', ['viinit']), 'viina'); // Too far to guess.
assert.equal(correct('1234', ['1235']), '1234');
assert.equal(correct('kosken', ['koskenkorva']), 'kosken'); // Partial query.
assert.equal(correct('vodak', ['vodka','vodkat']), 'vodka'); // Nearest only.
assert.equal(correct('vodak', ['vodkat','vodka']), 'vodka');
assert.equal(correct('chardnonnay', ['chardonnay']), 'chardonnay'); // Two edits.

const catalog = ['alko_tuotteet.json', 's_ryhma_tuotteet.json'].flatMap(file =>
    JSON.parse(fs.readFileSync(`${__dirname}/${file}`, 'utf8')));
const categoryStart = html.indexOf('function luokitteleKategoria(');
const categoryEnd = html.indexOf('const KATEGORIA_NIMET', categoryStart);
vm.runInContext(html.slice(categoryStart, categoryEnd), context);
const classify = vm.runInContext('luokitteleKategoria', context);
const normalizedCatalog = catalog.map(t => ({...t, tyyppi:classify(t)}));
const matches = search('viina', normalizedCatalog);
assert.ok(matches.length > 0);
assert.ok(matches.every(t => /viina/.test(vm.runInContext('normalisoiHaku', context)(t.nimi+' '+t.tyyppi))));
assert.ok(matches.some(t => /Jaloviina/.test(t.nimi)));
// Jaloviina Glögi is classified as wine, but its name is a literal match.
assert.ok(matches.every(t => /viina/i.test(t.nimi)));
assert.deepEqual(Array.from(search('viina', [{nimi:'Esimerkin Viina', tyyppi:'Väkevät'}])).map(t=>t.nimi), ['Esimerkin Viina']);
for(const [query, name] of [['koskenkovra','Koskenkorva'],['jalovinia','Jaloviina'],['chardonay','Chardonnay'],['punavini','punaviini']]) {
    const results=search(query, normalizedCatalog);
    assert.ok(results.length>0, query);
    assert.ok(results.every(t => (t.nimi+' '+t.tyyppi).toLowerCase().includes(name.toLowerCase())), query);
}
assert.equal(search('viina', normalizedCatalog.filter(t => t.tyyppi==='Viinit' && !/viina/i.test(t.nimi)), normalizedCatalog).length, 0);
console.log(`Search checks passed (${matches.length} literal viina matches in catalog).`);
