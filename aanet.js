/* Äänten pysyvät tunnisteet ja vanhojen tunnisteiden yhdistäminen. */
(function(root){
  const nimi=s=>String(s||'').normalize('NFKC').trim().replace(/\s+/g,' ').toLocaleLowerCase('fi-FI');
  const numero=n=>n==null||!Number.isFinite(Number(n))?null:Number(n);
  function kuva(s){
    if(!s||/missing-product-image/i.test(s))return null;
    let url;try{url=new URL(s);url.search='';url.hash=''}catch{return null}
    const text=url.href;let a=2166136261,b=2246822519;
    for(let i=0;i<text.length;i++){a=Math.imul(a^text.charCodeAt(i),16777619);b=Math.imul(b^text.charCodeAt(i),3266489917)}
    return (a>>>0).toString(16).padStart(8,'0')+(b>>>0).toString(16).padStart(8,'0');
  }
  const tunniste=t=>JSON.stringify({v:2,s:t.lahde,i:String(t.id),n:t.nimi,l:numero(t.tilavuus_litraa),a:numero(t.alkoholi_prosentti),h:kuva(t.kuva_url)});
  const order={sryhma:0,alko:1,kryhma:2};
  function indeksi(tuotteet,historia={}){
    const byId=new Map(),byName=new Map(),byImage=new Map();
    for(const t of tuotteet){const id=t.lahde+'|'+String(t.id);byId.set(id,t);const n=nimi(t.nimi);if(!byName.has(n))byName.set(n,[]);byName.get(n).push(t);const h=kuva(t.kuva_url);if(h){if(!byImage.has(h))byImage.set(h,[]);byImage.get(h).push(t)}}
    function choice(matches,d,price){
      if(!matches.length)return null;
      return matches.slice().sort((a,b)=>{
        const score=t=>(d.h&&kuva(t.kuva_url)===d.h?4:0)+(nimi(t.nimi)===nimi(d.n)?2:0)+(d.l!=null&&numero(t.tilavuus_litraa)===numero(d.l)?1:0);
        const diff=score(b)-score(a);if(diff)return diff;
        if(price!=null){const delta=Math.abs(Number(a.hinta_eur)-price)-Math.abs(Number(b.hinta_eur)-price);if(delta)return delta}
        return String(a.id).localeCompare(String(b.id));
      })[0];
    }
    function descriptor(d){
      d={...d,h:d.h||kuva(d.u)};
      if(!d||!d.s||(!d.n&&!d.h))return null;
      const exact=d.i&&byId.get(d.s+'|'+String(d.i));
      if(exact)return exact;
      const candidates=[...new Map([...(byName.get(nimi(d.n))||[]),...(d.h?byImage.get(d.h)||[]:[])].map(t=>[t.lahde+'|'+t.id,t])).values()];
      const same=candidates.filter(t=>t.lahde===d.s);
      if(same.length)return choice(same,d);
      for(const source of ['sryhma','alko','kryhma']){const group=candidates.filter(t=>t.lahde===source);if(group.length)return choice(group,d)}
      return null;
    }
    function ratkaise(key){
      let parsed;try{parsed=JSON.parse(key)}catch{}
      if(parsed?.v===2)return descriptor(parsed);
      const records=historia[key]||[];
      if(records.length){
        const matches=records.map(descriptor).filter(Boolean);
        if(matches.length){matches.sort((a,b)=>(order[a.lahde]??9)-(order[b.lahde]??9));return matches[0]}
      }
      const parts=String(key).split('||');if(parts.length!==3)return null;
      const [name,,price]=parts, matches=byName.get(nimi(name))||[];
      for(const source of ['sryhma','alko','kryhma']){const group=matches.filter(t=>t.lahde===source);if(group.length)return choice(group,{n:name},Number(price))}
      return null;
    }
    return {ratkaise};
  }
  const api={tunniste,indeksi,kuva};if(typeof module==='object'&&module.exports)module.exports=api;else root.AaniTunniste=api;
})(typeof globalThis==='object'?globalThis:this);
