// Compare les états du MP4 aux vignettes du vrai lecteur HTML aux mêmes instants.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {execFileSync} = require('node:child_process');
const path = require('node:path');
const {chromium} = require('playwright');
(async()=>{
  const browser = await chromium.launch({executablePath:process.env.CHROMIUM||'/usr/bin/chromium',args:['--no-sandbox']});
  try {
    const page = await browser.newPage();
    await page.setContent(fs.readFileSync(process.argv[2],'utf8'));
    const result = await page.evaluate(()=>{
      audioMix.removedCharacters = DATA.characters.slice(0,2).map(p=>p.id);
      const times = [...new Set([0,.249,.25,.499,.5,.749,.75,DATA.duration-.01,
        ...intervals.flatMap(i=>[Math.max(0,i.start-1.5),Math.max(0,i.start-.01),i.start,i.end]),
        ...cuts.flatMap(c=>[Math.max(0,c.time-.5),c.time,c.time+.249,c.time+.25])])].filter(t=>t<DATA.duration);
      const states = times.map(t=>{
        Object.defineProperty(video,'currentTime',{value:t,configurable:true}); update();
        return {portraits:cards.map(c=>[Number(c.card.style.opacity),c.caption.textContent]),
          plan:$('plan').hidden?null:[Number($('plan').style.opacity),$('plan-label').textContent]};
      });
      return {data:DATA,mix:audioMix,times,states};
    });
    const actual = JSON.parse(execFileSync(process.env.PYTHON||'python',['-c',`
import json,sys
sys.path.insert(0,'studio')
from mp4_visuals import portrait_state,plan_state
r=json.load(sys.stdin); d=r['data']; removed=r['mix']['removedCharacters']; result=[]
for t in r['times']:
 portraits=[]
 for p in d['characters']:
  opacity,caption=portrait_state(d['intervals'],p['id'],t,removed)
  portraits.append([opacity,caption or ('À vous' if p['id'] in removed else 'Film')+' · '+p['label']])
 cut,opacity,caption=plan_state(d['cuts'],t)
 result.append({'portraits':portraits,'plan':[opacity,caption] if cut else None})
print(json.dumps(result))
`],{cwd:path.resolve(__dirname,'../..'),input:JSON.stringify(result),encoding:'utf8'}));
    assert.deepEqual(actual,result.states);
    console.log(`Vignettes MP4 comparées au lecteur HTML à ${result.times.length} instants : mêmes opacités, clignotements, légendes et annonces de plan.`);
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exit(1)});
