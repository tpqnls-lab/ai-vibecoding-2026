window.refreshRecommendations=refreshRecommendations;const symbolNames={};const stockName=s=>symbolNames[s]||stocks.find(v=>v.symbol===s)?.name||s;async function loadNames(symbols){if(!symbols.length)return;try{const r=await fetch('/api/v1/stock-names?symbols='+symbols.join(','),{cache:'no-store'});Object.assign(symbolNames,await r.json())}catch(e){}} const pnlWon=n=>{const v=Number(n||0);return v>0?`+${won(v)}`:won(v)};const $=s=>document.querySelector(s),won=n=>new Intl.NumberFormat('ko-KR',{style:'currency',currency:'KRW',maximumFractionDigits:0}).format(Number(n||0));
const sectors={'454910':'로봇·자동화','028050':'플랜트·건설','012330':'자동차·부품','000810':'금융·보험','096770':'배터리·에너지'};const seenSymbols=new Set();const stocks=[{symbol:'454910',name:'두산로보틱스',price:69600,change:3.42},{symbol:'028050',name:'삼성E&A',price:49900,change:2.18},{symbol:'012330',name:'현대모비스',price:372500,change:1.76},{symbol:'000810',name:'삼성화재',price:660000,change:1.24},{symbol:'096770',name:'SK이노베이션',price:158300,change:.86}];let selected=stocks[0],side='BUY';
window.stocks=stocks;
function cards(){ $('#cards').innerHTML=stocks.map((s,i)=>`<article class="stock-card ${s===selected?'selected':''}" data-s="${s.symbol}"><span class="rank">#${i+1} · ${72+i*4}점</span><h3>${s.name}</h3><small class="sector">${s.sector||sectors[s.symbol]||'시장 랭킹 기반'}</small><span class="symbol">${s.symbol}</span><div class="price">${won(s.price)}</div><div class="change" style="color:${s.change>=0?"#ef3340":"#2563eb"}">전일 대비 ${s.change.toFixed(2)}%</div></article>`).join('');document.querySelectorAll('.stock-card').forEach(x=>x.onclick=()=>select(stocks.find(s=>s.symbol===x.dataset.s)))}
function select(s){selected=s;$('#workspace').classList.remove('hidden');$('#detail-name').textContent=s.name;$('#detail-symbol').textContent=s.symbol;$('#detail-price').textContent=won(s.price);$('#detail-change').textContent=`+${s.change.toFixed(2)}%`;cards();total()}
function portfolio(p){const hs=p.holdings||[];$('#cash').textContent=won(p.cash);$('#positions').textContent=`${hs.length}개` ;$('#pnl').textContent=`평가 손익 ${won(hs.reduce((v,h)=>v+Number(h.pnl||0),0))} · 실현 ${won(p.realized_pnl)}`;$('#holdings-list').innerHTML=hs.length?`<div class="holding-summary"><div><small>총 체결금액</small><b>${won(p.total_invested)}</b></div><div><small>총 자산금액(현금+평가)</small><b>${won(p.total_assets)}</b></div><div><small>실시간 평가금액</small><b>${won(p.total_market_value)}</b></div><div><small>전체 손익</small><b class="${Number(p.total_pnl)>=0?'profit':'loss'}">${pnlWon(p.total_pnl)} (${Number(p.total_pnl_percent).toFixed(2)}%)</b></div></div><div class="holding-head"><span>종목</span><span>수량</span><span>평균가</span><span>현재가(1주)</span><span>총 체결금액</span><span>실시간 현재금액</span><span>손익</span></div>`+hs.map(h=>`<div class="holding-row"><b>${stockName(h.symbol)}<small class="holding-symbol">${h.symbol}</small></b><span>${h.quantity}주</span><span>${won(h.average_price)}</span><span>${won(h.current_price)}</span><span>${won(h.invested_value)}</span><span>${won(h.market_value)}</span><span class="${Number(h.pnl)>=0?'profit':'loss'}">${pnlWon(h.pnl)} (${Number(h.pnl_percent).toFixed(2)}%)</span></div>`).join(''):'보유한 종목이 없습니다.'}
async function refreshRecommendations(exclude=''){try{const allExclude=new Set((exclude?exclude.split(','):[]).concat([...seenSymbols]));const r=await fetch('/api/v1/recommendations?exclude='+encodeURIComponent([...allExclude].join(','))+'&ts='+Date.now(),{cache:'no-store'});const next=await r.json();if(Array.isArray(next)&&next.length){next.forEach(x=>seenSymbols.add(x.symbol));stocks.splice(0,stocks.length,...next);selected=stocks[0];select(selected)}else{seenSymbols.clear()}}catch(e){console.warn('추천목록 갱신 실패',e)}}
function total(){$('#order-total').textContent=won(selected.price*Number($('#quantity').value||0))}
async function refresh(){const[p,r]=await Promise.all([fetch('/api/v1/portfolio'),fetch('/api/v1/orders')]);let pd=null,os=[];if(p.ok){pd=await p.json();await loadNames((pd.holdings||[]).map(h=>h.symbol));portfolio(pd)}if(r.ok){os=await r.json();await loadNames(os.map(o=>o.symbol));$('#orders-list').innerHTML=os.length?os.slice().reverse().map(o=>`<div class="order-row"><span>${o.created_at?new Date(o.created_at).toLocaleString('ko-KR'):'기록 없음'}</span><span><b class="${o.side==='BUY'?'buy-text':'sell-text'}">${o.side==='BUY'?'매수':'매도'}</b><br>${stockName(o.symbol)}<small class="holding-symbol">${o.symbol}</small></span><span>${o.quantity}주 × ${won(o.price)}</span><span>${o.status==='FILLED'?'체결':'거부'}</span></div>`).join(''):'아직 주문 내역이 없습니다.'}}
function connect(){const ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/market`);ws.onmessage=e=>{const data=JSON.parse(e.data);portfolio(data.portfolio);(data.prices||[]).forEach(q=>{const s=stocks.find(x=>x.symbol===q.symbol);if(s){s.price=Number(q.price);if(q.change_percent!==undefined&&q.change_percent!==null&&(Number(q.change_percent)!==0||s.change===0))s.change=Number(q.change_percent)}});cards();select(selected)};ws.onclose=()=>setTimeout(connect,1500)}
document.addEventListener('DOMContentLoaded',()=>{cards();select(selected);$('#quantity').oninput=total;document.querySelectorAll('.order-tabs button').forEach(b=>b.onclick=()=>{side=b.dataset.side;document.querySelectorAll('.order-tabs button').forEach(x=>x.classList.remove('active','buy'));b.classList.add('active');if(side==='BUY')b.classList.add('buy');$('#order-btn').textContent=side==='BUY'?'매수하기':'매도하기'});$('#order-btn').onclick=async()=>{const r=await fetch('/api/v1/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:selected.symbol,side,quantity:Number($('#quantity').value),price:selected.price})});$('#order-message').textContent=r.ok?'주문이 체결되었습니다.':'주문이 거부되었습니다.';await refresh()};const rb=document.querySelector('#refresh-recommendations');if(rb)rb.onclick=()=>refreshRecommendations(stocks.map(x=>x.symbol).join(','));connect();refresh();refreshRecommendations();setInterval(refreshRecommendations,300000)});


























document.addEventListener('click',e=>{if(e.target&&e.target.id==='refresh-recommendations'){e.preventDefault();refreshRecommendations(stocks.map(x=>x.symbol).join(','))}});




