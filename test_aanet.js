const assert=require('node:assert/strict');
const {indeksi,tunniste,kuva}=require('./aanet.js');
const t=(lahde,id,nimi,url,litra=1)=>({lahde,id,nimi,kuva_url:url,tilavuus_litraa:litra,alkoholi_prosentti:5,hinta_eur:2});
const old=t('alko','old','Testijuoma','https://example.com/photo.png');
const key=tunniste(old),s=t('sryhma','s','Testijuoma','https://example.com/s.png'),k=t('kryhma','k','Testijuoma','https://example.com/k.png'),same=t('alko','new','Testijuoma','https://example.com/a.png');
assert.equal(indeksi([s,k,same]).ratkaise(key).id,'new');
assert.equal(indeksi([k,s]).ratkaise(key).id,'s');
assert.equal(indeksi([
  t('alko','same-shop','Testijuoma','https://example.com/updated.png'),
  t('sryhma','same-photo','Muu nimi',old.kuva_url),
]).ratkaise(key).id,'same-shop');
const photo=t('sryhma','image','Eri nimi','https://example.com/photo.png?size=large');
assert.equal(indeksi([photo,k]).ratkaise(key).id,'image');
assert.equal(indeksi([k]).ratkaise(key).id,'k');
assert.equal(indeksi([]).ratkaise(key),null);
assert.equal(indeksi([s]).ratkaise('Testijuoma||5||1').id,'s');
const alkoExact={...same,hinta_eur:1,alkoholi_prosentti:5};
const sDifferent={...s,hinta_eur:3,alkoholi_prosentti:6};
assert.equal(indeksi([alkoExact,sDifferent]).ratkaise('Testijuoma||5||1').id,'s');
assert.equal(indeksi([photo]).ratkaise(JSON.stringify({v:2,s:'alko',h:kuva(old.kuva_url)})).id,'image');
const legacy='Vanha nimi||5||2';
const historical={ [legacy]:[{s:'alko',i:'gone',n:'Vanha nimi',u:'https://example.com/photo.png?width=160'}] };
assert.equal(indeksi([{...same,nimi:'Uusi nimi',kuva_url:'https://example.com/photo.png?width=320'}],historical).ratkaise(legacy).id,'new');
const priorityHistory={ [legacy]:[{s:'kryhma',i:'gone',n:'Vanha nimi',u:old.kuva_url}] };
assert.equal(indeksi([
  t('alko','name','Vanha nimi','https://example.com/other.png'),
  t('sryhma','photo','Uusi nimi',old.kuva_url),
],priorityHistory).ratkaise(legacy).id,'photo');
assert.equal(kuva('https://example.com/missing-product-image.svg'),null);
console.log('Äänien tunnistus: kauppaprioriteetti, nimi, kuva ja historialliset avaimet OK');
