const API=window.API_BASE||"";
const $=s=>document.querySelector(s), esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const LANG=(()=>{try{return localStorage.getItem("nw-lang")==="de"?"de":"en"}catch{return"en"}})(), L=(en,de)=>LANG==="de"?de:en;
const api=(u,o={})=>{o.headers={...(o.headers||{}),"X-Lang":LANG};if(o.json){o.method=o.method||"POST";o.headers["Content-Type"]="application/json";o.body=JSON.stringify(o.json)}
  return fetch(API+u,o).then(async r=>{const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.detail||r.statusText);return j})};
let cfg,photos=[],docsCache=[],activeDoc=null,docsSel=null,filter="all",map,layer;
const SRC={message:"chat message",voice:"dictation",answer:"your answer in chat",user:"edited by you",timestamp:"message time",weather:"weather service",
  photo:"photos",drilling:"drilling list (Polier)",schedule:"schedule",diary:"site diary",documents:"notices",email:"e-mail",minutes:"minutes",document:"client document",project:"project data",calendar:"calendar"};
// reviewer (LLM B) state per critical field, set by backend/core/review.py
const REV={being_verified:"⏳ being verified",verified:"✓ verified",flagged:"⚠ check source"};
// TAB_APPLY switches the view; TAB lets js/fx.js wrap it in a cinematic transition when present
const TAB=t=>window.FX?FX.tab(t,()=>TAB_APPLY(t)):TAB_APPLY(t);
const TAB_APPLY=t=>{document.querySelectorAll("#nav button").forEach(x=>x.classList.toggle("on",x.dataset.t==t));
  document.querySelectorAll(".tab").forEach(s=>s.classList.toggle("on",s.id==t));
  if(t=="twin"){if(window.SiteTwin)window.SiteTwin.show();else{document.addEventListener("sitetwin-ready",()=>window.SiteTwin.show(),{once:true});
    setTimeout(()=>{if(!window.SiteTwin)twinFail("The 3D module did not load within 8 s (blocked script, old cached file, or WebGL disabled).")},8000)}} else window.SiteTwin?.hide();
  if(t=="mapt")drawMap(); if(t=="metrics")loadMetrics(); if(t=="plan")loadPlan(); if(t=="docs")loadDocs(); if(t=="photos")loadPhotos();};
document.querySelectorAll("#nav button").forEach(b=>b.onclick=()=>TAB(b.dataset.t));

async function init(){cfg=await api("/api/config");$("#reportLink").href=API+"/api/report";
  $("#site").textContent=cfg.site.name;
  const L=cfg.llm;$("#b-llm").textContent=L.mode=="llm"?"BauBuddy AI":(LANG==="de"?"Nur Regeln":"Rules only");
  $("#b-llm").title=L.mode=="llm"?`Confidence threshold ${L.threshold}. Critical fields: ${L.critical_fields.join(", ")}`:`LLM off (${L.error||"no key"}). Rules run under the same evidence and confidence gates.`;
  $("#b-llm").classList.toggle("g",L.mode=="llm");
  $("#b-rf").textContent=cfg.mock_mode?(LANG==="de"?"Demo-Fotos":"Demo photos"):(LANG==="de"?"Foto-KI live":"Photo AI live");$("#b-rf").classList.toggle("g",!cfg.mock_mode);
  $("#newType").innerHTML=Object.entries(cfg.doc_types).map(([k,v])=>`<option value="${k}">${esc(v.title)}</option>`).join("");
  $("#pDate").value=new Date(Date.now()-new Date().getTimezoneOffset()*6e4).toISOString().slice(0,10);
  await loadPhotos();}

/* ---------- chat lives in the AI Manager tab (js/command.js) ---------- */
window.NW={dictated:false};
/* ---------- document view ---------- */
function showAssistDoc(id){openDocInTab(id);}
function renderDoc(el,d){
  const st=d.status,ro=st=="sent";
  const finds={};(d.review?.findings||[]).forEach(x=>(finds[x.field_name]=finds[x.field_name]||[]).push(x));
  const fields=d.meta.fields.map(m=>{const f=d.fields[m.key],miss=m.required&&!f.value,low=f.value&&f.by=="ai"&&f.confidence!=null&&f.confidence<0.7;
    const s=f.source;const srcTxt=s?(SRC[s.type]||s.type):"";
    return `<div class="f ${miss?"miss":""} ${low?"low":""}" data-k="${m.key}">
      <label>${esc(m.label)}${m.required?' <span style="color:var(--bad)">*</span>':""}${m.critical?' <span class="mut" title="critical field">●</span>':""}${f.locked?' <span title="Edited by you, AI will not overwrite">🔒</span>':""}${m.custom?` <span class="mut" title="Field you added">eigenes Feld</span>${ro?"":` <button class="s" data-rmf="${m.key}" title="Remove this field">×</button>`}`:""}${REV[f.review?.status]?` <span class="rev ${f.review.status}" title="${esc(f.review.note_de||REV[f.review.status])}">${REV[f.review.status]}</span>`:""}</label>
      <textarea rows="${Math.min(6,Math.max(1,Math.ceil((f.value||"").length/70)+(f.value||"").split("\n").length-1))}" ${ro?"disabled":""} placeholder="${miss?"missing, required":"empty"}">${esc(f.value)}</textarea>
      ${finds[m.key]?finds[m.key].map(x=>`<div class="prop bad">Reviewer (${esc(x.issue)}): ${esc(x.explanation_de)} → ${esc(x.suggested_action_de)}</div>`).join(""):""}
      ${f.value?`<div class="src">${s?`<a data-q>source: ${esc(srcTxt)}${s.locator?" · "+esc(s.locator):""}</a>${s.evidence_id?`<code style="font-size:10.5px">${esc(s.evidence_id.length>40?s.evidence_id.slice(0,40)+"…":s.evidence_id)}</code>`:""}`:""}${low?'<span style="color:var(--warn)">low confidence, please check</span>':""}${f.by=="ai"&&f.confidence!=null?`<span>conf ${Math.round(f.confidence*100)}%</span>`:""}</div>
      <div class="quote">${esc(s?.quote||"")}</div>`:""}
      ${f.proposal?`<div class="prop">AI suggests: <b>${esc(f.proposal.value)}</b> <button class="s" data-acc="${m.key}">Accept</button></div>`:""}</div>`}).join("");
  const thumbs=d.photos.map(pid=>photos.find(p=>p.id==pid)).filter(Boolean).map(p=>`<img src="${API}/data/${p.file}" title="${esc(p.category)}">`).join("")||'<span class="mut">No photos attached.</span>';
  const log=d.log.map((e,i)=>({e,i})).reverse().map(({e,i})=>`<div><span>${esc(e.at.slice(11,16))}</span><span>${esc(e.by)}</span>
    <span style="flex:1">${e.kind=="status"?`status ${esc(e.old)} → ${esc(e.new)}${e.note?" ("+esc(e.note)+")":""}`:e.kind=="proposal"?`proposal for ${esc(e.field)}`:
    `${esc(e.kind)} ${esc(e.field)}: “${esc((e.old||"").slice(0,30))}” → “${esc((e.new||"").slice(0,40))}”`}</span>
    ${e.kind=="edit"&&!e.undone&&!ro?`<button class="s" data-undo="${i}">Undo</button>`:e.undone?"<i>undone</i>":""}</div>`).join("")||"No edits yet.";
  const rv=d.review?.status;
  el.innerHTML=`<div class="dh"><h2>${esc(d.title)}</h2><span class="pill ${st}">${st}</span>${d.proposal_from?'<span class="badge">proposal from alert</span>':""}
    ${rv=="running"?'<span class="badge">critical fields being verified…</span>':rv=="completed"?`<span class="badge ${(d.review.findings||[]).length?"":"g"}">reviewer: ${(d.review.findings||[]).length} finding(s)</span>`:""}</div>
    <div class="row" style="margin-bottom:6px">
      ${st=="draft"?`<button class="p" data-st="checked" ${d.missing.length?"title='Fill required fields first'":""}>Mark as checked</button>`:""}
      ${st=="checked"?`<button class="p" data-st="sent">Approve & mark as sent</button>`:""}
      <button data-docx>Word</button><button data-pdf>PDF</button><span data-id="${d.id}" style="display:none"></span></div>
    <div class="err" id="derr"></div>
    ${d.missing.length?`<div class="mut" style="margin-bottom:4px">Missing required: ${esc(d.missing.map(k=>d.meta.fields.find(f=>f.key==k).label).join(", "))}</div>`:""}
    ${fields}
    ${ro?"":`<button class="s" id="addField" style="margin:2px 0 8px" title="Add a field this document type does not have">${L("+ Add field","+ Feld hinzufügen")}</button>`}
    <details ${d.photos.length?"open":""}><summary>Photos (${d.photos.length})</summary><div class="thumbs">${thumbs}</div>
      ${ro?"":`<button class="s" id="pickPh" style="margin-top:6px">Choose photos</button><div class="thumbs" id="phPick" style="display:none;margin-top:6px"></div>`}</details>
    <details><summary>Edit log</summary><div class="log">${log}</div></details>
    <p class="mut">Draft created with AI assistance. Formal completeness check only, no legal advice. ${st!="draft"?`Checked by ${esc(d.checked_by)} ${esc((d.checked_at||"").replace("T"," ").slice(0,16))}.`:""}${d.sent_at?` Marked as sent ${esc(d.sent_at.replace("T"," ").slice(0,16))}.`:""}</p>`;
  const reload=nd=>{renderDoc(el,nd);if(el.id=="docView")loadDocs(false)};
  if(rv=="running")setTimeout(async()=>{if(el.innerHTML.includes(d.id))renderDoc(el,await api("/api/docs/"+d.id))},2500);
  el.querySelectorAll(".f").forEach(fe=>{const k=fe.dataset.k,ta=fe.querySelector("textarea"),orig=ta.value;
    ta.onblur=async()=>{if(ta.value!==orig){try{reload(await api(`/api/docs/${d.id}/fields/${k}`,{method:"PATCH",json:{value:ta.value}}))}catch(e){el.querySelector("#derr").textContent=e.message}}};
    const q=fe.querySelector("[data-q]");if(q)q.onclick=()=>{const x=fe.querySelector(".quote");x.style.display=x.style.display=="block"?"none":"block"};});
  el.querySelectorAll("[data-acc]").forEach(b=>b.onclick=async()=>reload(await api(`/api/docs/${d.id}/fields/${b.dataset.acc}/accept`,{json:{}})));
  el.querySelectorAll("[data-undo]").forEach(b=>b.onclick=async()=>reload(await api(`/api/docs/${d.id}/undo/${b.dataset.undo}`,{json:{}})));
  const err=e=>el.querySelector("#derr").textContent=e.message;
  const af=el.querySelector("#addField");if(af)af.onclick=async()=>{const label=(prompt("Name des neuen Feldes (z. B. Ort):")||"").trim();if(!label)return;
    const value=prompt(L(`Value for “${label}” (optional):`,`Wert für „${label}“ (optional):`))||"";try{reload(await api(`/api/docs/${d.id}/fields`,{json:{label,value}}))}catch(e){err(e)}};
  el.querySelectorAll("[data-rmf]").forEach(b=>b.onclick=async()=>{if(!confirm("Feld entfernen?"))return;
    try{reload(await api(`/api/docs/${d.id}/fields/${b.dataset.rmf}`,{method:"DELETE"}))}catch(e){err(e)}});
  el.querySelectorAll("[data-pdf]").forEach(b=>b.onclick=()=>openPdf(d.id,b));
  el.querySelectorAll("[data-docx]").forEach(b=>b.onclick=async()=>{b.disabled=true;await pushSnap();b.disabled=false;location.href=`${API}/api/docs/${d.id}/docx`});
  el.querySelectorAll("[data-st]").forEach(b=>b.onclick=async()=>{try{reload(await api(`/api/docs/${d.id}/status`,{json:{status:b.dataset.st}}))}catch(e){el.querySelector("#derr").textContent=e.message}});
  const pk=el.querySelector("#pickPh");if(pk)pk.onclick=()=>{const box=el.querySelector("#phPick");box.style.display="flex";const sel=new Set(d.photos);
    box.innerHTML=photos.map(p=>`<img src="${API}/data/${p.file}" data-id="${p.id}" class="${sel.has(p.id)?"sel":""}" title="${esc(p.category)} ${esc(p.taken_at)}">`).join("")+`<button class="s p" id="phSave">Save</button>`;
    box.querySelectorAll("img").forEach(i=>i.onclick=()=>{sel.has(i.dataset.id)?sel.delete(i.dataset.id):sel.add(i.dataset.id);i.classList.toggle("sel")});
    box.querySelector("#phSave").onclick=async()=>reload(await api(`/api/docs/${d.id}/photos`,{json:{photos:[...sel]}}));};
}

/* ---------- documents tab ---------- */
async function loadDocs(render=true){docsCache=await api("/api/docs");
  $("#docList").innerHTML=docsCache.map(d=>`<li data-id="${d.id}" class="${d.id==docsSel?"on":""}"><div style="display:flex;gap:6px;align-items:center"><b style="flex:1">${esc(d.title)}</b><span class="pill ${d.status}">${d.status}</span></div>
    <div class="mut">${esc(d.fields.location?.value||d.fields.date?.value||d.fields.subject?.value||"")} · ${esc(d.updated_at.replace("T"," ").slice(0,16))}${d.missing.length?` · ${d.missing.length} missing`:""}</div></li>`).join("")||'<li class="mut">No documents yet.</li>';
  $("#docList").querySelectorAll("li[data-id]").forEach(li=>li.onclick=()=>{docsSel=li.dataset.id;loadDocs()});
  if(render&&docsSel)renderDoc($("#docView"),await api("/api/docs/"+docsSel));}
function openDocInTab(id){docsSel=id;TAB("docs");}
$("#newDoc").onclick=async()=>{const d=await api("/api/docs",{json:{type:$("#newType").value}});openDocInTab(d.id)};
$("#dailyBtn").onclick=async()=>{const d=await api("/api/reports/daily",{json:{}});openDocInTab(d.id)};

/* ---------- plan ---------- */
async function loadPlan(){const p=await api("/api/plan");$("#asof").textContent=p.as_of;
  const w=p.weather_today;$("#wx").textContent=p.weather_available?(w?`${w.text}, ${Math.round(w.tmin)} to ${Math.round(w.tmax)} °C, rain ${w.rain} mm`:""):"";
  $("#alerts").innerHTML=p.alerts.map((a,i)=>`<div class="alert ${a.level}"><span class="dot ${a.level}"></span><span style="flex:1">${esc(a.text)}</span>
    ${a.suggest?`<button class="s p" data-al="${i}">${esc(a.suggest_label)}</button>`:""}</div>`).join("")||(p.activities.length?'<div class="mut">No deviations.</div>':'<div class="mut">No schedule loaded.</div>');
  $("#alerts").querySelectorAll("[data-al]").forEach(b=>b.onclick=async()=>{const a=p.alerts[b.dataset.al];b.disabled=true;
    const d=await api("/api/plan/propose",{json:{kind:a.kind,activity:a.activity}});openDocInTab(d.id)});
  $("#actTable").innerHTML=p.activities.length?`<tr><th></th><th>Activity</th><th>Period</th><th>Actual / planned</th><th style="width:28%">Progress</th><th>Delay</th></tr>`+p.activities.map(a=>`<tr><td><span class="dot ${a.light}"></span></td>
    <td>${esc(a.name)}</td><td class="mut">${esc(a.start)} – ${esc(a.end)}</td><td>${a.actual} / ${a.planned} ${esc(a.unit)} <span class="mut">of ${a.total}</span></td>
    <td><div class="bar"><i style="width:${Math.min(100,a.actual/a.total*100)}%"></i><b style="left:${Math.min(100,a.planned/a.total*100)}%"></b></div></td>
    <td>${a.light=="grey"?'<span class="mut">not started</span>':a.delay_days>0?a.delay_days+" d":"on plan"}</td></tr>`).join(""):"";
  $("#pAct").innerHTML=p.activities.map(a=>`<option value="${a.id}">${esc(a.name)}</option>`).join("");}
$("#pAdd").onclick=async()=>{if(!$("#pQty").value)return;await api("/api/progress",{json:{date:$("#pDate").value,activity:$("#pAct").value,qty:+$("#pQty").value,note:$("#pNote").value}});
  $("#pQty").value=$("#pNote").value="";loadPlan()};

/* ---------- summaries ---------- */
let samples=null;const getS=async()=>samples||(samples=await api("/api/demo/samples"));
$("#sMin").onclick=async()=>$("#sumText").value=(await getS()).minutes;$("#sMail").onclick=async()=>$("#sumText").value=(await getS()).email;
$("#sGo").onclick=async()=>{const text=$("#sumText").value.trim();if(!text)return;$("#sumOut").innerHTML='<div class="empty">Working…</div>';
  const r=await api("/api/summarize",{json:{text}});
  $("#sumOut").innerHTML=`<b>Summary (${esc(r.kind)})</b><ul>${r.summary.map(s=>`<li>${esc(s)}</li>`).join("")}</ul>
    ${r.masked?.length?`<p class="mut">Masked before AI: ${esc(r.masked.join(", "))}</p>`:""}
    <b>Open items</b>${r.open_items.length?`<table class="t"><tr><th>Item</th><th>Owner</th><th>Deadline</th></tr>${r.open_items.map(i=>`<tr title="${esc(i.quote)}"><td>${esc(i.item)}</td><td>${esc(i.owner||"—")}</td><td>${esc(i.deadline||"—")}</td></tr>`).join("")}</table>`:'<p class="mut">None found.</p>'}
    ${r.decisions.length?`<b>Decisions</b><ul>${r.decisions.map(s=>`<li>${esc(s)}</li>`).join("")}</ul>`:""}
    ${r.nachtrag_candidates.length?`<div class="alert yellow" style="display:block"><b>Possible change order (client instruction / changed work)</b><ul>${r.nachtrag_candidates.map(s=>`<li>${esc(s)}</li>`).join("")}</ul>
      <button class="p s" id="mkNT">Draft change order notice from this</button></div>`:""}`;
  const b=$("#mkNT");if(b)b.onclick=async()=>{b.disabled=true;const d=await api("/api/docs",{json:{type:"nachtragsmeldung",text,source:r.kind=="email"?"email":"minutes"}});openDocInTab(d.id)};};

/* ---------- photos, map, live ---------- */
async function loadPhotos(){photos=await api("/api/photos");renderPhotos();}
// English display names for category keys that are German terms (German mode: js/ui-glass.js translates the keys)
const CATN=LANG==="de"?{}:{"Nachtrag evidence":"change order evidence"},catName=c=>CATN[c]||c;
function renderPhotos(){const cats=["all",...cfg.categories];
  $("#cats").innerHTML=cats.map(c=>`<span class="chip ${c==filter?"on":""}" data-c="${esc(c)}">${esc(catName(c))} ${c=="all"?photos.length:photos.filter(p=>p.category==c).length}</span>`).join("");
  $("#cats").querySelectorAll(".chip").forEach(x=>x.onclick=()=>{filter=x.dataset.c;renderPhotos()});
  $("#grid").innerHTML=photos.filter(p=>filter=="all"||p.category==filter).slice().reverse().map(p=>`<div class="pc ${p.needs_confirmation??(p.confidence<.5&&p.category_source=="model")?"low":""}">
    <img src="${API}/data/${p.file}" data-id="${p.id}"><div class="b"><select data-id="${p.id}">${cfg.categories.map(c=>`<option value="${esc(c)}" ${c==p.category?"selected":""}>${esc(catName(c))}</option>`).join("")}</select>
    <span class="mut">${p.category_source=="user"?"set by you":(p.category_source=="llm"?"vision LLM ":"detector ")+Math.round(p.confidence*100)+"%"} · ${p.location_source=="exif"?"GPS from photo":"site location"}</span>
    ${p.caption_de?`<span style="font-size:12.5px">${esc(p.caption_de)}</span>`:""}${p.needs_confirmation&&p.category_source!="user"?'<span style="color:var(--warn);font-size:12px">please confirm category</span>':""}
    <span class="mut">${esc((p.taken_at||"").replace("T"," "))}</span></div></div>`).join("")||'<p class="mut">No photos yet.</p>';
  $("#grid").querySelectorAll("img").forEach(i=>i.onclick=()=>openP(i.dataset.id));
  $("#grid").querySelectorAll("select").forEach(s=>s.onchange=async()=>{await api("/api/photos/"+s.dataset.id,{method:"PATCH",json:{category:s.value}});loadPhotos()});}
up.onchange=async()=>{const fd=new FormData();[...up.files].forEach(f=>fd.append("files",f));try{await api("/api/photos",{method:"POST",body:fd})}catch(e){alert(e.message)}up.value="";loadPhotos()};
function drawBoxes(cv,w,h,dets){cv.width=w;cv.height=h;const c=cv.getContext("2d");c.clearRect(0,0,w,h);c.lineWidth=Math.max(2,w/300);c.strokeStyle=c.fillStyle="#e11";c.font=`${Math.max(12,w/50)}px sans-serif`;
  dets.forEach(d=>{c.strokeRect(d.x-d.width/2,d.y-d.height/2,d.width,d.height);c.fillText(`${d.class} ${Math.round(d.confidence*100)}%`,d.x-d.width/2+4,d.y-d.height/2+14)});}
function openP(id){const p=photos.find(x=>x.id==id);dimg.onload=()=>drawBoxes(dcv,dimg.naturalWidth,dimg.naturalHeight,p.detections);dimg.src=API+"/data/"+p.file;
  dinfo.innerHTML=`<b>${esc(p.category)}</b> (${esc(p.category_source)}) · ${p.lat.toFixed(5)}, ${p.lon.toFixed(5)} (${esc(p.location_source)})<br><span class="mut">Detections: ${esc(p.detections.map(d=>d.class+" "+Math.round(d.confidence*100)+"%").join(", ")||(p.mock?"mock mode":"none"))}</span>`;dlg.showModal();}
dlg.onclick=e=>{if(e.target==dlg)dlg.close()};
function drawMap(){if(!map){map=window.L.map("mapbox").setView([cfg.site.lat,cfg.site.lon],16);window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"© OpenStreetMap"}).addTo(map);layer=window.L.layerGroup().addTo(map)}
  layer.clearLayers();window.L.marker([cfg.site.lat,cfg.site.lon]).addTo(layer).bindPopup("Site");
  photos.forEach(p=>window.L.circleMarker([p.lat,p.lon],{radius:7,color:p.location_source=="exif"?"#c8501e":"#888"}).addTo(layer).bindPopup(`<img src="${API}/data/${p.file}" width="160"><br>${esc(p.category)}`));
  setTimeout(()=>{map.invalidateSize();if(!map._fitted&&photos.length){map._fitted=true;map.fitBounds(window.L.latLngBounds(photos.map(p=>[p.lat,p.lon]).concat([[cfg.site.lat,cfg.site.lon]])),{padding:[40,40],maxZoom:17})}},60);}
let stream,timer,busy=false;
camBtn.onclick=async()=>{if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;clearInterval(timer);camBtn.textContent="Start camera";snap.disabled=true;return}
  stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:"environment"}});vid.srcObject=stream;await vid.play();camBtn.textContent="Stop camera";snap.disabled=false;
  timer=setInterval(async()=>{if(busy||!vid.videoWidth)return;busy=true;const c=document.createElement("canvas");c.width=vid.videoWidth;c.height=vid.videoHeight;c.getContext("2d").drawImage(vid,0,0);
    const blob=await new Promise(r=>c.toBlob(r,"image/jpeg",.7));const fd=new FormData();fd.append("file",blob,"f.jpg");
    try{const r=await api("/api/infer",{method:"POST",body:fd});drawBoxes(ov,c.width,c.height,r.detections);document.dispatchEvent(new CustomEvent("bb:live-detections",{detail:r}));liveinfo.textContent=r.mock?"mock mode":r.detections.length+" detections"}catch(e){liveinfo.textContent=e.message}busy=false},1000)};
snap.onclick=async()=>{const c=document.createElement("canvas");c.width=vid.videoWidth;c.height=vid.videoHeight;c.getContext("2d").drawImage(vid,0,0);
  const blob=await new Promise(r=>c.toBlob(r,"image/jpeg",.9));const fd=new FormData();fd.append("files",blob,"live_"+Date.now()+".jpg");await api("/api/photos",{method:"POST",body:fd});loadPhotos()};

/* ---------- metrics ---------- */
async function loadMetrics(){const m=await api("/api/metrics");
  $("#mTable").innerHTML=m.stages.length?`<tr><th>Stage</th><th>Runs</th><th>Avg ms</th><th>Median ms</th><th>Max ms</th><th>Tokens in/out</th><th>Cost €</th><th>Model</th></tr>`+
    m.stages.map(a=>`<tr><td>${esc(a.stage)}</td><td>${a.count}</td><td>${a.avg_ms}</td><td>${a.p50_ms}</td><td>${a.max_ms}</td><td>${a.tokens_in} / ${a.tokens_out}</td><td>${a.cost_eur}</td><td>${esc(a.model||"—")}</td></tr>`).join(""):'<tr><td class="mut">No measurements yet.</td></tr>';
  $("#mRecent").innerHTML=m.recent.map(r=>`<div><span>${esc(r.started_at.slice(11,19))}</span><span style="flex:1">${esc(r.stage)} · ${esc(r.run_id)}</span><span>${r.duration_ms} ms</span></div>`).join("");}
$("#mRefresh").onclick=()=>{loadMetrics();window.NWDash?.loadPerf?.()};

/* ---------- demo controls (no browser dialogs) ---------- */
// full demo state (project, schedule, site documents -> layout, geotagged photos, incidents), then reload every view
$("#demoBtn").onclick=async()=>{$("#demoBtn").textContent="Loading…";await api("/api/demo/full",{json:{}});location.reload()};
let armed=false;$("#resetBtn").onclick=async()=>{if(!armed){armed=true;$("#resetBtn").textContent="Click again to reset";setTimeout(()=>{armed=false;$("#resetBtn").textContent="Reset demo"},3000);return}
  await api("/api/demo/reset",{json:{}});armed=false;$("#resetBtn").textContent="Reset demo";docsSel=null;NW.loadMsgs?.();};
init();
// slots for the other workstreams (js/voice.js, inbox.js, replan.js, tile.js)
Object.assign(window.NW,{api,esc,$,showAssistDoc,openDocInTab,TAB});

// PDF: headless-LibreOffice export (with ENTWURF watermark); 503/any failure falls back to the browser print view.
// The tab is opened synchronously (inside the click) so popup blockers allow it; it is then pointed at the PDF blob or the print view.
// the report embeds a 3D view of the live twin: upload a fresh overview shot before exporting (skipped if the twin never loaded)
async function pushSnap(){try{const img=window.SiteTwin?.reportShot?.();if(img)await api("/api/site/snapshot",{json:{image:img}})}catch(e){}}
async function openPdf(id,btn){
  const w=window.open("","_blank"),print=`${API}/api/docs/${id}/print`;
  await pushSnap();
  if(btn)btn.disabled=true;
  try{
    const r=await fetch(`${API}/api/docs/${id}/pdf`);
    if(!r.ok||!/pdf/i.test(r.headers.get("content-type")||""))throw new Error(r.status);
    const url=URL.createObjectURL(await r.blob());
    if(w)w.location.href=url;else{const a=document.createElement("a");a.href=url;a.download=`${id}.pdf`;a.click()}
    setTimeout(()=>URL.revokeObjectURL(url),60000);
  }catch(e){if(w)w.location.href=print;else window.location.href=print}
  finally{if(btn)btn.disabled=false}
}
