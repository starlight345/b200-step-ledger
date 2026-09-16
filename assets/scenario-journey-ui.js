(function () {
  'use strict';
  const $ = id => document.getElementById(id), J = window.CacheJourney;
  const NS = 'http://www.w3.org/2000/svg';
  const colors = {weight:'#e8809f',kv:'#4bc0be',state:'#5fc08a'}, names = {weight:'weight',kv:'KV',state:'state'};
  const bytes = x => x >= 1e9 ? (x / 1e9).toFixed(2) + ' GB' : x >= J.MiB ? (x / J.MiB).toFixed(1) + ' MiB' : (x / 1024).toFixed(1) + ' KiB';
  const time = ns => ns >= 1000 ? (ns / 1000).toFixed(2) + ' µs' : ns.toFixed(0) + ' ns';
  const number = id => Number($(id).value);
  const statusNames = {lookup:'L2 확인',hit:'적중 · HBM 접근 없음',miss:'미스 · HBM 읽기 필요',fetch:'HBM → L2',fill:'L2 채움',deliver:'L2 → 연산부',store:'연산부 → L2 수정',writeback:'L2 → HBM 되쓰기',evict:'L2 교체',near:'근접 메모리 → 연산부',nearfill:'HBM → 근접 메모리 최초 적재',ready:'요청 완료'};
  let exampleOverride=null, result, index=0, modelNs=0, lastFrame=0, lastShown=-1, playing=!matchMedia('(prefers-reduced-motion: reduce)').matches, finished=false, whole;
  function config() {
    whole = calc();
    const partition = $('mode').value === 'partition';
    const reserve = partition ? Math.min(whole.C,J.PERSIST_MAX) : 0;
    const tile = number('journey-tile') * J.MiB;
    return {capacityBytes:J.L2_BYTES-reserve,tileBytes:tile,hbmTBps:number('hbm'),l2TBps:number('l2-bandwidth'),
      nearTBps:number(partition?'l2-bandwidth':'near-bandwidth'),hbmLatencyNs:number('hbm-latency'),l2LatencyNs:number('l2-latency'),
      nearLatencyNs:number(partition?'l2-latency':'near-latency'),nearAvailable:(partition?reserve:whole.C)>=tile,
      nearLabel:partition?'persisting 예약 영역':'3D SRAM',primaryKind:$('journey-pattern').value==='dirty'?'state':whole.order[0]||'kv',otherKinds:Object.keys(whole.obj).filter(k=>whole.obj[k].alloc>0),pattern:$('journey-pattern').value,
      nearPrefill:$('journey-near-fill').checked};
  }
  function svgEl(tag, attrs, text) {const el=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,v);if(text!==undefined)el.textContent=text;return el;}
  function stack(element, values, capacity, suffix) {
    element.replaceChildren();const total=Object.values(values).reduce((a,b)=>a+b,0),scale=Math.max(capacity,total,1);
    for(const [kind,value] of Object.entries(values)) if(value>0){const part=document.createElement('span');part.style.width=100*value/scale+'%';part.style.background=colors[kind];part.title=names[kind]+' '+bytes(value)+' · '+(100*value/Math.max(capacity,1)).toFixed(1)+'% '+suffix;element.appendChild(part);}
    element.setAttribute('aria-label',Object.entries(values).map(([k,v])=>names[k]+' '+bytes(v)).join(', ')+', '+suffix+' '+bytes(capacity));
  }
  function miniStack(id,values,capacity,x,y,width){const el=$(id);el.replaceChildren(svgEl('rect',{x,y,width,height:8,fill:'#273341',rx:2}));let off=0;const scale=Math.max(capacity,Object.values(values).reduce((a,b)=>a+b,0),1);for(const [k,v]of Object.entries(values)){if(v<=0)continue;const w=width*v/scale;el.appendChild(svgEl('rect',{x:x+off,y,width:w,height:8,fill:colors[k]}));off+=w;}}
  function renderStorage(){
    const partition=$('mode').value==='partition',capacity=partition?Math.min(whole.C,J.PERSIST_MAX):whole.C;
    const hbmCapacity=191503138816; // CUDA device total from this B200; not free memory.
    const original=Object.fromEntries(Object.entries(whole.obj).map(([k,v])=>[k,v.alloc]));
    const placed=Object.fromEntries(Object.entries(whole.obj).map(([k,v])=>[k,v.placed]));
    const total=Object.values(original).reduce((a,b)=>a+b,0), used=Object.values(placed).reduce((a,b)=>a+b,0);
    stack($('hbm-storage'),original,hbmCapacity,'장치 용량');stack($('near-storage'),placed,capacity,'선택 용량');
    $('hbm-storage-total').textContent=bytes(total)+' / '+bytes(hbmCapacity);
    $('near-storage-total').textContent=bytes(used)+' / '+bytes(capacity);
    $('near-storage-title').textContent=partition?'persisting 예약 영역 · 배치한 사본':'3D SRAM · 배치한 사본';
    $('hbm-storage-detail').textContent=Object.entries(original).filter(([,v])=>v>0).map(([k,v])=>names[k]+' '+(100*v/hbmCapacity).toFixed(1)+'% ('+bytes(v)+')').join(' · ');
    $('near-storage-detail').textContent=capacity?Object.entries(placed).filter(([,v])=>v>0).map(([k,v])=>names[k]+' '+(100*v/capacity).toFixed(1)+'% ('+bytes(v)+')').join(' · ')+' · 미배치 '+(100*Math.max(0,capacity-used)/capacity).toFixed(1)+'%':'선택한 근접 메모리 용량이 없습니다.';
    $('storage-warning').textContent=total>hbmCapacity?'지속 데이터 계산만으로도 HBM 용량을 넘습니다. 이 설정은 실행 가능성을 보장하지 않는 가상 조건입니다.':'';
    miniStack('near-mini-storage',placed,capacity,39,115,137);miniStack('hbm-mini-storage',original,hbmCapacity,39,372,137);
  }
  function renderTiming(){
    const t=result.timings,c=result.config,fillEvent=result.events.find(e=>e.type==='nearfill');
    const max=Math.max(t.hit,t.miss,t.near,fillEvent?fillEvent.durationNs:0);
    const rows=[['HBM 미스',t.miss,'#6f84a1'],['L2 적중',t.hit,colors.kv],[c.nearLabel+' 상주',t.near,'#d5a84f']];
    if(fillEvent)rows.push(['단계 0 · HBM → '+c.nearLabel+' 최초 적재',fillEvent.durationNs,'#8297b1']);
    $('route-bars').replaceChildren();
    for(const [label,duration,color] of rows){const row=document.createElement('div');row.className='bar-row';const head=document.createElement('div');head.className='bar-head';const name=document.createElement('span');name.textContent=label;const value=document.createElement('b');value.textContent=time(duration);head.append(name,value);const track=document.createElement('div');track.className='route-bar';const fill=document.createElement('i');fill.style.width=100*duration/max+'%';fill.style.background=color;track.append(fill);row.append(head,track);$('route-bars').append(row);}
    $('near-title').textContent=c.nearLabel==='persisting 예약 영역'?'persisting 예약 영역 · 같은 물리 L2':'가상 3D SRAM';
    $('near-speed').textContent=c.nearTBps.toFixed(1)+' TB/s · '+c.nearLatencyNs+' ns';
    $('near-available').textContent=!c.nearAvailable?'용량 부족 · 경로 제외':fillEvent?'단계 0에서 '+bytes(c.tileBytes)+' 적재':'사전 상주 가정 · 적재 비용 제외';
    $('near-path-label').textContent=c.nearLabel==='persisting 예약 영역'?'일반 영역과 persisting 예약 영역은 같은 물리 L2':'추가 SRAM 직접 연결 가정';
    $('hbm-speed').textContent=c.hbmTBps.toFixed(2)+' TB/s · '+c.hbmLatencyNs+' ns';
    $('l2-speed').textContent=c.l2TBps.toFixed(1)+' TB/s · '+c.l2LatencyNs+' ns';
    $('cache-capacity').textContent=bytes(c.capacityBytes)+' 일반 영역';
    $('journey-scale').textContent='화면 시간 '+Math.round(500000/number('speed')).toLocaleString()+'배 확대 · 경로 간 같은 배율';
    renderStorage();
  }
  function paintCache(snapshot){
    const el=$('cache-slots'),c=result.config;el.replaceChildren();
    const count=Math.floor(c.capacityBytes/c.tileBytes),shown=Math.min(16,Math.max(count,1));
    for(let i=0;i<shown;i++){
      const entry=snapshot.entries[i],x=299+(i%4)*34,y=234+Math.floor(i/4)*14;
      el.appendChild(svgEl('rect',{x,y,width:28,height:11,rx:2,fill:entry?colors[entry.kind]:'#273341',stroke:entry?.dirty?'#ffcc66':'#455769','stroke-width':entry?.dirty?2:.5}));
      if(entry){const label=svgEl('text',{x:x+14,y:y+8.5,'text-anchor':'middle',fill:'#0c1118','font-size':8,'font-family':'monospace'},entry.id);el.appendChild(label);}
    }
    $('cache-usage').textContent=bytes(snapshot.used)+' / '+bytes(c.capacityBytes);
    const groups={weight:0,kv:0,state:0};for(const entry of snapshot.entries)groups[entry.kind]+=entry.bytes;
    const parts=Object.entries(groups).filter(([,v])=>v).map(([k,v])=>names[k]+' '+(100*v/Math.max(c.capacityBytes,1)).toFixed(1)+'%');
    parts.push('빈 공간 '+(100*Math.max(0,c.capacityBytes-snapshot.used)/Math.max(c.capacityBytes,1)).toFixed(1)+'%');
    $('cache-composition').textContent='L2 일반 영역 · 대표 타일 실험: '+parts.join(' · ')+'. 황색 테두리 = 수정되어 되쓰기가 필요한 조각.';
  }
  function paint(){
    if(!result)return;
    const e=result.events[index],atEnd=finished||e.durationNs===0,progress=atEnd?1:Math.max(0,Math.min(1,(modelNs-e.startNs)/e.durationNs));
    const snap=progress>=1?e.after:e.before,req=result.requests[e.request];
    if(lastShown!==index){
      const phase=result.config.pattern==='near'?(req.op==='fill'?'단계 0 · 최초 적재 · ':'단계 1 · 정상 서비스 · '):'';
      $('journey-kind').textContent=phase+'요청 '+(e.request+1)+'/'+result.requests.length+' · '+names[req.kind]+' '+req.id+' · '+req.source;
      $('journey-caption').textContent=e.text;
      $('journey-detail').textContent=statusNames[e.type]+' · 이 구간 '+time(e.durationNs)+' · 요청 전체 '+time(req.durationNs);
      const list=$('journey-history');list.replaceChildren();
      for(const item of result.events.slice(Math.max(0,index-3),index+1)){const li=document.createElement('li');li.textContent=time(item.startNs)+' · '+item.text;list.append(li);}
      lastShown=index;
    }
    $('journey-progress').style.width=100*progress+'%';
    $('journey-clock').textContent='모의 경과 '+time(Math.min(modelNs,result.totalNs))+' / '+time(result.totalNs)+(finished?' · 완료':'');
    $('journey-read').textContent=bytes(snap.stats.hbmRead);$('journey-write').textContent=bytes(snap.stats.hbmWrite);
    $('journey-hits').textContent=snap.stats.hits+' / '+snap.stats.misses;$('journey-evictions').textContent=snap.stats.evictions+'회';
    paintCache(snap);
    document.querySelectorAll('.journey-path,.journey-node').forEach(el=>el.classList.remove('active'));
    const packet=$('journey-packet');packet.setAttribute('visibility','hidden');
    if(e.path&&progress<1){const path=$('path-'+e.path);path.classList.add('active');const point=path.getPointAtLength(path.getTotalLength()*progress);packet.setAttribute('cx',point.x);packet.setAttribute('cy',point.y);packet.setAttribute('fill',(e.type==='store'||e.type==='writeback')?'#ffcc66':colors[req.kind]);packet.setAttribute('visibility','visible');}
    const node=e.type==='fetch'||e.type==='writeback'?'hbm':e.type==='near'||e.type==='nearfill'?'near':e.type==='ready'?'compute':'l2';$('node-'+node).classList.add('active');
    $('current-address').textContent=req.id;$('compute-state').textContent=e.type==='ready'?(req.op==='write'?'수정 완료':'데이터 도착'):e.type==='store'?'수정 중':'데이터 대기';
    $('play').textContent=playing?'Ⅱ 멈춤':finished?'▶ 다시 재생':'▶ 재생';
  }
  function reset(override){setPlaying(false);exampleOverride=override||null;result=J.simulate({...config(),...exampleOverride});index=0;modelNs=0;lastShown=-1;finished=false;lastFrame=0;renderTiming();paint();}
  function setPlaying(value){playing=value;lastFrame=0;$('play').textContent=value?'Ⅱ 멈춤':'▶ 재생';}
  function frame(timestamp){
    if(playing&&result&&!finished){
      if(lastFrame){modelNs+=Math.min(100,timestamp-lastFrame)*2*number('speed');
        while(index<result.events.length-1&&modelNs>=result.events[index].endNs)index++;
        if(modelNs>=result.totalNs){modelNs=result.totalNs;index=result.events.length-1;finished=true;playing=false;}
        paint();
      }lastFrame=timestamp;
    } else lastFrame=0;
    requestAnimationFrame(frame);
  }
  $('play').addEventListener('click',()=>{if(finished)reset(exampleOverride);setPlaying(!playing);paint();});
  $('next').addEventListener('click',()=>{setPlaying(false);if(index>=result.events.length-1)reset();else index++;modelNs=result.events[index].startNs;lastShown=-1;finished=index===result.events.length-1;paint();});
  $('reset-journey').addEventListener('click',()=>{setPlaying(false);reset(exampleOverride);});
  $('speed').addEventListener('change',()=>{renderTiming();lastFrame=0;});
  for(const id of ['journey-pattern','journey-tile','journey-near-fill'])$(id).addEventListener('change',()=>{reset();});
  for(const id of ['l2-bandwidth','near-bandwidth','l2-latency','hbm-latency','near-latency'])$(id).addEventListener('change',()=>{
    if(!$(id).checkValidity()||!Number.isFinite(number(id))){$(id).reportValidity();$(id).value=$(id).dataset.lastValid||$(id).defaultValue;return;}$(id).dataset.lastValid=$(id).value;render();
  });
  for(const id of ['l2-bandwidth','near-bandwidth','l2-latency','hbm-latency','near-latency'])$(id).addEventListener('input',()=>{if($(id).checkValidity()&&Number.isFinite(number(id)))render();});
  window.journeyApp={reset,setVisible(visible){if(!visible)setPlaying(false);paint();}};
  reset();requestAnimationFrame(frame);
})();
