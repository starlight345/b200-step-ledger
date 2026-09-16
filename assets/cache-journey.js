/* A deterministic teaching model. Tiles are illustrative address ranges, not GPU cache lines. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.CacheJourney = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const MiB = 2 ** 20;
  const L2_BYTES = 132644864, PERSIST_MAX = 82903040;
  function transferNs(bytes, tbps) {
    if (!(tbps > 0) || bytes < 0) throw new Error('Invalid transfer parameters');
    return bytes / (tbps * 1000); // decimal TB/s -> bytes/ns
  }
  function timings(c) {
    const l2 = c.l2LatencyNs + transferNs(c.tileBytes, c.l2TBps);
    return {
      hit: l2,
      miss: c.l2LatencyNs + c.hbmLatencyNs + transferNs(c.tileBytes, c.hbmTBps) + transferNs(c.tileBytes, c.l2TBps),
      near: c.nearLatencyNs + transferNs(c.tileBytes, c.nearTBps)
    };
  }
  function simulate(input) {
    const c = Object.assign({ capacityBytes: L2_BYTES, tileBytes: 16 * MiB,
      hbmTBps: 8, l2TBps: 30, nearTBps: 20, hbmLatencyNs: 400,
      l2LatencyNs: 100, nearLatencyNs: 50, nearAvailable: true,
      nearLabel: '3D SRAM', primaryKind: 'kv', otherKinds: ['weight','kv','state'], pattern: 'compare' }, input);
    if (!(c.tileBytes > 0) || c.capacityBytes < 0) throw new Error('Invalid cache size');
    for (const k of ['hbmLatencyNs','l2LatencyNs','nearLatencyNs']) if (c[k] < 0) throw new Error('Negative latency');
    timings(c);
    const resident = new Map(), events = [], requests = [];
    let used = 0, now = 0;
    const stats = { hits: 0, misses: 0, nearHits: 0, hbmRead: 0, hbmWrite: 0, l2Read: 0, l2Write: 0, nearRead: 0, evictions: 0 };
    function snapshot() {
      return { used, entries: Array.from(resident, ([id, x]) => ({ id, bytes: x.bytes, dirty: x.dirty, kind: x.kind })), stats: { ...stats } };
    }
    function emit(type, id, durationNs, path, text, change) {
      const before = snapshot();
      if (change) change();
      const after = snapshot();
      events.push({ type, id, durationNs, startNs: now, endNs: now + durationNs, path, text, before, after, request: requests.length - 1 });
      now += durationNs;
    }
    function touch(id) { const value = resident.get(id); resident.delete(id); resident.set(id, value); }
    function evictFor(bytes) {
      while (used + bytes > c.capacityBytes && resident.size) {
        const [id, entry] = resident.entries().next().value;
        if (entry.dirty) emit('writeback', id, c.hbmLatencyNs + transferNs(entry.bytes, c.hbmTBps), 'writeback',
          `${id}가 수정되어 HBM에 먼저 되씁니다.`, () => { stats.hbmWrite += entry.bytes; });
        emit('evict', id, 0, '', `${id}를 L2에서 교체합니다.`, () => {
          resident.delete(id); used -= entry.bytes; stats.evictions++;
        });
      }
    }
    function access(id, op = 'read', near = false) {
      const start = now;
      const kind = id === 'A' ? c.primaryKind : c.otherKinds[(Number(id.slice(1)) - 1) % c.otherKinds.length];
      const req = { id, kind, op, near, source: near ? c.nearLabel : resident.has(id) ? 'L2 hit' : 'HBM miss', startNs: start, firstEvent: events.length };
      requests.push(req);
      if (near) {
        emit('near', id, c.nearLatencyNs + transferNs(c.tileBytes, c.nearTBps), 'near',
          `${c.nearLabel}에 미리 둔 ${id}를 연산부로 전달합니다.`, () => { stats.nearRead += c.tileBytes; stats.nearHits++; });
      } else {
        const hit = resident.has(id);
        emit('lookup', id, c.l2LatencyNs, 'lookup', `${id}가 L2에 있는지 확인합니다.`);
        if (hit) {
          emit('hit', id, 0, '', `${id}: L2 적중. HBM에서 다시 읽지 않습니다.`, () => { stats.hits++; touch(id); });
        } else {
          emit('miss', id, 0, '', `${id}: L2 미스. HBM에서 가져옵니다.`, () => { stats.misses++; });
          if (c.tileBytes <= c.capacityBytes) evictFor(c.tileBytes);
          emit('fetch', id, c.hbmLatencyNs + transferNs(c.tileBytes, c.hbmTBps), 'fetch',
            `HBM → L2로 ${id}를 가져옵니다.`, () => { stats.hbmRead += c.tileBytes; });
          emit('fill', id, 0, '', c.tileBytes <= c.capacityBytes ? `${id}의 사본을 L2에 채웠습니다.` : `${id}는 통과하지만 이 타일 전체를 보존할 공간은 없습니다.`, () => {
            if (c.tileBytes <= c.capacityBytes) { resident.set(id, { bytes: c.tileBytes, dirty: false, kind }); used += c.tileBytes; }
          });
        }
        if (op === 'write') {
          emit('store', id, transferNs(c.tileBytes, c.l2TBps), 'store', `${id}를 L2에서 수정합니다. HBM 쓰기는 교체할 때 일어납니다.`, () => {
            stats.l2Write += c.tileBytes;
            if (resident.has(id)) { resident.get(id).dirty = true; touch(id); }
          });
          if (!resident.has(id)) emit('writeback', id, c.hbmLatencyNs + transferNs(c.tileBytes, c.hbmTBps), 'writeback',
            `보존하지 못한 ${id}를 HBM에 씁니다.`, () => { stats.hbmWrite += c.tileBytes; });
        } else {
          emit('deliver', id, transferNs(c.tileBytes, c.l2TBps), 'deliver', `${id}: L2 → 연산부 전달.`, () => { stats.l2Read += c.tileBytes; });
        }
      }
      emit('ready', id, 0, '', op === 'write' ? `${id} 수정 완료.` : `${id}가 연산부에 도착했습니다. 연산 자체의 시간은 제외합니다.`);
      req.endNs = now; req.durationNs = now - start; req.lastEvent = events.length - 1;
    }
    // Warm-cache scenario starts with an explicit preloaded copy; warm-up traffic is excluded.
    if (c.pattern === 'hit' && c.tileBytes <= c.capacityBytes) {
      resident.set('A', {bytes:c.tileBytes, dirty:false, kind:c.primaryKind}); used=c.tileBytes;
    }
    const initial = snapshot();
    if (c.pattern === 'hit') {
      access('A'); access('A'); access('A');
    } else if (c.pattern === 'cold') {
      access('B1'); access('B2'); access('B3');
    } else if (c.pattern === 'mixed') {
      access('A'); access('B1'); access('A'); access('B2'); access('A'); access('B1');
    } else if (c.pattern === 'near') {
      access('A', 'read', c.nearAvailable);
    } else if (c.pattern === 'compare') {
      access('A'); access('A'); if (c.nearAvailable) access('A', 'read', true);
    } else if (c.pattern === 'reuse') {
      access('A'); access('A'); access('A');
    } else if (c.pattern === 'eviction' || c.pattern === 'dirty') {
      access('A'); access('A', c.pattern === 'dirty' ? 'write' : 'read');
      const count = Math.max(1, Math.floor(c.capacityBytes / c.tileBytes));
      for (let i = 0; i < count; i++) access('B' + (i + 1));
      access('A');
    } else throw new Error('Unknown access pattern');
    return { config: c, events, requests, initial, totalNs: now, final: snapshot(), timings: timings(c) };
  }
  // An explicitly hypothetical steady-state snapshot. This does not predict hit rate.
  function steadyContents(remaining, capacityBytes) {
    if (!(capacityBytes >= 0) || Object.values(remaining).some(v => !Number.isFinite(v) || v < 0)) throw new Error('Invalid residency input');
    const workingSet = Object.values(remaining).reduce((a,b) => a+b, 0);
    const used = Math.min(capacityBytes, workingSet);
    return {values:Object.fromEntries(Object.entries(remaining).map(([k,v]) => [k,workingSet ? used*v/workingSet : 0])), used, workingSet, capacityBytes};
  }
  return { MiB, L2_BYTES, PERSIST_MAX, transferNs, timings, simulate, steadyContents };
});
