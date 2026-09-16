const assert = require('node:assert/strict');
const {simulate, timings, transferNs, MiB} = require('../assets/cache-journey.js');
const base = {capacityBytes:32*MiB,tileBytes:16*MiB,hbmTBps:8,l2TBps:30,nearTBps:20,hbmLatencyNs:400,l2LatencyNs:100,nearLatencyNs:50};
let r=simulate({...base,pattern:'reuse'});
assert.equal(r.final.stats.misses,1);assert.equal(r.final.stats.hits,2);assert.equal(r.final.stats.hbmRead,16*MiB);
assert.equal(r.requests[0].durationNs,timings(base).miss);
assert(Math.abs(r.requests[1].durationNs-timings(base).hit)<1e-9);
r=simulate({...base,pattern:'eviction'});
assert.equal(r.final.stats.misses,4);assert.equal(r.final.stats.hits,1);
assert(r.events.some(e=>e.type==='evict'&&e.id==='A'));
assert.equal(r.final.stats.hbmWrite,0);
r=simulate({...base,pattern:'dirty'});
assert.equal(r.final.stats.hbmWrite,16*MiB);
assert(r.events.findIndex(e=>e.type==='writeback')<r.events.findIndex(e=>e.type==='evict'&&e.id==='A'));
for(const e of r.events){assert(e.after.used<=base.capacityBytes);assert(e.durationNs>=0)}
r=simulate({...base,pattern:'compare'});assert.equal(r.final.stats.nearHits,1);assert.equal(r.final.stats.hbmRead,16*MiB);
const slow=simulate({...base,hbmTBps:4,pattern:'compare'});assert(slow.requests[0].durationNs>r.requests[0].durationNs);assert.equal(slow.timings.hit,r.timings.hit);assert.equal(slow.timings.near,r.timings.near);
const fastL2=simulate({...base,l2TBps:60,pattern:'compare'});assert(fastL2.timings.hit<r.timings.hit);assert(fastL2.timings.miss<r.timings.miss);
const slowNear=simulate({...base,nearTBps:10,pattern:'compare'});assert(slowNear.timings.near>r.timings.near);
r=simulate({...base,capacityBytes:0,pattern:'dirty'});assert(r.final.entries.length===0);assert.equal(r.final.stats.hbmWrite,16*MiB);
r=simulate({...base,nearAvailable:false,pattern:'compare'});assert.equal(r.requests.length,2);assert.equal(r.final.stats.nearHits,0);
assert.equal(transferNs(8e6,8),1000);
// Phase 0 initial fill, then phase 1 service from the near tier.
r=simulate({...base,pattern:'near',nearAvailable:true,nearPrefill:true});
assert.equal(r.requests.length,2);assert.equal(r.requests[0].op,'fill');
assert.equal(r.final.stats.nearFill,16*MiB);assert.equal(r.final.stats.hbmRead,16*MiB);assert.equal(r.final.stats.nearRead,16*MiB);
assert(r.events.findIndex(e=>e.type==='nearfill')<r.events.findIndex(e=>e.type==='near'));
assert.equal(r.events.find(e=>e.type==='nearfill').durationNs,base.hbmLatencyNs+transferNs(16*MiB,base.hbmTBps));
const noFill=simulate({...base,pattern:'near',nearAvailable:true});
assert.equal(noFill.final.stats.nearFill,0);assert.equal(noFill.final.stats.hbmRead,0);
assert(r.totalNs>noFill.totalNs);
assert.equal(simulate({...base,pattern:'near',nearAvailable:false,nearPrefill:true}).final.stats.nearFill,0);
// nearFill labels the same bytes the fill already charged to hbmRead; it is not additional traffic.
assert.equal(r.final.stats.nearFill,r.final.stats.hbmRead);
assert.equal(r.events.filter(e=>e.type==='nearfill').length,1);
assert.equal(r.events.filter(e=>e.type==='fetch').length,0);
console.log('Cache journey: read conservation, hit/miss, LRU eviction, dirty writeback, timing sensitivity, zero capacity and near-tier initial fill passed.');
