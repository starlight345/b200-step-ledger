(function(){
'use strict';
const $=id=>document.getElementById(id),J=window.CacheJourney,K=['weight','kv','state'];
const C={weight:'#e8809f',kv:'#4bc0be',state:'#5fc08a'},N={weight:'weight',kv:'KV',state:'state'};
const HBM=191503138816, sum=o=>Object.values(o).reduce((a,b)=>a+b,0), empty=()=>({weight:0,kv:0,state:0});
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const b=x=>x===null?'미계측':x===0?'0 B':x>=1e9?(x/1e9).toFixed(2)+' GB':x>=J.MiB?(x/J.MiB).toFixed(1)+' MiB':x>=1024?(x/1024).toFixed(1)+' KiB':x.toFixed(0)+' B';
const pct=v=>(v>0&&v<.1?v.toFixed(3):v.toFixed(1));
const t=ns=>ns>=1e6?(ns/1e6).toFixed(3)+' ms':ns>=1000?(ns/1000).toFixed(2)+' µs':ns.toFixed(0)+' ns';
const cases={
 model:{label:'모델 한 스텝',title:'전체 모델의 저장량과 한 스텝 이동량',kind:'model'},
 mixed:{label:'일반적인 혼합 접근',title:'처음 읽기와 다시 읽기가 섞이면',kind:'sim',pattern:'mixed'},
 hit:{label:'캐시 적중',title:'이미 담겨 있으면 HBM을 다시 읽지 않습니다',kind:'sim',pattern:'hit'},
 cold:{label:'캐시 미스',title:'처음 읽는 데이터는 HBM에서 채웁니다',kind:'sim',pattern:'cold'},
 eviction:{label:'용량 압박 · 교체',title:'다른 데이터가 밀어내면 다시 HBM으로',kind:'sim',pattern:'eviction'},
 dirty:{label:'수정 · 되쓰기',title:'수정한 state를 내보낼 때는 HBM에 되씁니다',kind:'sim',pattern:'dirty'},
 near:{label:'근접 메모리 상주',title:'미리 배치한 사본을 가까운 SRAM에서 전달합니다',kind:'sim',pattern:'near'},
 measured64:{label:'B200 · state 보호 이득',title:'64 MiB 객체 · state 보호가 빨랐던 실제 실험',kind:'proxy',size:64},
 measured256:{label:'B200 · 캐시 분할 손해',title:'256 MiB 객체 · 보호해도 느려졌던 실제 실험',kind:'proxy',size:256},
 llama:{label:'실제 Llama decode',title:'Llama-3.1-8B · B200에서 실행한 조건',kind:'decode',model:'llama',key:'llama31_8b'},
 granite:{label:'실제 Granite decode',title:'Granite 하이브리드 · B200에서 실행한 조건',kind:'decode',model:'granite',key:'granite_4h'}
};
let selected='model',view='system',evidence={},loadError='',cachePhase='final',running=!matchMedia('(prefers-reduced-motion: reduce)').matches,current;
$('system-panel').innerHTML=`<div class="system-intro"><h3>상황을 골라 전체 지도를 비교하세요</h3><p>상자 안 색은 저장 구성, 연결선은 데이터 경로입니다. 저장량과 이동량은 서로 다른 값입니다.</p></div><div class="case-groups"><div class="case-group" id="sim-cases"><span>구조 계산 · 설명용 상황</span></div><div class="case-group" id="measured-cases"><span>저장된 B200 실험 · 실제 기록에서 불러옴</span></div></div><div id="system-content"></div>`;
for(const [key,c]of Object.entries(cases)){const btn=document.createElement('button');btn.className='case-button';btn.textContent=c.label;btn.dataset.case=key;btn.setAttribute('aria-pressed','false');if(['proxy','decode'].includes(c.kind))btn.dataset.measured='';btn.addEventListener('click',()=>select(key));$(['proxy','decode'].includes(c.kind)?'measured-cases':'sim-cases').append(btn);}
const note=document.createElement('p');note.id='scenario-control-note';note.className='scenario-control-note';document.querySelector('.controls').append(note);
// Controls are shared with the whole-model calculator. Recorded cases keep their exact source condition.
const controlNote=document.getElementById('scenario-control-note');
function settings(){return{hbmTBps:Number($('hbm').value),l2TBps:Number($('l2-bandwidth').value),nearTBps:Number($('near-bandwidth').value),hbmLatencyNs:Number($('hbm-latency').value),l2LatencyNs:Number($('l2-latency').value),nearLatencyNs:Number($('near-latency').value),tileBytes:16*J.MiB};}
function copyValues(x,key){return Object.fromEntries(K.map(k=>[k,x.obj[k][key]]));}
function store(title,values,capacity,foot,unknown=false){return{title,values,capacity,foot,unknown};}
function source(label,url){return{label,url};}
function modelData(x=calc(),recorded=false){
 const partition=$('mode').value==='partition',reserve=partition?Math.min(x.C,J.PERSIST_MAX):0,nearCap=partition?reserve:x.C;
 const flows={fetch:empty(),writeback:empty(),deliver:empty(),store:empty(),near:empty(),nearRead:empty(),nearWrite:empty()},remaining=x.total-x.tier;
 const missFraction=remaining?Math.min(1,x.hbm/remaining):0;
 for(const k of K){const o=x.obj[k],p=o.alloc?o.placed/o.alloc:0;flows.fetch[k]=o.read*(1-p)*missFraction;flows.writeback[k]=o.write*(1-p)*missFraction;flows.deliver[k]=o.read*(1-p);flows.store[k]=o.write*(1-p);flows.near[k]=o.traffic*p;flows.nearRead[k]=o.read*p;flows.nearWrite[k]=o.write*p;}
 const payload=copyValues(x,'alloc'),placed=copyValues(x,'placed');
 return{type:'model',title:cases.model.title,tag:'가정 + 구조 계산',desc:x.m.name+' · B='+x.B+' · '+x.N.toLocaleString()+' tokens · 전체 모델 한 스텝. 일반 L2의 주소별 적중·미스는 알 수 없습니다.',unit:'한 스텝',stores:[store('HBM · 지속 데이터',payload,HBM,'구조·가정값 · 실제 할당 덤프 아님'),store('일반 L2 · 사본 캐시',empty(),J.L2_BYTES-reserve,'객체별 점유와 적중률 미계측',true),store(partition?'보호 L2 · 같은 물리 캐시':'가상 3D SRAM',placed,nearCap,'사전 배치 가정 · 초기 적재 비용 제외')],flows,
 facts:[['HBM 읽기 + 쓰기',b(x.hbm),'계산 · 실제 버스 카운터 아님'],['근접 메모리 서비스',b(x.tier),'읽기 + 쓰기 합'],['지속 데이터',b(sum(payload)),'HBM 원본 · 캐시 사본은 별도'],['서비스 시간 합',t(x.serial*1e6),'HBM + 근접 경로 · 겹침 제외']],
 explanation:partition?'일반 영역과 보호 영역은 하나의 물리 L2를 나눕니다. 일반 영역의 절감량은 남은 작업집합에 균등하게 적중한다는 가정입니다.':'HBM에서 읽는 선은 L2를 거쳐 연산부로 이어집니다. 이 전체 모델 계산은 일반 L2의 재사용 절감을 0으로 두며, 선택한 추가 SRAM의 배치 효과만 뺍니다. 실제 B200 적중률을 0%로 측정했다는 뜻은 아닙니다.',
 warnings:sum(payload)>HBM?'지속 데이터만으로 장치 용량을 초과합니다. 실행 가능성을 보장하지 않는 조건입니다.':'',
 formula:modelFormula(x,partition),sources:[source('모델 구조·시간 기록','assets/model_evidence.json'),source('용량·weight 보정 입력','assets/numerical_evidence.json'),source('모델 계수표·전체 전제','SCENARIO_MODEL.md#whole-model-inputs')],partition,x};
}
function modelFormula(x,partition){
 const lines=[`B = ${x.B}, N = ${x.N}, 근접 용량 C = ${x.C.toLocaleString()} B`,`KV 저장 = B × Σ[층 수 × 토큰당 KV 바이트 × 유효 토큰 수]`,`전역 층 유효 토큰 = N; sliding 층 = min(N, window)`,`새 KV 쓰기/step = B × Σ[층 수 × 토큰당 KV 바이트]`,`state 저장 = B × Σ[state 층 수 × 층당 state 바이트]`];
 for(const g of x.m.groups){lines.push(g.t==='state'?`state: ${x.B} × ${g.n} × ${g.c} = ${(x.B*g.n*g.c).toLocaleString()} B`:`${g.t} KV: ${x.B} × ${g.n} × ${g.b} × ${g.t==='sliding'?Math.min(x.N,g.w):x.N} = ${(x.B*g.n*g.b*(g.t==='sliding'?Math.min(x.N,g.w):x.N)).toLocaleString()} B`);}
 if(x.m.proxy)lines.push(`대리실험: weight = KV = state = ${x.N}/1024 MiB. 실제 실험의 정렬된 크기는 ‘B200’ 사례 원자료에 별도 표기.`);
 if(x.m.moe){const m=x.m.moe;lines.push(`MoE 활성 expert 합집합 = E × [1 − (1 − k/E)^B]`,`= ${m.E} × [1 − (1 − ${m.k}/${m.E})^${x.B}] = ${union(x.m,x.B).toFixed(3)}개`,`weight 읽기 = (trunk ${m.base} + expert당 ${m.per} × ${m.layers}층 × 합집합) GB`,`독립·균등 라우팅 가정. 실제 expert 선택 기록 아님.`);}
 lines.push(`weight 상주 = ${b(x.obj.weight.alloc)}, step 읽기 = ${b(x.obj.weight.read)}`,`weight 입력은 계산기의 시나리오 상수입니다. 모델별 실측 HBM 바이트나 실제 allocation 덤프로 취급하지 않습니다.`,`객체 가치 = (읽기 + 쓰기)/저장량 → weight ${x.obj.weight.score.toFixed(3)}, KV ${x.obj.kv.score.toFixed(3)}, state ${x.obj.state.score.toFixed(3)}`,`배치 순서 = ${x.order.join(' → ')}; 객체 배치 = min(남은 C, 객체 저장량)`,`근접 서비스 = Σ[객체 접근량 × 배치량/객체 저장량] = ${b(x.tier)}`);
 if(partition)lines.push(`보호 R = min(C, 82,903,040 B); 일반 L2 = 132,644,864 − R`,`남은 작업집합 W = Σ저장량 − Σ배치량`,`일반 적중 절감 = min(1, 일반 L2/W) × (전체 접근 − 근접 서비스)`,`HBM = 전체 접근 − 근접 서비스 − 일반 적중 절감`);
 else lines.push(`HBM = Σ(읽기 + 쓰기) − 근접 서비스 = ${b(x.total)} − ${b(x.tier)} = ${b(x.hbm)}`);
 lines.push(`서비스 시간 = HBM B/(${x.hbw/1e12} × 10¹² B/s) + 근접 B/(${x.tbw/1e12} × 10¹² B/s)`,`= ${t(x.hbmMs*1e6)} + ${t(x.tierMs*1e6)} = ${t(x.serial*1e6)}`,`유효 KV payload를 계산하며 엔진이 예약한 전체 KV pool·페이지 패딩은 포함하지 않습니다.`,`추가 SRAM 장기 상주를 가정하며 최초 채움·교체·종료 flush 비용은 제외합니다.`,`state/KV 쓰기는 균등한 배치 비율만큼 근접 메모리로 갑니다. 실제 주소 선택 기록은 없습니다.`,`전체 모델 계산에는 요청 개수를 모르므로 고정 지연을 더하지 않습니다.`,`한 요청 화면의 시간 = 고정 지연 + 타일 전송 시간이며, 전체 모델 시간과 다릅니다.`,`기준 시간 입력 m.base = ${x.m.base} ms (해당 모델의 고정 기준값)`,`기존 예상 속도 카드: compute floor = max(0.02 ms, 기준시간 − 전체 접근/HBM BW)`,`step 추정 = max(compute floor, HBM 서비스, 근접 서비스). 기준시간은 m.base 고정 입력이며 조건별 실측 예측값이 아닙니다.`);
 return lines;
}
function simData(){
 const c=cases[selected],s=settings(),x=calc(),partition=$('mode').value==='partition',reserve=partition?Math.min(x.C,J.PERSIST_MAX):0;
 const r=J.simulate({...s,pattern:c.pattern,primaryKind:['dirty','near'].includes(selected)?'state':'kv',otherKinds:K,capacityBytes:J.L2_BYTES-reserve,nearAvailable:(partition?reserve:x.C)>=s.tileBytes,nearLabel:partition?'보호 L2':'3D SRAM',nearTBps:partition?s.l2TBps:s.nearTBps,nearLatencyNs:partition?s.l2LatencyNs:s.nearLatencyNs});
 const payload=empty(),seen=new Set();for(const req of r.requests)if(!seen.has(req.id)){seen.add(req.id);payload[req.kind]+=s.tileBytes;}
 const flows={fetch:empty(),writeback:empty(),deliver:empty(),store:empty(),near:empty()};
 for(const e of r.events)if(flows[e.type]){const kind=e.type==='writeback'?e.before.entries.find(a=>a.id===e.id)?.kind||r.requests[e.request].kind:r.requests[e.request].kind;flows[e.type][kind]+=s.tileBytes;}
 flows.nearRead={...flows.near};flows.nearWrite=empty();
 const cache=empty();for(const a of r[cachePhase].entries)cache[a.kind]+=a.bytes;
 const near=empty();if(selected==='near'&&r.config.nearAvailable)near.state=s.tileBytes;
 const stats=r.final.stats,miss=stats.misses,hit=stats.hits;
 return{type:'sim',title:c.title,tag:'설명용 시뮬레이션 · 실측 아님',desc:'16 MiB 조각 '+r.requests.length+'개 요청. 전체 모델의 한 스텝이 아니라, 선택한 상황만 떼어낸 예시입니다.',unit:'이 요청 묶음',stores:[store('HBM · 원본 조각',payload,HBM,'회색은 실제 free 측정이 아님'),store('일반 L2 · '+(cachePhase==='final'?'실행 후':'실행 전'),cache,r.config.capacityBytes,'16 MiB 타일 · LRU 모의 점유'),store(partition?'보호 L2 · 같은 물리 캐시':'가상 3D SRAM',near,partition?reserve:x.C,'미리 담은 사본 · 초기 적재 비용 제외')],flows,partition,
 facts:[['L2 적중 / 미스',hit+' / '+miss,'동일 조각 ID로 판정'],['HBM 읽기',b(stats.hbmRead),'모의 미스 × 16 MiB'],['HBM 되쓰기',b(stats.hbmWrite),'수정 조각을 교체할 때'],['요청 전체 시간',t(r.totalNs),'직렬 서비스 · 연산 시간 제외']],
 explanation:({mixed:'A → B1 → A → B2 → A → B1. 용량과 접근 순서에 따라 미스와 재사용이 나뉩니다. 실제 workload의 평균 적중률을 뜻하지 않습니다.',hit:'A를 L2에 미리 채운 뒤 세 번 읽습니다. 사전 적재 비용은 이 구간 밖에 있습니다.',cold:'서로 다른 B1·B2·B3를 한 번씩 읽습니다. 처음에는 L2가 비어 있습니다.',eviction:'A를 읽고 재사용한 뒤, 캐시를 채울 만큼 다른 조각을 읽고 다시 A를 찾습니다. 수정하지 않은 조각은 버릴 때 HBM 쓰기가 없습니다.',dirty:'A(state)를 읽고 수정한 뒤 경쟁 조각을 읽습니다. 더티 A를 내보내면 16 MiB를 되쓴 다음, 다음 A 요청 때 다시 가져옵니다.',near:'A(state)가 근접 메모리에 이미 있다는 가정입니다. 용량이 16 MiB보다 작으면 HBM 미스 경로로 돌아갑니다.'})[selected],
 formula:[`조각 Q = 16 × 2²⁰ = ${s.tileBytes.toLocaleString()} B`,`요청 순서 = ${r.requests.map(q=>q.id+(q.op==='write'?' 수정':'')).join(' → ')}`,`일반 L2 = ${r.config.capacityBytes.toLocaleString()} B; 보관 가능한 전체 타일 = floor(L2/Q) = ${Math.floor(r.config.capacityBytes/s.tileBytes)}`,`시작 상태: ${r.initial.entries.length?'A가 미리 상주 (warm-up 제외)':'일반 L2 비어 있음'}`,`미스 읽기 = ${miss} × Q = ${stats.hbmRead.toLocaleString()} B`,`되쓰기 = 수정되어 내보낸 조각 × Q = ${stats.hbmWrite.toLocaleString()} B`,`적중: L2 지연 ${s.l2LatencyNs} ns + Q / (${s.l2TBps} × 1000 B/ns) = ${t(r.timings.hit)}`,`미스: L2 지연 + HBM 지연 ${s.hbmLatencyNs} ns + Q/(${s.hbmTBps} × 1000) + Q/(${s.l2TBps} × 1000) = ${t(r.timings.miss)}`,`근접: 지연 ${r.config.nearLatencyNs} ns + Q/(${r.config.nearTBps} × 1000) = ${t(r.timings.near)}`,`전체 = 각 lookup·transfer·write-back 구간의 합 = ${t(r.totalNs)}`,`채움 bookkeeping은 0 ns. HBM 전송에 채움 비용을 포함합니다.`,`완전 연관 LRU, write-allocate/write-back 가정. GPU의 실제 cache line·set·동시 요청·압축·L1·연산은 생략합니다.`,`16 MiB 전체 타일보다 일반 L2가 작으면 타일을 보존하지 않습니다. 실제 하드웨어의 규칙이 아닌 예시 모델의 한계입니다.`],sources:[source('시뮬레이터 로직','assets/cache-journey.js'),source('전제·단위','SCENARIO_MODEL.md')],r};
}
function proxyData(){
 const c=cases[selected],rows=evidence['raw'+c.size],cell=evidence.sweep.cells.find(a=>a.size_mib_requested===c.size&&a.layers===36),device=rows.find(a=>a.kind==='device'),trials=rows.filter(a=>a.kind==='trial'),target=trials.find(a=>a.policy==='persist_state'),size=device.object_bytes,reserve=device.reserve_bytes;
 const names={default:'보호 없음',reserved_normal:'영역만 예약',persist_weight:'weight 보호',persist_kv:'KV 보호',persist_state:'state 보호'};
 const median=a=>{a.sort((a,b)=>a-b);return(a[Math.floor((a.length-1)/2)]+a[Math.floor(a.length/2)])/2;};
 const table=Object.keys(names).map(k=>({name:names[k],time:median(trials.filter(a=>a.policy===k).map(a=>a.step_ms)),speed:k==='default'?1:cell.aggregate[k].geomean_speedup,selected:k==='persist_state'}));
 const payload={weight:size,kv:size,state:size},flows={fetch:null,writeback:null,deliver:{weight:size,kv:size,state:size},store:{weight:0,kv:0,state:size},near:null,nearRead:null,nearWrite:null};
 return{type:'proxy',title:c.title,tag:'B200 실측 · 시간/설정/검증 결과',desc:'동일 크기 weight·KV·state, 36층, 6가지 접근 순서 × 3회 반복. 각 조건의 기본 정책과 짝지어 비교합니다. 실제 주소·캐시 내용의 녹화는 아닙니다.',unit:'대리실험 한 스텝',partition:true,stores:[store('HBM · 할당한 객체',payload,device.total_bytes,'원자료 object_bytes · 객체 3개'),store('일반 L2 · 분할 후',empty(),device.l2_bytes-reserve,'점유 구성·적중률 미계측',true),store('보호 L2 · 같은 물리 캐시',empty(),reserve,'state 보호 요청 창 '+b(target.window_bytes),true)],flows,
 facts:[['state 보호 속도',cell.aggregate.persist_state.geomean_speedup.toFixed(4)+'×','기본 대비 · 짝지은 비율의 기하평균'],['검증 오류',cell.validation_errors+' / '+cell.trial_count,'5개 정책을 포함한 전체 trial'],['논리 접근량',b(size*4),'읽기 3회 + state 쓰기 1회'],['보호 예산/객체',Math.min(100,reserve/size*100).toFixed(1)+'%','예산 비율 · 실제 적중률 아님']],
 explanation:c.size===64?'state 보호의 실행시간 개선은 실제로 측정했습니다. 다만 얼마의 HBM 읽기·쓰기를 줄였는지, L2에 어떤 바이트가 남았는지는 직접 계수하지 못했습니다.':'대상 객체가 커지면 보호 예산이 전체를 덮지 못합니다. 이 조건에서는 모든 보호 정책의 실행시간이 기본보다 길었습니다. 용량 비율만으로 실제 캐시 교체 동작을 확정하지 않습니다.',
 formula:[`원자료: ${cell.file}; layers = 36`,`실제 정렬된 객체 크기 = ${size.toLocaleString()} B (요청 ${c.size} MiB와 약간 다름)`,`HBM 객체 = weight + KV + state = 3 × ${size.toLocaleString()} = ${(3*size).toLocaleString()} B`,`논리 읽기 = W + K + S; 논리 쓰기 = S; 합 = 4 × 객체 = ${(4*size).toLocaleString()} B`,`L2 = ${device.l2_bytes.toLocaleString()} B; 예약 = ${reserve.toLocaleString()} B; 일반 = ${(device.l2_bytes-reserve).toLocaleString()} B`,`state access-policy 요청 창 = ${target.window_bytes.toLocaleString()} B`,`예산/객체 = min(1, ${reserve}/${size}) = ${(Math.min(1,reserve/size)*100).toFixed(3)}% (적중률 아님)`,`각 matched cell i: rᵢ = 기본 step_msᵢ / 보호 step_msᵢ`,`표시 speedup = exp[Σ ln(rᵢ)/18] = ${cell.aggregate.persist_state.geomean_speedup.toFixed(6)}×`,`표의 시간은 정책별 18개 trial 중앙값. 중앙값끼리 나눈 비율은 위 기하평균과 다를 수 있습니다.`,`1보다 크면 빠름, 1보다 작으면 느림. 같은 order/pass끼리 짝지어 비교합니다.`,`warm-up ${target.warm_iterations}회, pilot ${target.pilot_iterations}회 이후 측정. iterations는 정책별로 다를 수 있습니다.`,`논리 접근량 ≠ 실제 HBM 바이트. 이 실험은 HBM read/write·L2 hit counter를 수집하지 않았습니다.`,`기존 L2 예약 대리실험이며 추가 3D SRAM 칩을 제작·측정한 결과가 아닙니다.`],
 sources:[source('실제 trial 원자료','assets/experiments/placement_sweep_20260916/'+cell.file),source('18조건 집계','assets/placement_sweep_summary.json'),source('집계 계산 코드','assets/experiments/placement_sweep_20260916/analyze_placement_sweep.py')],table};
}
function decodeData(){
 const c=cases[selected],m=evidence.models.models.find(a=>a.key===c.key),row=m.decode_grid.find(a=>a.batch===8&&a.context_tokens===2048),x=calc(),d=modelData(x,true);
 d.type='decode';d.title=c.title;d.tag='B200 실측 시간 + 구조 기반 메모리 계산';d.desc=m.name+' · B=8 · 문맥 2,048 · '+m.decode_measurement_date+' · '+evidence.models.serving_engine+'. 저장량·이동 경로 도식은 구조 계산입니다.';
 d.flows.fetch=null;d.flows.writeback=null;d.flows.near=empty();d.flows.nearRead=empty();d.flows.nearWrite=empty();d.stores[2]=store('추가 3D SRAM 없음',empty(),0,'이 실행에는 추가 SRAM이 없습니다');
 d.facts=[['기록된 step 시간',row.step_ms.toFixed(4)+' ms','동기화 후 실행 완료 간격 중앙값'],['처리량',row.tokens_per_second.toFixed(1)+' tok/s','실행 기록 · batch decode'],['측정 구간',row.timing_intervals_used+' / '+row.decode_steps,'사용한 시간 간격 / decode steps'],['HBM 물리 이동량','미계측','이 시간 기록만으로 환산 불가']];
 d.explanation='실제 실행시간을 확인할 수 있는 기준선입니다. 아래 계산은 모델 구조로 필요한 데이터 크기를 설명하며, 이 실행의 실제 캐시 적중률이나 HBM read/write를 복원하지 않습니다.';
 d.formula=[`기록 파일: ${m.runtime_source_file}`,`B = 8, 문맥 = 2,048, decode_steps = ${row.decode_steps}, timing_intervals_used = ${row.timing_intervals_used}`,`step_ms = CUDA 동기화 후 execute_model 완료 시각 간격들의 중앙값 = ${row.step_ms} ms`,`순수 커널 시간이나 클라이언트 전체 응답 지연이 아닙니다.`,`처리량 ≈ B × 1000/step_ms = ${(8000/row.step_ms).toFixed(1)} tok/s (원자료 ${row.tokens_per_second} tok/s)`,`실행 시간 → HBM 바이트 역산은 하지 않습니다. compute·메모리·겹침이 함께 포함되어 있기 때문입니다.`,'이하 저장량·접근량은 별도 구조 계산이며 위 실행에서 직접 계수한 물리 바이트가 아닙니다.',...modelFormula(x,false)];
 if(m.state_traffic_estimation){const e=m.state_traffic_estimation;d.formula.push(`별도 DCGM 회귀: ${e.method}`,`배경 제거 추정 범위 ${e.global_background_subtracted_range.map(v=>v.toFixed(4)).join('–')} B / state 상주 B`,`이 범위는 별도 회귀 결과이며 위 실행의 직접 read/write 카운터가 아닙니다.`);}
 d.sources=[source('모델별 측정 조건·정의','assets/model_evidence.json'),source('구조·용량 입력','assets/numerical_evidence.json'),source('측정 설명','memory.html#numbers')];return d;
}
function val(values){return values===null?'미계측':b(sum(values));}
function node(s,x,y,w,h){
 const vals=s.values,total=sum(vals),isHBM=x===18,scale=Math.max(s.capacity,total,1);
 let out=`<rect class="sys-node" x="${x}" y="${y}" width="${w}" height="${h}" rx="10"/><text class="sys-title" x="${x+15}" y="${y+27}">${esc(s.title)}</text><text class="sys-number" x="${x+15}" y="${y+49}">${esc(s.unknown?'용량 '+b(s.capacity):b(total)+' / '+b(s.capacity))}</text>`;
 if(s.unknown){out+=`<rect x="${x+15}" y="${y+65}" width="${w-30}" height="22" rx="3" fill="url(#unknown-hatch)"/><text class="sys-text" x="${x+15}" y="${y+110}">객체별 상주량 미계측</text>`;}
 else{out+=`<rect x="${x+15}" y="${y+65}" width="${w-30}" height="22" rx="3" fill="#293846"/>`;let offset=0;for(const k of K){const width=(w-30)*vals[k]/scale;if(width){out+=`<rect x="${x+15+offset}" y="${y+65}" width="${width}" height="22" fill="${C[k]}"><title>${N[k]} ${b(vals[k])} · ${pct(100*vals[k]/scale)}%</title></rect>`;offset+=width;}}
 if(h>150){out+=`<text class="sys-text" x="${x+15}" y="${y+106}">${'색 비율 = 이 영역 용량 대비'}</text>`;K.forEach((k,i)=>{out+=`<circle cx="${x+19}" cy="${y+127+i*23}" r="4" fill="${C[k]}"/><text class="sys-text" x="${x+30}" y="${y+131+i*23}">${N[k]}</text><text class="sys-number" text-anchor="end" x="${x+w-13}" y="${y+131+i*23}">${esc(b(vals[k]))} · ${pct(100*vals[k]/scale)}%</text>`;});}
 else out+=`<text class="sys-text" x="${x+15}" y="${y+108}">${esc(K.filter(k=>vals[k]>0).map(k=>N[k]+' '+pct(vals[k]/scale*100)+'%').join(' · ')||'미배치')}</text>`;
 }
 if(isHBM){out+=`<rect x="${x+15}" y="${y+h-49}" width="${w-30}" height="4" fill="#293846"/><rect x="${x+15}" y="${y+h-49}" width="${(w-30)*Math.min(1,total/s.capacity)}" height="4" fill="#b5c5d3"/><text class="sys-text" x="${x+15}" y="${y+h-29}">장치 대비 ${(100*total/s.capacity).toFixed(2)}% · 나머지 미포함</text>`;}
 out+=`<text class="sys-text" x="${x+15}" y="${y+h-12}" font-size="10">${esc(s.foot)}</text>`;return out;
}
function map(d){
 const measured=['proxy','decode'].includes(d.type),s=settings();
 const routes=[['fetch',258,280,365,280],['writeback',365,379,258,379],['deliver',605,280,737,280],['store',737,363,605,363],['nearRead',605,97,837,223],['nearWrite',861,223,605,126]];
 let out=`<svg id="system-map" viewBox="0 0 960 490" role="img" aria-labelledby="system-map-title system-map-desc"><title id="system-map-title">${esc(d.title)} · 전체 메모리 지도</title><desc id="system-map-desc">${esc(d.explanation)}</desc><defs><pattern id="unknown-hatch" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#273442"/><path d="M0 8L8 0" stroke="#526577" stroke-width="2"/></pattern><marker id="sys-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L8 4L0 8Z" fill="context-stroke"/></marker></defs>`;
 for(const [key,x1,y1,x2,y2]of routes){const v=d.flows[key],known=v!==null,active=known&&sum(v)>0;
 if(!known||!active){const path=`M${x1} ${y1} L${x2} ${y2}`;out+=`<path d="${path}" class="sys-route sys-unknown" marker-end="url(#sys-arrow)" opacity="${known?.25:.7}"/>`;}
 if(active)K.forEach((k,i)=>{if(v[k]<=0)return;const off=(i-1)*7,path=key==='nearRead'?`M${x1} ${y1+off} Q837 ${y1+off} ${x2+off} ${y2}`:key==='nearWrite'?`M${x1+off} ${y1} Q861 ${y2+off} ${x2} ${y2+off}`:`M${x1} ${y1+off} L${x2} ${y2+off}`;out+=`<path d="${path}" class="sys-route" style="stroke:${C[k]}" marker-end="url(#sys-arrow)" ${['store','writeback','nearWrite'].includes(key)?'stroke-dasharray="5 4"':''}><title>${N[k]}: ${b(v[k])}</title></path>`;
 if(!measured){const bw=['fetch','writeback'].includes(key)?s.hbmTBps:key.startsWith('near')&&!d.partition?s.nearTBps:s.l2TBps,lat=['fetch','writeback'].includes(key)?s.hbmLatencyNs:key.startsWith('near')?(d.partition?s.l2LatencyNs:s.nearLatencyNs):0,dur=(lat+J.transferNs(16*J.MiB,bw))*.0005/Number($('speed').value);out+=`<circle r="3.5" fill="${C[k]}"><animateMotion dur="${dur}s" repeatCount="indefinite" path="${path}"/></circle>`;}});
 }
 out+=node(d.stores[0],18,194,240,276)+node(d.stores[1],365,194,240,276)+node(d.stores[2],365,15,240,133);
 out+=`<rect class="sys-node" x="737" y="223" width="205" height="200" rx="10"/><text class="sys-title" x="754" y="251">GPU compute</text><text class="sys-text" x="754" y="277">weight × 입력</text><text class="sys-text" x="754" y="299">KV 읽기 · 새 KV 쓰기</text><text class="sys-text" x="754" y="321">state 읽기 · 갱신</text><text class="sys-number" x="754" y="352">${esc(measured?'실행 시간은 아래 기록':d.type==='sim'?'요청 묶음':'한 스텝')}</text><text class="sys-text" x="754" y="386">${measured?'시간 실측 · 경로는 도식':'연산 시간은 별도'}</text>`;
 out+=`<text class="sys-text" x="310" y="251" text-anchor="middle">${measured?'물리 읽기':'HBM → L2 읽기'}</text><text class="sys-number" x="310" y="303" text-anchor="middle">${esc(val(d.flows.fetch))}</text><text class="sys-text" x="310" y="351" text-anchor="middle">HBM 되쓰기</text><text class="sys-number" x="310" y="402" text-anchor="middle">${esc(val(d.flows.writeback))}</text><text class="sys-text" x="670" y="249" text-anchor="middle">${measured?'논리 읽기 요청':'L2 → 연산부'}</text><text class="sys-number" x="670" y="303" text-anchor="middle">${esc(val(d.flows.deliver))}</text><text class="sys-text" x="670" y="343" text-anchor="middle">${measured?'논리 쓰기 요청':'연산부 → L2'}</text><text class="sys-number" x="670" y="392" text-anchor="middle">${esc(val(d.flows.store))}</text><text class="sys-text" x="684" y="62">${d.partition?'같은 L2의 보호 영역':'근접 읽기 + 쓰기'}</text><text class="sys-number" x="684" y="83">${esc(val(d.flows.near))}</text>`;
 if(d.partition)out+=`<path d="M484 148 L484 190" stroke="#687d8e" stroke-dasharray="3 3"/><text class="sys-text" x="505" y="177">두 영역 합 = ${b(J.L2_BYTES)}</text>`;
 return out+'</svg>';
}
function proofs(d){
 const measured=['proxy','decode'].includes(d.type),table=d.table?`<h4>원자료의 실행시간과 비교 결과</h4><table class="measured-table"><thead><tr><th>정책</th><th>중앙값 ms</th><th>짝지은 speedup</th></tr></thead><tbody>${d.table.map(r=>`<tr class="${r.selected?'selected':''}"><td>${r.name}</td><td>${r.time.toFixed(6)}</td><td>${r.speed.toFixed(4)}×</td></tr>`).join('')}</tbody></table>`:'';
 return `<details class="system-proof" open><summary>숫자가 나온 근거 · 수식 · 전제</summary><div class="proof-body"><div class="proof-chain"><span>${measured?'보존 원자료':'구조 / 예시 입력'}</span> → <span>${measured?'조건과 정의 확인':'용량·접근 순서 계산'}</span> → <span>${measured?'측정값 + 별도 설명 도식':'경로별 바이트·시간'}</span></div><p>${measured?'초록 실측 표시는 기록된 실행시간·설정·검증에만 적용합니다. 물리 HBM 바이트와 객체별 L2 상주량은 미계측으로 남깁니다.':'아래 식을 현재 입력으로 계산합니다. 시뮬레이션의 적중률·점유율·이동량을 B200 측정값으로 부르지 않습니다.'}</p><div class="source-links">${d.sources.map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)} ↗</a>`).join('')}</div>${table}<h4>입력 → 계산식 → 결과</h4><div class="proof-formula">${d.formula.map(esc).join('\n')}</div><h4>도식과 숫자를 읽는 전제</h4><ul><li>GB·TB/s는 10진수, MiB는 2²⁰ 바이트입니다. 원자료 정수 바이트를 우선합니다.</li><li>HBM의 색 면적과 얇은 용량 막대는 장치 대비 비율입니다. 나머지는 activation·workspace·예약량 등을 포함해 미모델링입니다. 실제 free가 아닙니다.</li><li>L2·근접 메모리 색 면적은 해당 영역 용량 대비입니다. 가정한 사본이 생겨도 HBM 원본을 빼지 않습니다. 빗금은 객체별 상주량을 모른다는 뜻입니다.</li><li>선의 바이트는 ${esc(d.unit)}의 합입니다. 읽기와 쓰기를 구분하며, HBM → L2와 L2 → 연산부는 서로 다른 링크입니다. 둘을 합쳐 HBM 트래픽으로 세지 않습니다.</li><li>${measured?'실측 사례의 선은 경로 설명용입니다. 시간 기록에서 패킷의 속도나 캐시 적중 순서를 만들지 않습니다.':'움직이는 점은 16 MiB 조각의 경로 속도 예시입니다. 경로마다 동일한 시간 확대율을 쓰며 선 굵기·점 개수는 전체 트래픽 규모를 나타내지 않습니다. 전체 요청 순서는 ‘한 요청 따라가기’에서 봅니다.'}</li><li>3D SRAM 직접 연결은 설계 가정입니다. 기존 B200 L2 보호 실험은 별도 물리 SRAM을 추가한 실험이 아닙니다.</li></ul><h4>속도 입력과 애니메이션</h4><div class="proof-formula">HBM ${$('hbm').value} TB/s, L2 ${$('l2-bandwidth').value} TB/s, 추가 SRAM ${$('near-bandwidth').value} TB/s (편집 가능한 가정)
전송 시간(ns) = 바이트 / [TB/s × 1000]
한 요청의 전체 지연 = lookup + 필요한 링크 전송 + 고정 지연
화면 시간 확대 = 500,000 / ${$('speed').value} (경로 간 공통)
${measured?'위 가정은 이 사례의 실측 시간에 대입하지 않습니다. 실측 사례에서는 이동 점을 재생하지 않습니다.':'지도 점은 링크별 전송과 해당 HBM/SRAM 고정 지연을 반영합니다. 요청 전체의 L2 확인 순서는 상세 화면에서 더합니다.'}</div></div></details>`;
}
function speedPanel(d){
 const s=settings(),measured=['proxy','decode'].includes(d.type);
 if(measured)return '<div class="system-speed"><h4>전체 시스템의 전송 속도</h4><p>이 기록에는 링크별 물리 바이트·대역폭이 없습니다. 위의 실행시간만 실측이며 HBM·L2 전송시간은 미계측입니다. 속도를 바꿔 보는 비교는 ‘모델 한 스텝’에서 할 수 있습니다.</p></div>';
 const specs=[['HBM ↔ L2',sum(d.flows.fetch)+sum(d.flows.writeback),s.hbmTBps],['L2 ↔ 연산부',sum(d.flows.deliver)+sum(d.flows.store),s.l2TBps],[d.partition?'보호 L2 ↔ 연산부':'3D SRAM ↔ 연산부',sum(d.flows.near),d.partition?s.l2TBps:s.nearTBps]];
 const times=specs.map(([,bytes,bw])=>J.transferNs(bytes,bw)),max=Math.max(...times,1);
 return `<div class="system-speed"><h4>전체 이동량이 지나가는 데 걸리는 시간 · ${esc(d.unit)}</h4><p>각 경로의 읽기+쓰기 합 ÷ 가정한 대역폭. 여러 경로를 동시에 비교합니다. 고정 지연·연산·전송 겹침을 제외한 링크 서비스 시간입니다.</p><div class="system-speed-grid">${specs.map(([name,bytes,bw],i)=>`<div><span>${name}</span><strong>${t(times[i])}</strong><small>${b(bytes)} ÷ ${bw} TB/s</small><div class="track"><div class="fill" style="background:${['#8297b1','#4bc0be','#d5a84f'][i]};width:${times[i]/max*100}%"></div></div></div>`).join('')}</div><p>막대는 같은 시간 눈금입니다. 한 스텝 실행시간은 이 세 시간을 단순히 더하거나 가장 긴 값만 고르는 것으로 확정되지 않습니다.</p></div>`;
}
function draw(d){
 current=d;const measured=['proxy','decode'].includes(d.type),routeSpecs=[['fetch','HBM → L2 · 읽기'],['writeback','L2 → HBM · 되쓰기'],['deliver',measured?'연산의 논리 읽기':'L2 → 연산부 · 읽기'],['store',measured?'연산의 논리 쓰기':'연산부 → L2 · 쓰기'],['near',d.partition?'보호 L2 서비스':'추가 SRAM 서비스']];
 $('system-content').innerHTML=`<div class="system-heading"><span class="basis-tag ${measured?'measured':''}">${esc(d.tag)}</span><h3>${esc(d.title)}</h3><p>${esc(d.desc)}</p></div><div class="system-facts">${d.facts.map(([n,v,f])=>`<div class="system-fact"><span>${esc(n)}</span><strong>${esc(v)}</strong><small>${esc(f)}</small></div>`).join('')}</div><div class="system-map-wrap">${map(d)}</div><div class="system-map-controls">${d.type==='sim'?`<button class="play" id="cache-phase">L2: ${cachePhase==='final'?'실행 후 → 실행 전 보기':'실행 전 → 실행 후 보기'}</button>`:''}${!measured?`<button class="play" id="map-play">${running?'Ⅱ 이동 표시 멈춤':'▶ 이동 표시 재생'}</button>`:''}<span>${esc(d.unit)} 합계 · 지도는 동시 경로 요약</span>${d.type==='sim'?'<button class="system-detail-link" id="open-detail">이 상황을 한 요청씩 따라가기 →</button>':''}</div><div class="system-legend">${K.map(k=>`<span><i style="background:${C[k]}"></i>${N[k]}</span>`).join('')}<span>실선: 읽기 / 점선: 쓰기 또는 미계측 경로</span><span>빗금: 점유 미계측</span></div>${d.warnings?`<div class="sys-alert">${esc(d.warnings)}</div>`:''}${speedPanel(d)}<div class="system-transfers">${routeSpecs.map(([k,n])=>`<article class="transfer-card"><h4>${esc(n)}</h4><strong>${esc(val(d.flows[k]))}</strong><div class="transfer-parts">${d.flows[k]?K.map(a=>`<span style="color:${C[a]}">${N[a]} ${b(d.flows[k][a])}</span>`).join(''):'물리 바이트를 측정한 카운터 없음'}</div><p>${d.flows[k]===null?'기록된 실행시간으로 대체하거나 역산하지 않습니다.':measured?'논리 접근량 · 실제 링크 전송량 아님':'가정과 요청 순서에서 계산'}</p></article>`).join('')}</div><p class="system-description">${esc(d.explanation)}</p>${proofs(d)}`;
 $('cache-phase')?.addEventListener('click',()=>{cachePhase=cachePhase==='final'?'initial':'final';refresh();});
 $('map-play')?.addEventListener('click',()=>{running=!running;setAnimation();$('map-play').textContent=running?'Ⅱ 이동 표시 멈춤':'▶ 이동 표시 재생';});
 $('open-detail')?.addEventListener('click',()=>{$('journey-pattern').value=cases[selected].pattern;$('journey-tile').value='16';window.journeyApp.reset({primaryKind:current.r.config.primaryKind,otherKinds:K});setView('journey');});
 setAnimation();
}
function setAnimation(){const svg=$('system-map');if(!svg)return;if(running&&view==='system')svg.unpauseAnimations();else svg.pauseAnimations();}
function refresh(){
 document.querySelectorAll('[data-case]').forEach(el=>el.setAttribute('aria-pressed',el.dataset.case===selected?'true':'false'));
 if(controlNote)controlNote.textContent=['proxy','decode'].includes(cases[selected].kind)?'현재는 고정된 실측 조건입니다. 모델·용량을 바꾸면 ‘모델 한 스텝’ 가정 계산으로 전환합니다.':cases[selected].kind==='sim'?'예시 데이터는 16 MiB 조각입니다. 위 용량·속도 입력을 공유하며, 모델 크기와는 별개입니다.':'모델·배치·문맥·정책을 바꾸면 전체 지도가 함께 바뀝니다.';
 const kind=cases[selected].kind;
 if((kind==='proxy'&&!evidence.sweep)||(kind==='decode'&&!evidence.models)){$('system-content').innerHTML=`<p class="system-empty">${esc(loadError||'보존 원자료를 불러오는 중입니다…')}</p>`;return;}
 try{draw(kind==='model'?modelData():kind==='sim'?simData():kind==='proxy'?proxyData():decodeData());}catch(error){$('system-content').innerHTML='<p class="system-empty">이 조건의 원자료를 읽지 못했습니다. 수치를 임의로 채우지 않았습니다.</p>';console.error(error);}
}
function setView(next){view=next;$('system-panel').hidden=next!=='system';$('journey-panel').hidden=next!=='journey';for(const key of ['system','journey']){$('view-'+key).setAttribute('aria-pressed',next===key?'true':'false');$('view-'+key).classList.toggle('active',next===key);}if(window.journeyApp.setVisible)window.journeyApp.setVisible(next==='journey');setAnimation();}
function select(key){
 selected=key;cachePhase='final';const c=cases[key];
 if(c.kind==='decode'){$('model').value=c.model;$('batch').value=batches.indexOf(8);$('context').value=contexts.indexOf(2048);$('capacity').value=0;$('mode').value='added';scenario='';render();}
 else if(c.kind==='proxy'){$('model').value='proxy';$('batch').value=0;$('context').value=contexts.indexOf(c.size*1024);$('capacity').value=caps.indexOf(128);$('mode').value='partition';$('policy').value='state';scenario='';render();}
 else refresh();
 document.querySelectorAll('.preset').forEach(el=>el.classList.toggle('active',el.dataset.s===scenario));setView('system');
}
$('view-system').addEventListener('click',()=>setView('system'));$('view-journey').addEventListener('click',()=>setView('journey'));
$('speed').addEventListener('change',refresh);
window.overviewApp={refresh,useModel(){selected='model';},conditionChanged(id){if(cases[selected].kind==='sim'&&['hbm','capacity','mode'].includes(id))return;selected='model';}};
setView('system');refresh();
(async()=>{try{const urls={sweep:'assets/placement_sweep_summary.json',models:'assets/model_evidence.json',raw64:'assets/experiments/placement_sweep_20260916/placement_m64_l36.jsonl',raw256:'assets/experiments/placement_sweep_20260916/placement_m256_l36.jsonl'};const entries=await Promise.all(Object.entries(urls).map(async([key,url])=>{const response=await fetch(url);if(!response.ok)throw Error('Evidence unavailable');const text=await response.text();return[key,key.startsWith('raw')?text.trim().split('\n').map(s=>JSON.parse(s)):JSON.parse(text)];}));evidence=Object.fromEntries(entries);if(['proxy','decode'].includes(cases[selected].kind))refresh();}catch(error){loadError='원자료를 불러오지 못했습니다. 새로고침 후 다시 선택해 주세요. 실측 수치를 임의로 채우지 않았습니다.';if(['proxy','decode'].includes(cases[selected].kind))refresh();}})();
})();
