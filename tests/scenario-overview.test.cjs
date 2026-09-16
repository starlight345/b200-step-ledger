const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const J=require('../assets/cache-journey.js');
for(const [pattern,hits,misses]of [['hit',3,0],['cold',0,3],['mixed',3,3]]){
 const r=J.simulate({pattern,nearAvailable:false});
 assert.equal(r.final.stats.hits,hits);assert.equal(r.final.stats.misses,misses);
 assert.equal(r.final.stats.hbmRead,misses*16*J.MiB);
 assert.equal(r.final.stats.l2Read,r.requests.length*16*J.MiB);
 for(const e of r.events)assert(e.after.used<=r.config.capacityBytes);
}
let r=J.simulate({pattern:'hit',capacityBytes:0});assert.equal(r.final.stats.hits,0);assert.equal(r.final.stats.misses,3);
r=J.simulate({pattern:'mixed',capacityBytes:2*16*J.MiB});assert.equal(r.final.stats.hits,2);assert.equal(r.final.stats.misses,4);
r=J.simulate({pattern:'near',nearAvailable:false});assert.equal(r.final.stats.hbmRead,16*J.MiB);assert.equal(r.final.stats.nearRead,0);
r=J.simulate({pattern:'near',nearAvailable:true});assert.equal(r.final.stats.hbmRead,0);assert.equal(r.final.stats.nearRead,16*J.MiB);
const summary=JSON.parse(fs.readFileSync('assets/placement_sweep_summary.json'));
for(const size of [64,256]){
 const rows=fs.readFileSync(`assets/experiments/placement_sweep_20260916/placement_m${size}_l36.jsonl`,'utf8').trim().split('\n').map(JSON.parse),trials=rows.filter(r=>r.kind==='trial');
 const match=summary.cells.find(c=>c.size_mib_requested===size&&c.layers===36);
 for(const policy of ['reserved_normal','persist_weight','persist_kv','persist_state']){
  const pairs=trials.filter(t=>t.policy===policy).map(t=>trials.find(a=>a.policy==='default'&&a.order===t.order&&a.pass===t.pass).step_ms/t.step_ms);
  assert.equal(pairs.length,18);const gm=Math.exp(pairs.reduce((a,b)=>a+Math.log(b),0)/pairs.length);assert(Math.abs(gm-match.aggregate[policy].geomean_speedup)<1e-10);
 }
 assert.equal(trials.reduce((a,t)=>a+t.validation_errors,0),0);
 // reserved_normal sets the reserve with no window, so persist_state/reserved_normal isolates what naming a target bought.
 const gm=policy=>{const v=trials.filter(t=>t.policy===policy).map(t=>trials.find(a=>a.policy==='default'&&a.order===t.order&&a.pass===t.pass).step_ms/t.step_ms);return Math.exp(v.reduce((a,b)=>a+Math.log(b),0)/v.length);};
 assert.equal(new Set(trials.filter(t=>t.policy==='reserved_normal').map(t=>t.window_bytes)).size,1);
 assert.equal(trials.find(t=>t.policy==='reserved_normal').window_bytes,0);
 const targeting=gm('persist_state')/gm('reserved_normal');
 if(size===64)assert(targeting>1.1,`64 MiB targeting gain collapsed to ${targeting}`);
 else assert(Math.abs(targeting-1)<0.01,`256 MiB targeting effect is not neutral: ${targeting}`);
}
// Execute the existing structural calculator with lightweight controls, then check conservation over its full input grid.
const elements=new Map();function el(id){if(!elements.has(id))elements.set(id,{value:'',textContent:'',innerHTML:'',insertAdjacentHTML(){},addEventListener(){}});return elements.get(id);}
el('hbm').value='8';el('l2-bandwidth').value='30';el('near-bandwidth').value='20';
const context={document:{getElementById:el,querySelectorAll(){return[];}},window:{},console};vm.createContext(context);
const html=fs.readFileSync('scenario-lab.html','utf8'),script=html.match(/<script>([\s\S]*?)<\/script>/)[1];vm.runInContext(script,context);
// The hardcoded PROXY36 table is displayed as measured, so pin it to the raw trials it claims to summarize.
const proxy36=vm.runInContext('PROXY36',context);
for(const size of [64,256]){
 const trials=fs.readFileSync(`assets/experiments/placement_sweep_20260916/placement_m${size}_l36.jsonl`,'utf8').trim().split('\n').map(JSON.parse).filter(r=>r.kind==='trial');
 const gm=policy=>{const v=trials.filter(t=>t.policy===policy).map(t=>trials.find(a=>a.policy==='default'&&a.order===t.order&&a.pass===t.pass).step_ms/t.step_ms);return Math.exp(v.reduce((a,b)=>a+Math.log(b),0)/v.length);};
 for(const [key,policy] of [['rn','reserved_normal'],['state','persist_state'],['weight','persist_weight'],['kv','persist_kv']])
  assert(Math.abs(proxy36[size][key]-gm(policy))<5e-5,`PROXY36[${size}].${key} drifted from ${policy}`);
}
let checks=0;
for(const model of ['llama','qwen','mistral','llama2','granite','gemma','gptoss','deepseek','proxy'])for(const mode of ['added','partition'])for(const capacity of ['0','1','4','9'])for(const batch of ['0','3','5'])for(const ctx of ['0','2','7']){
 Object.entries({model,mode,capacity,batch,context:ctx,policy:'auto'}).forEach(([k,v])=>el(k).value=v);
 const x=vm.runInContext('calc()',context),os=Object.values(x.obj);
 assert(os.every(o=>Math.abs(o.read+o.write-o.traffic)<1e-5));assert(os.every(o=>o.placed>=0&&o.placed<=o.alloc));
 assert(os.reduce((s,o)=>s+o.placed,0)<=Math.min(x.C,mode==='partition'?J.PERSIST_MAX:Infinity)+1e-5);
 assert(x.hbm>=0&&x.hbm<=x.total);assert(x.tier>=0&&x.tier<=x.total+1e-5);
 if(mode==='added')assert(Math.abs(x.hbm+x.tier-x.total)<1e-4);
 if(x.proxySpeed!==null)assert(model==='proxy'&&mode==='partition'&&x.C>=J.PERSIST_MAX&&[16,32,64,96,128,256].includes(x.N/1024));
 checks++;
}
console.log(`Overview: warm/cold/mixed conservation, zero capacity, near fallback, exact 18-cell measured ratios and ${checks} structural conditions passed.`);

const full=J.steadyContents({weight:64,kv:64,state:0},48);
assert.equal(full.used,48);assert.equal(full.values.weight,24);assert.equal(full.values.kv,24);
const small=J.steadyContents({weight:8,kv:4,state:2},48);assert.equal(small.used,14);assert.deepEqual(small.values,{weight:8,kv:4,state:2});
assert.equal(J.steadyContents({weight:0,kv:0,state:0},48).used,0);
assert.equal(J.steadyContents({weight:64,kv:64,state:64},0).used,0);
assert.throws(()=>J.steadyContents({weight:-1},48));
console.log('Steady-state composition: full/small/empty/zero-capacity budgets and per-object bounds passed.');
