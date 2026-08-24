// anchor-view — 锚点视图模式客户端插件（prototype skill 对齐脚手架）。
// 接入：经服务打开 /proto?abs=<绝对路径> 自动注入（源码零改动）；或页面
// </body> 前一行 <script src="http://127.0.0.1:8420/__am_client.js"></script>。
// 卸载：删 script 行即净（经 /proto 打开无需删）；服务未起时静默无影响。
// 术语三级回退：window.AM_TERMS 预置 → 服务 /__am_terms（项目 domains 表）→ DOM 现查。
// 零依赖；全部 UI 元素带 .am-ui，页面交互在开启模式下冻结，Esc 退出。
(function () {
'use strict';
if (window.__AM_VIEW__) return;
window.__AM_VIEW__ = 1;

const css = `
  .am-fab{position:fixed;right:18px;bottom:18px;z-index:10003;background:var(--bg3,#262635);color:var(--fg2,#c9c9d6);border:1px solid var(--bg4,#3b3b4d);border-radius:20px;padding:9px 15px;cursor:pointer;font-size:13px;box-shadow:0 4px 16px rgba(0,0,0,.4)}
  .am-fab.cur{background:var(--accent,#6d5dfc);color:#fff;border-color:var(--accent,#6d5dfc)}
  .am-switch{position:fixed;right:18px;bottom:62px;z-index:10003;display:none;align-items:center;gap:4px;background:var(--bg3,#262635);border:1px solid var(--bg4,#3b3b4d);border-radius:10px;padding:4px}
  .am-switch.on{display:flex}
  .am-switch button{background:transparent;color:var(--fg2,#c9c9d6);border:none;padding:5px 10px;border-radius:7px;cursor:pointer;font-size:12px}
  .am-switch button.cur{background:var(--accent,#6d5dfc);color:#fff}
  .am-switch span{color:var(--fg3,#8b8b9a);font-size:11px;padding:0 6px}
  .am-tag{position:fixed;z-index:10000;color:#fff;font-size:11px;line-height:1.6;padding:1px 8px;border-radius:0 0 8px 0;cursor:pointer;white-space:nowrap}
  .am-bar{position:fixed;z-index:10000;height:18px;color:#fff;font-size:11px;line-height:18px;padding:0 8px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .am-panel{position:fixed;top:0;right:0;bottom:0;width:300px;z-index:10002;background:var(--bg2,#1f1f2a);color:var(--fg,#e8e8f0);border-left:1px solid var(--bg4,#3b3b4d);padding:14px;overflow:auto}
  .am-panel h3{font-size:13px;margin-bottom:4px}
  .am-panel .am-note{font-size:11px;color:var(--fg3,#8b8b9a);margin-bottom:10px;line-height:1.5}
  .am-row{padding:8px 10px;border:1px solid var(--bg4,#3b3b4d);border-radius:9px;margin-bottom:6px;cursor:pointer}
  .am-row:hover{border-color:var(--accent,#6d5dfc)}
  .am-row b{font-size:12px}
  .am-row code{font-size:11px;color:var(--accent2,#a390ff);margin-left:6px}
  .am-row .st{float:right;font-size:11px;color:var(--green,#22c55e)}
  .am-row .st.pend{color:var(--amber,#f59e0b)}
  .am-row .st.miss{color:var(--red,#ef4444)}
  .am-row p{font-size:11px;color:var(--fg3,#8b8b9a);margin-top:3px;line-height:1.5}
  .am-btn{width:100%;margin-top:6px;background:var(--accent,#6d5dfc);color:#fff;border:none;border-radius:9px;padding:8px;cursor:pointer;font-size:12px}
  .am-btn.ghost{background:var(--bg4,#3b3b4d);color:var(--fg2,#c9c9d6)}
  .am-card{position:fixed;z-index:10004;background:var(--bg3,#262635);color:var(--fg,#e8e8f0);border:1px solid var(--bg4,#3b3b4d);border-radius:12px;padding:14px;width:290px;box-shadow:0 8px 30px rgba(0,0,0,.5);font-size:12px}
  .am-card h4{font-size:13px;margin-bottom:8px}
  .am-card .kv{color:var(--fg2,#c9c9d6);line-height:1.8;word-break:break-all}
  .am-card .kv code{color:var(--accent2,#a390ff)}
  .am-card input{width:100%;margin:4px 0 8px;background:var(--bg,#17171f);border:1px solid var(--bg4,#3b3b4d);border-radius:7px;color:var(--fg,#e8e8f0);padding:6px 8px;font-size:12px}
  .am-card .ops{display:flex;gap:6px;margin-top:6px}
  .am-card .ops button{flex:1;background:var(--accent,#6d5dfc);color:#fff;border:none;border-radius:7px;padding:6px;cursor:pointer;font-size:12px}
  .am-card .ops button.ghost{background:var(--bg4,#3b3b4d);color:var(--fg2,#c9c9d6)}
  .am-flash{animation:amFlash .7s ease 3}
  @keyframes amFlash{0%,100%{outline-color:var(--accent,#6d5dfc)}50%{outline-color:#fff}}
  .am-toast{position:fixed;bottom:70px;left:50%;transform:translateX(-50%);background:var(--bg3,#262635);color:var(--fg,#e8e8f0);border:1px solid var(--bg4,#3b3b4d);padding:8px 16px;border-radius:10px;z-index:10005;font-size:12px;box-shadow:0 4px 16px rgba(0,0,0,.4)}
  body.am-picking *{cursor:crosshair !important}
  .am-gbar{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);z-index:10004;background:var(--bg3,#262635);color:var(--fg,#e8e8f0);border:1px solid var(--bg4,#3b3b4d);border-radius:12px;padding:8px 14px;display:flex;gap:8px;align-items:center;font-size:12px;box-shadow:0 4px 16px rgba(0,0,0,.4)}
  .am-gbar b{color:var(--amber,#f59e0b)}
  .am-gbar button{background:var(--accent,#6d5dfc);color:#fff;border:none;border-radius:7px;padding:6px 12px;cursor:pointer;font-size:12px}
  .am-gbar button.ghost{background:var(--bg4,#3b3b4d);color:var(--fg2,#c9c9d6)}
  .am-gsel{outline:2px dashed var(--amber,#f59e0b) !important;outline-offset:2px}
  .am-del{float:right;font-size:11px;color:var(--fg3,#8b8b9a);cursor:pointer;margin-left:8px;padding:1px 6px;border:1px solid var(--bg4,#3b3b4d);border-radius:6px}
  .am-del:hover{color:var(--red,#ef4444);border-color:var(--red,#ef4444)}
  .am-del.arm{color:var(--red,#ef4444);border-color:var(--red,#ef4444)}
`;
const styleEl = document.createElement('style');
styleEl.textContent = css;
document.head.appendChild(styleEl);

const AM = { on:false, variant:'a', picking:false, groupPicking:false, groupSel:[], pending:[], els:[], solo:new Set(), colors:['#6d5dfc','#3b82f6','#22c55e','#f59e0b'] };
let AM_TERMS = Array.isArray(window.AM_TERMS) ? window.AM_TERMS.slice() : [];
function amTermOf(a){ const t=AM_TERMS.find(t=>t.anchor===a); return t?t.term:null; }
function amAnchored(){ return [...document.querySelectorAll('[data-term-anchor]')]; }
function amChain(el){ const c=[]; let p=el.parentElement; while(p){ if(p.hasAttribute&&p.hasAttribute('data-term-anchor'))c.push(p.getAttribute('data-term-anchor')); p=p.parentElement; } return c.reverse(); }
function amSig(el){
  let s='<'+el.tagName.toLowerCase();
  if(el.id) s+=' id="'+el.id+'"';
  const cls=(typeof el.className==='string')?el.className.trim().split(/\s+/).slice(0,3).join(' '):'';
  if(cls) s+=' class="'+cls+'"';
  return s+'>';
}
function amClearOverlays(){
  AM.els.forEach(o=>o.remove()); AM.els=[];
  document.querySelectorAll('.am-flash').forEach(e=>e.classList.remove('am-flash'));
  document.querySelectorAll('.am-gsel').forEach(e=>e.classList.remove('am-gsel'));
  amAnchored().forEach(e=>{ e.style.outline=''; e.style.outlineOffset=''; });
}
function amTagEl(el){
  const a=el.getAttribute('data-term-anchor');
  el.style.outline='2px solid #6d5dfc'; el.style.outlineOffset='-2px';
  const o=document.createElement('div');
  o.className='am-tag am-ui'; o.style.background='#6d5dfc';
  o.textContent=(amTermOf(a)||a)+' · '+a;
  o.onclick=(ev)=>{ ev.stopPropagation(); amInfo(el); };
  o._for=el; o._solo=a;
  document.body.appendChild(o); AM.els.push(o);
}
function amSolo(el){
  const a=el.getAttribute('data-term-anchor');
  if(AM.solo.has(a)){
    AM.els.filter(o=>o._solo===a).forEach(o=>o.remove());
    AM.els=AM.els.filter(o=>o._solo!==a);
    AM.solo.delete(a);
    el.style.outline=''; el.style.outlineOffset='';
    return;
  }
  AM.solo.add(a); amTagEl(el); amSync();
}
function amBuild(){
  amClearOverlays();
  if(AM.variant==='c'){
    amAnchored().forEach(el=>{
      const a=el.getAttribute('data-term-anchor');
      const col=AM.colors[amChain(el).length%AM.colors.length];
      el.style.outline='2px solid '+col; el.style.outlineOffset='-2px';
      const o=document.createElement('div');
      o.className='am-bar am-ui'; o.style.background=col;
      o.textContent=[...amChain(el).map(x=>amTermOf(x)||x), amTermOf(a)||a].join(' › ');
      o.onclick=(ev)=>{ ev.stopPropagation(); amInfo(el); };
      o._for=el;
      document.body.appendChild(o); AM.els.push(o);
    });
    return;
  }
  const shown=AM.variant==='a'?amAnchored():amAnchored().filter(el=>AM.solo.has(el.getAttribute('data-term-anchor')));
  shown.forEach(amTagEl);
  if(AM.variant==='a')return;
    const p=document.createElement('div'); p.className='am-panel am-ui';
    let rows='';
    AM_TERMS.forEach(t=>{
      const el=document.querySelector('[data-term-anchor="'+t.anchor+'"]');
      const st=t.pend?'<span class="st pend">未落盘</span>':(el?'<span class="st">✓ 已锚定</span>':'<span class="st miss">✗ 缺失</span>');
      rows+='<div class="am-row" data-a="'+t.anchor+'"><b>'+(t.term||t.anchor)+'</b><code>'+t.anchor+'</code><span class="am-del">删除锚点</span>'+st+'<p>'+t.def+'</p></div>';
    });
    p.innerHTML='<h3>锚点清单</h3><div class="am-note">点击条目显示/隐藏该锚点的标签（可多个并存）；A 覆盖标签=显示全部，切到本清单后保持并可逐个关闭。锚点模式下页面交互冻结，Esc 退出。'+(AM.saveUrl!==null?'已连接锚点服务，保存即写盘。':'未检测到锚点服务（npx prototype-anchor serve），保存仅会话内生效。')+'</div>'+rows+
      '<button class="am-btn" id="am-add">＋ 添加锚点（点选页面元素）</button>'+
      '<button class="am-btn" id="am-gadd" style="background:var(--amber,#f59e0b)">＋ 添加分组（点选多个元素）</button>'+
      '<button class="am-btn ghost" id="am-export">复制新增片段（'+AM.pending.length+'）</button>';
    document.body.appendChild(p); AM.els.push(p);
    p.querySelectorAll('.am-row').forEach(row=>{
      row.onclick=()=>{
        const el=document.querySelector('[data-term-anchor="'+row.dataset.a+'"]');
        if(!el)return;
        if(!AM.solo.has(row.dataset.a)){
          el.scrollIntoView({block:'center',behavior:'smooth'});
          el.classList.remove('am-flash'); void el.offsetWidth; el.classList.add('am-flash');
        }
        amSolo(el);
      };
      row.querySelector('.am-del').onclick=(ev)=>{
        ev.stopPropagation();
        const el=document.querySelector('[data-term-anchor="'+row.dataset.a+'"]');
        if(!el){ amToast('元素不存在，无需删除'); return; }
        amDeleteAnchor(el,ev.target);
      };
    });
    p.querySelector('#am-add').onclick=()=>{ AM.picking=true; document.body.classList.add('am-picking'); };
    p.querySelector('#am-gadd').onclick=()=>{ AM.groupPicking=true; AM.groupSel=[]; document.body.classList.add('am-picking'); amGroupBar(); };
    p.querySelector('#am-export').onclick=amExport;
}
function amSync(){
  if(!AM.on)return;
  AM.els.forEach(o=>{
    if(!o._for)return;
    const r=o._for.getBoundingClientRect();
    o.style.left=r.left+'px'; o.style.top=r.top+'px';
    if(o.classList.contains('am-bar'))o.style.width=Math.min(r.width,420)+'px';
    o.style.display=(r.width===0||r.bottom<0||r.top>innerHeight)?'none':'';
  });
}
document.addEventListener('scroll',amSync,true);
window.addEventListener('resize',amSync);
function amCloseCard(){ const c=document.getElementById('am-card'); if(c)c.remove(); }
function amInfo(el){
  amCloseCard();
  const a=el.hasAttribute('data-term-anchor')?el.getAttribute('data-term-anchor'):null;
  const t=a?AM_TERMS.find(x=>x.anchor===a):null;
  const chain=amChain(el).map(x=>amTermOf(x)||x);
  const r=el.getBoundingClientRect();
  const card=document.createElement('div'); card.className='am-card am-ui'; card.id='am-card';
  card.style.left=Math.max(8,Math.min(r.left,innerWidth-310))+'px';
  card.style.top=Math.max(8,Math.min(r.bottom+8,innerHeight-280))+'px';
  let html='<h4>'+(t?t.term:'未命名元素')+(a?' <code style="color:var(--accent2,#a390ff)">'+a+'</code>':'')+'</h4>';
  html+='<div class="kv">DOM：<code>'+amSig(el)+'</code></div>';
  if(t)html+='<div class="kv">定义：'+t.def+'</div>';
  if(chain.length)html+='<div class="kv">嵌套于：'+chain.join(' › ')+'</div>';
  if(a){
    html+='<div class="ops"><button class="ghost" id="am-c-del">'+(amIsGroupBox(el)?'删除并拆盒':'删除锚点')+'</button><button class="ghost" id="am-c-close">关闭</button></div>';
  }else{
    html+='<div class="kv" style="margin-top:6px">添加锚点：</div>';
    html+='<input id="am-in-term" placeholder="术语名（可空，沉淀时 agent 推荐）">';
    html+='<input id="am-in-anchor" placeholder="锚点值（kebab，如：msg-list）">';
    html+='<input id="am-in-def" placeholder="一句话定义（可空，随新增片段导出）">';
    html+='<div class="ops"><button id="am-c-ok">保存</button><button class="ghost" id="am-c-close">取消</button></div>';
  }
  card.innerHTML=html;
  document.body.appendChild(card);
  card.querySelector('#am-c-close').onclick=amCloseCard;
  const del=card.querySelector('#am-c-del');
  if(del)del.onclick=()=>amDeleteAnchor(el,del);
  const ok=card.querySelector('#am-c-ok');
  if(ok)ok.onclick=()=>{
    const term=card.querySelector('#am-in-term').value.trim();
    const anchor=card.querySelector('#am-in-anchor').value.trim();
    const def=card.querySelector('#am-in-def').value.trim();
    if(!anchor){ amToast('锚点值必填'); card.querySelector('#am-in-anchor').focus(); return; }
    amCloseCard();
    amSave(term,anchor,def,el);
  };
}
function amExport(){
  const btn=document.getElementById('am-export');
  if(!AM.pending.length){ if(btn)btn.textContent='暂无新增'; return; }
  const lines=['锚点新增清单（交给 agent，由 prototype-anchor-sync 沉淀进术语表）：',''];
  AM.pending.forEach((pd,i)=>{
    lines.push((i+1)+'. '+(pd.term||'（待命名）')+' → data-term-anchor="'+pd.anchor+'"');
    if(pd.def)lines.push('   定义：'+pd.def);
    lines.push('   grep 定位：'+pd.sig);
  });
  navigator.clipboard.writeText(lines.join('\n'));
  if(btn)btn.textContent='已复制 ✓';
}
function amToast(msg){
  const t=document.createElement('div'); t.className='am-toast am-ui'; t.textContent=msg;
  document.body.appendChild(t); setTimeout(()=>t.remove(),Math.min(9000,2400+msg.length*90));
}
function amPath(el){
  const segs=[];
  while(el&&el.tagName){
    const tag=el.tagName.toLowerCase();
    let i=0,s=el;
    while((s=s.previousElementSibling))if(s.tagName===el.tagName)i++;
    segs.unshift(tag+':'+i);
    if(el===document.documentElement)break;
    el=el.parentElement;
  }
  return segs.join('/');
}
function amSave(term,anchor,def,el){
  const sig=amSig(el);
  el.setAttribute('data-term-anchor',anchor);
  const entry={term,anchor,def:def||'（会话内新增，待沉淀术语表）',pend:true};
  AM_TERMS.push(entry);
  AM.pending.push({term,anchor,def,sig});
  if(AM.saveUrl===null){ amToast('会话内生效（未落盘）— npx prototype-anchor serve 启动后保存即写盘'); amBuild(); amSync(); return; }
  fetch(AM.saveUrl+'/__am_save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({file:AM.file,path:amPath(el),anchor,term,def})})
  .then(r=>r.json()).then(res=>{
    if(res.ok){ entry.pend=false; if(def)entry.def=def; amToast('锚点已写盘：'+sig); }
    else amToast('服务拒绝：'+(res.error||'未知错误'));
    amBuild(); amSync();
  }).catch(()=>{ AM.saveUrl=null; amToast('写入失败，转为未落盘'); amBuild(); amSync(); });
}
function amIsGroupBox(el){ return el.tagName==='DIV' && el.attributes.length===1 && el.hasAttribute('data-term-anchor'); }
function amDeleteAnchor(el,btn){
  if(!btn.dataset.arm){ btn.dataset.arm='1'; btn.classList.add('arm'); btn.textContent='确认删除？'; return; }
  const anchor=el.getAttribute('data-term-anchor');
  AM.solo.delete(anchor);
  const unwrap=amIsGroupBox(el);
  const path=amPath(el);
  if(unwrap){
    const p=el.parentElement;
    while(el.firstChild)p.insertBefore(el.firstChild,el);
    p.removeChild(el);
  }else el.removeAttribute('data-term-anchor');
  amCloseCard();
  if(AM.saveUrl===null){ amToast('会话内生效（未落盘）— 启动锚点服务后删除即写盘'); amBuild(); amSync(); return; }
  fetch(AM.saveUrl+'/__am_delete',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({file:AM.file,path,unwrap})})
  .then(r=>r.json()).then(res=>{
    amToast(res.ok?('已删除锚点：'+anchor+(unwrap?'（盒已拆除）':'')):('服务拒绝：'+(res.error||'未知错误')));
    amBuild(); amSync();
  }).catch(()=>{ AM.saveUrl=null; amToast('写入失败，删除仅会话内生效'); amBuild(); amSync(); });
}
function amGroupBar(){
  const old=document.getElementById('am-gbar'); if(old)old.remove();
  const bar=document.createElement('div'); bar.id='am-gbar'; bar.className='am-gbar am-ui';
  bar.innerHTML='分组：已选 <b id="am-gcnt">0</b> 个元素（须同父相邻）<button id="am-gdone">完成</button><button class="ghost" id="am-gcancel">取消</button>';
  document.body.appendChild(bar);
  bar.querySelector('#am-gdone').onclick=amGroupCard;
  bar.querySelector('#am-gcancel').onclick=amGroupCancel;
}
function amGroupCancel(){
  AM.groupPicking=false; AM.groupSel=[];
  document.body.classList.remove('am-picking');
  const bar=document.getElementById('am-gbar'); if(bar)bar.remove();
  document.querySelectorAll('.am-gsel').forEach(e=>e.classList.remove('am-gsel'));
}
function amGroupToggle(el){
  const i=AM.groupSel.indexOf(el);
  if(i>=0){ AM.groupSel.splice(i,1); el.classList.remove('am-gsel'); }
  else{ AM.groupSel.push(el); el.classList.add('am-gsel'); }
  const c=document.getElementById('am-gcnt'); if(c)c.textContent=AM.groupSel.length;
}
function amGroupCard(){
  if(!AM.groupSel.length){ amToast('请先点选要归组的元素'); return; }
  const els=AM.groupSel.slice();
  amGroupCancel(); amCloseCard();
  const card=document.createElement('div'); card.className='am-card am-ui'; card.id='am-card';
  card.style.left=Math.max(8,innerWidth/2-145)+'px';
  card.style.top='80px';
  card.innerHTML='<h4>添加分组 <code style="color:var(--amber,#f59e0b)">'+els.length+' 个成员</code></h4>'
    +'<input id="am-in-term" placeholder="组名（可空，沉淀时 agent 推荐）">'
    +'<input id="am-in-anchor" placeholder="锚点值（kebab，如：session-ops）">'
    +'<input id="am-in-def" placeholder="一句话定义（可空，随新增片段导出）">'
    +'<div class="ops"><button id="am-c-ok">保存</button><button class="ghost" id="am-c-close">取消</button></div>';
  document.body.appendChild(card);
  card.querySelector('#am-c-close').onclick=amCloseCard;
  card.querySelector('#am-c-ok').onclick=()=>{
    const term=card.querySelector('#am-in-term').value.trim();
    const anchor=card.querySelector('#am-in-anchor').value.trim();
    const def=card.querySelector('#am-in-def').value.trim();
    if(!anchor){ amToast('锚点值必填'); card.querySelector('#am-in-anchor').focus(); return; }
    amCloseCard();
    amSaveGroup(term,anchor,def,els);
  };
}
function amGroupWrapable(els){
  const p=els[0]&&els[0].parentElement;
  if(!p)return false;
  for(const el of els) if(el.parentElement!==p)return false;
  const kids=[...p.children];
  const idx=els.map(el=>kids.indexOf(el)).sort((a,b)=>a-b);
  for(let i=1;i<idx.length;i++) if(idx[i]!==idx[0]+i)return false;
  return true;
}
function amSaveGroup(term,anchor,def,els){
  if(!amGroupWrapable(els)){ amToast('所选元素不是同一父级下的相邻兄弟，无法包盒'); return; }
  const paths=els.map(amPath);
  const box=document.createElement('div');
  box.setAttribute('data-term-anchor',anchor);
  els[0].parentElement.insertBefore(box,els[0]);
  els.forEach(el=>box.appendChild(el));
  const entry={term,anchor,def:def||'（会话内新增分组，待沉淀术语表）',pend:true};
  AM_TERMS.push(entry);
  const sig='box × '+els.length+'（'+amSig(els[0])+' 等）';
  AM.pending.push({term,anchor,def,sig});
  if(AM.saveUrl===null){ amToast('会话内生效（未落盘）— npx prototype-anchor serve 启动后保存即写盘'); amBuild(); amSync(); return; }
  fetch(AM.saveUrl+'/__am_save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({file:AM.file,paths,anchor,term,def,wrap:true})})
  .then(r=>r.json()).then(res=>{
    if(res.ok){ entry.pend=false; amToast('已落盘：'+anchor+' 盒（'+els.length+' 个成员）'); }
    else amToast('服务拒绝：'+(res.error||'未知错误'));
    amBuild(); amSync();
  }).catch(()=>{ AM.saveUrl=null; amToast('写入失败，转为未落盘'); amBuild(); amSync(); });
}
function amToggle(force){
  AM.on=(force!==undefined)?force:!AM.on;
  document.querySelector('.am-switch').classList.toggle('on',AM.on);
  document.getElementById('am-fab').classList.toggle('cur',AM.on);
  if(AM.on){ amBuild(); amSync(); }
  else{ amClearOverlays(); AM.solo.clear(); amCloseCard(); amGroupCancel(); AM.picking=false; document.body.classList.remove('am-picking'); }
}
function amSetVariant(v){
  if(AM.variant==='a'&&v==='b') AM.solo=new Set(amAnchored().map(el=>el.getAttribute('data-term-anchor')));
  AM.variant=v;
  document.querySelectorAll('.am-switch button[data-v]').forEach(b=>b.classList.toggle('cur',b.dataset.v===v));
  amBuild(); amSync();
}
document.addEventListener('click',(e)=>{
  if(!AM.on)return;
  if(e.target.closest('.am-ui'))return;
  e.preventDefault(); e.stopPropagation();
  if(AM.groupPicking){ amGroupToggle(e.target); return; }
  if(AM.picking){
    AM.picking=false; document.body.classList.remove('am-picking');
    amInfo(e.target);
    return;
  }
  if(e.target.hasAttribute&&e.target.hasAttribute('data-term-anchor'))amInfo(e.target);
},true);
document.addEventListener('keydown',(e)=>{
  if(e.key!=='Escape')return;
  if(document.getElementById('am-card')){ amCloseCard(); return; }
  if(AM.groupPicking){ amGroupCancel(); return; }
  if(AM.on)amToggle(false);
});
function amDiscoverTerms(){
  document.querySelectorAll('[data-term-anchor]').forEach(el=>{
    const a=el.getAttribute('data-term-anchor');
    if(!AM_TERMS.some(t=>t.anchor===a)) AM_TERMS.push({term:a,anchor:a,def:'（待补定义）'});
  });
}
function amLoadTerms(){
  if(AM.saveUrl===null){ amDiscoverTerms(); return; }
  fetch(AM.saveUrl+'/__am_terms?file='+encodeURIComponent(AM.file))
  .then(r=>r.json()).then(res=>{
    if(Array.isArray(res.terms)) res.terms.forEach(t=>{
      if(!AM_TERMS.some(x=>x.anchor===t.anchor)) AM_TERMS.push(t);
    });
    amDiscoverTerms();
  }).catch(()=>amDiscoverTerms());
}
function amInit(){
  const fab=document.createElement('button');
  fab.id='am-fab'; fab.className='am-fab am-ui'; fab.textContent='⬦ 锚点'; fab.title='锚点视图模式';
  fab.onclick=()=>amToggle();
  const sw=document.createElement('div'); sw.className='am-switch am-ui';
  sw.innerHTML='<button data-v="a" class="cur">A 覆盖标签</button><button data-v="b">B 锚点清单</button><button data-v="c">C 层级条</button><span>Esc 退出</span>';
  sw.querySelectorAll('button').forEach(b=>b.onclick=()=>amSetVariant(b.dataset.v));
  document.body.appendChild(fab); document.body.appendChild(sw);
  AM.saveUrl=null;
  AM.file=(location.protocol==='file:')?decodeURIComponent(location.pathname)
    :(new URLSearchParams(location.search).get('abs')||location.pathname.split('/').pop()||'prototype.html');
  const bases=(location.protocol==='file:')?['http://127.0.0.1:8420']:['','http://127.0.0.1:8420'];
  (function tryPing(){
    if(!bases.length){ amDiscoverTerms(); return; }
    const b=bases.shift();
    fetch(b+'/__am_ping').then(r=>{ if(!r.ok)throw 0; AM.saveUrl=b;
      setInterval(()=>{ if(AM.saveUrl!==null)fetch(AM.saveUrl+'/__am_ping').catch(()=>{}); },60000);
      amLoadTerms();
    }).catch(tryPing);
  })();
}
if(document.body) amInit();
else document.addEventListener('DOMContentLoaded',amInit);
})();
