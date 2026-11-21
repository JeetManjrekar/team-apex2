const API=window.API_BASE||"";
const $=s=>document.querySelector(s), esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const api=(u,o={})=>{if(o.json){o.method=o.method||"POST";o.headers={"Content-Type":"application/json"};o.body=JSON.stringify(o.json)}
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
  const L=cfg.llm;$("#b-llm").textContent=L.mode=="llm"?`BauBuddy AI: ${L.model}${L.reviewer?" + reviewer":""}`:"Extraction: rules fallback";
  $("#b-llm").title=L.mode=="llm"?`Confidence threshold ${L.threshold}. Critical fields: ${L.critical_fields.join(", ")}`:`LLM off (${L.error||"no key"}). Rules run under the same evidence and confidence gates.`;
  $("#b-llm").classList.toggle("g",L.mode=="llm");
  $("#b-rf").textContent=cfg.mock_mode?"Photos: mock mode":"Roboflow live";$("#b-rf").classList.toggle("g",!cfg.mock_mode);
  $("#newType").innerHTML=Object.entries(cfg.doc_types).map(([k,v])=>`<option value="${k}">${esc(v.title)}</option>`).join("");
  $("#pDate").value=new Date(Date.now()-new Date().getTimezoneOffset()*6e4).toISOString().slice(0,10);
  renderChips();await loadMsgs();await loadPhotos();}

/* ---------- chat ---------- */
const DEMO=[
 ["Rock at pile 7","Bohrpfahl 7: bei 4 m auf Fels gestoßen, laut Baugrundgutachten erst ab 9 m erwartet. Bohrzeit 6 Stunden statt 2, Bohrgerät steht still."],
 ["Excavator idle","Excavator idle since 10 am at abutment south because the client has not released the reinforcement plans"],
 ["Defect","Crack in the formwork at pier 2, subcontractor Müller Bau, please fix by 24.11.2026"],
 ["Diary note","Betonlieferung Sauberkeitsschicht um 7:30 angeliefert, 12 m3, 8 Arbeiter auf der Baustelle"],
 ["Edit by chat","change duration to 3 days"],
 ["File note","Telefonat mit Hr. Weber: Meißeleinsatz an Pfahl 7 freigegeben, schriftliche Bestätigung folgt bis Montag"],
 ["Daily report","daily report"]];
function renderChips(){$("#demoChips").innerHTML=DEMO.map((d,i)=>`<span class="chip" data-i="${i}">${esc(d[0])}</span>`).join("");
  $("#demoChips").querySelectorAll(".chip").forEach(c=>c.onclick=()=>{$("#inp").value=DEMO[c.dataset.i][1];$("#inp").focus()});}
function msgHtml(m){const acts=(m.actions||[]).map((a,i)=>`<button class="s" data-act='${esc(JSON.stringify(a))}'>${esc(a.label)}</button>`).join("");
  const open=m.doc?`<button class="s" data-open="${m.doc}">Open draft</button>`:"";
  const mask=m.masked?.length?`<div class="t">Masked before AI: ${esc(m.masked.join(", "))}</div>`:"";
  return `<div class="m ${m.role}">${esc(m.text)}${(acts||open)?`<div class="acts">${open}${acts}</div>`:""}${mask}<div class="t">${esc((m.at||"").slice(11,16))}</div></div>`;}
function bindMsgs(){$("#msgs").querySelectorAll("[data-open]").forEach(b=>b.onclick=()=>showAssistDoc(b.dataset.open));
  $("#msgs").querySelectorAll("[data-act]").forEach(b=>b.onclick=async()=>{const a=JSON.parse(b.dataset.act);b.disabled=true;
    const d=await api("/api/docs",{json:{type:a.type,text:a.text,source:"message"}});showAssistDoc(d.id);});}
window.NW={dictated:false};
async function loadMsgs(){const r=await api("/api/messages");
  $("#msgs").innerHTML=r.messages.length?r.messages.map(msgHtml).join(""):`<div class="empty">Tell me what happened on site. Type, dictate with 🎤, or tap an example below.<br><br>Try: rock at pile 7 → I draft a Mehrkostenanzeige and ask for what is missing.</div>`;
  bindMsgs();$("#msgs").scrollTop=1e9;if(r.active)showAssistDoc(r.active);}
async function send(){const text=$("#inp").value.trim();if(!text)return;$("#inp").value="";$("#send").disabled=true;const voice=NW.dictated;NW.dictated=false;
  try{const r=await api("/api/chat",{json:{text,voice}});await loadMsgs();if(r.active)showAssistDoc(r.active);}
  catch(e){$("#msgs").insertAdjacentHTML("beforeend",`<div class="m assistant err">${esc(e.message)}</div>`)}$("#send").disabled=false;}
$("#send").onclick=send;$("#inp").onkeydown=e=>{if(e.key=="Enter"&&!e.shiftKey){e.preventDefault();send()}};
chatPhotos.onchange=async()=>{const fd=new FormData();[...chatPhotos.files].forEach(f=>fd.append("files",f));
  try{const r=await api("/api/photos",{method:"POST",body:fd});
    $("#msgs").insertAdjacentHTML("beforeend",`<div class="m assistant">Added ${r.length} photo(s): ${esc(r.map(p=>p.category+(p.detections.length?" ("+p.detections.map(d=>d.class).join(", ")+")":"")).join("; "))}. They will be attached to matching drafts and today's daily report.</div>`);
    $("#msgs").scrollTop=1e9;loadPhotos();}catch(e){alert(e.message)}chatPhotos.value="";};
/* ---------- document view ---------- */
async function showAssistDoc(id){activeDoc=id;const d=await api("/api/docs/"+id);renderDoc($("#assistDoc"),d);}
function renderDoc(el,d){
  const st=d.status,ro=st=="sent";
  const finds={};(d.review?.findings||[]).forEach(x=>(finds[x.field_name]=finds[x.field_name]||[]).push(x));
  const fields=d.meta.fields.map(m=>{const f=d.fields[m.key],miss=m.required&&!f.value,low=f.value&&f.by=="ai"&&f.confidence!=null&&f.confidence<0.7;
    const s=f.source;const srcTxt=s?(SRC[s.type]||s.type):"";
    return `<div class="f ${miss?"miss":""} ${low?"low":""}" data-k="${m.key}">
      <label>${esc(m.label)}${m.required?' <span style="color:var(--bad)">*</span>':""}${m.critical?' <span class="mut" title="critical field">●</span>':""}${f.locked?' <span title="Edited by you, AI will not overwrite">🔒</span>':""}${REV[f.review?.status]?` <span class="rev ${f.review.status}" title="${esc(f.review.note_de||REV[f.review.status])}">${REV[f.review.status]}</span>`:""}</label>
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
    ${d.extraction_mode?`<span class="badge ${d.extraction_mode=="llm"?"g":""}">${d.extraction_mode=="llm"?"extracted by BauBuddy AI":"extracted by rules"}</span>`:""}
    ${rv=="running"?'<span class="badge">critical fields being verified…</span>':rv=="completed"?`<span class="badge ${(d.review.findings||[]).length?"":"g"}">reviewer: ${(d.review.findings||[]).length} finding(s)</span>`:""}
    <span class="mut">${esc(d.meta.en)} ${esc(d.meta.basis)}</span></div>
    <div class="row" style="margin-bottom:6px">
      ${st=="draft"?`<button class="p" data-st="checked" ${d.missing.length?"title='Fill required fields first'":""}>Mark as checked</button>`:""}
      ${st=="checked"?`<button class="p" data-st="sent">Approve & mark as sent</button>`:""}
      <a href="${API}/api/docs/${d.id}/docx"><button>Word</button></a><a href="${API}/api/docs/${d.id}/print" target="_blank"><button>PDF</button></a><span data-id="${d.id}" style="display:none"></span></div>
    <div class="err" id="derr"></div>
    ${d.missing.length?`<div class="mut" style="margin-bottom:4px">Missing required: ${esc(d.missing.map(k=>d.meta.fields.find(f=>f.key==k).label).join(", "))}</div>`:""}
    ${fields}
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
async function loadPlan(){const p=await api("/api/plan");$("#asof").textContent=`as of ${p.as_of}`;
  const w=p.weather_today;$("#wx").textContent=p.weather_available?(w?`Weather today: ${w.text}, ${Math.round(w.tmin)} to ${Math.round(w.tmax)} °C, rain ${w.rain} mm`:""):"Weather service unreachable";
  $("#alerts").innerHTML=p.alerts.map((a,i)=>`<div class="alert ${a.level}"><span class="dot ${a.level}"></span><span style="flex:1">${esc(a.text)}</span>
    ${a.suggest?`<button class="s p" data-al="${i}">${esc(a.suggest_label)}</button>`:""}</div>`).join("")||(p.activities.length?'<div class="mut">No deviations.</div>':'<div class="mut">No schedule loaded. Click "Load demo data".</div>');
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
    ${r.nachtrag_candidates.length?`<div class="alert yellow" style="display:block"><b>Possible Nachtrag (client instruction / changed work)</b><ul>${r.nachtrag_candidates.map(s=>`<li>${esc(s)}</li>`).join("")}</ul>
      <button class="p s" id="mkNT">Draft Nachtragsmeldung from this</button></div>`:""}`;
  const b=$("#mkNT");if(b)b.onclick=async()=>{b.disabled=true;const d=await api("/api/docs",{json:{type:"nachtragsmeldung",text,source:r.kind=="email"?"email":"minutes"}});openDocInTab(d.id)};};

/* ---------- photos, map, live ---------- */
async function loadPhotos(){photos=await api("/api/photos");renderPhotos();}
function renderPhotos(){const cats=["all",...cfg.categories];
  $("#cats").innerHTML=cats.map(c=>`<span class="chip ${c==filter?"on":""}" data-c="${esc(c)}">${esc(c)} ${c=="all"?photos.length:photos.filter(p=>p.category==c).length}</span>`).join("");
  $("#cats").querySelectorAll(".chip").forEach(x=>x.onclick=()=>{filter=x.dataset.c;renderPhotos()});
  $("#grid").innerHTML=photos.filter(p=>filter=="all"||p.category==filter).slice().reverse().map(p=>`<div class="pc ${p.needs_confirmation??(p.confidence<.5&&p.category_source=="model")?"low":""}">
    <img src="${API}/data/${p.file}" data-id="${p.id}"><div class="b"><select data-id="${p.id}">${cfg.categories.map(c=>`<option ${c==p.category?"selected":""}>${esc(c)}</option>`).join("")}</select>
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
function drawMap(){$("#siteinfo").textContent=`Site: ${cfg.site.name} (${cfg.site.lat}, ${cfg.site.lon}). Orange = GPS from photo, grey = site location (no GPS in photo).`;
  if(!map){map=L.map("mapbox").setView([cfg.site.lat,cfg.site.lon],16);L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"© OpenStreetMap"}).addTo(map);layer=L.layerGroup().addTo(map)}
  layer.clearLayers();L.marker([cfg.site.lat,cfg.site.lon]).addTo(layer).bindPopup("Site");
  photos.forEach(p=>L.circleMarker([p.lat,p.lon],{radius:7,color:p.location_source=="exif"?"#c8501e":"#888"}).addTo(layer).bindPopup(`<img src="${API}/data/${p.file}" width="160"><br>${esc(p.category)}`));
  setTimeout(()=>map.invalidateSize(),50);}
let stream,timer,busy=false;
camBtn.onclick=async()=>{if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;clearInterval(timer);camBtn.textContent="Start camera";snap.disabled=true;return}
  stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:"environment"}});vid.srcObject=stream;await vid.play();camBtn.textContent="Stop camera";snap.disabled=false;
  timer=setInterval(async()=>{if(busy||!vid.videoWidth)return;busy=true;const c=document.createElement("canvas");c.width=vid.videoWidth;c.height=vid.videoHeight;c.getContext("2d").drawImage(vid,0,0);
    const blob=await new Promise(r=>c.toBlob(r,"image/jpeg",.7));const fd=new FormData();fd.append("file",blob,"f.jpg");
    try{const r=await api("/api/infer",{method:"POST",body:fd});drawBoxes(ov,c.width,c.height,r.detections);liveinfo.textContent=r.mock?"mock mode":r.detections.length+" detections"}catch(e){liveinfo.textContent=e.message}busy=false},1000)};
snap.onclick=async()=>{const c=document.createElement("canvas");c.width=vid.videoWidth;c.height=vid.videoHeight;c.getContext("2d").drawImage(vid,0,0);
  const blob=await new Promise(r=>c.toBlob(r,"image/jpeg",.9));const fd=new FormData();fd.append("files",blob,"live_"+Date.now()+".jpg");await api("/api/photos",{method:"POST",body:fd});loadPhotos()};

/* ---------- metrics ---------- */
async function loadMetrics(){const m=await api("/api/metrics");$("#mfile").textContent=m.file;
  $("#mTable").innerHTML=m.stages.length?`<tr><th>Stage</th><th>Runs</th><th>Avg ms</th><th>Median ms</th><th>Max ms</th><th>Tokens in/out</th><th>Cost €</th><th>Model</th></tr>`+
    m.stages.map(a=>`<tr><td>${esc(a.stage)}</td><td>${a.count}</td><td>${a.avg_ms}</td><td>${a.p50_ms}</td><td>${a.max_ms}</td><td>${a.tokens_in} / ${a.tokens_out}</td><td>${a.cost_eur}</td><td>${esc(a.model||"—")}</td></tr>`).join(""):'<tr><td class="mut">No measurements yet. Use the assistant first.</td></tr>';
  $("#mRecent").innerHTML=m.recent.map(r=>`<div><span>${esc(r.started_at.slice(11,19))}</span><span style="flex:1">${esc(r.stage)} · ${esc(r.run_id)}</span><span>${r.duration_ms} ms</span></div>`).join("");}
$("#mRefresh").onclick=loadMetrics;

/* ---------- demo controls (no browser dialogs) ---------- */
$("#demoBtn").onclick=async()=>{await api("/api/demo/load",{json:{}});$("#demoBtn").textContent="Demo data loaded ✓";loadPlan()};
let armed=false;$("#resetBtn").onclick=async()=>{if(!armed){armed=true;$("#resetBtn").textContent="Click again to reset";setTimeout(()=>{armed=false;$("#resetBtn").textContent="Reset demo"},3000);return}
  await api("/api/demo/reset",{json:{}});armed=false;$("#resetBtn").textContent="Reset demo";$("#assistDoc").innerHTML='<div class="empty">Drafts appear here.</div>';docsSel=null;loadMsgs();};
init();
// slots for the other workstreams (js/voice.js, inbox.js, replan.js, tile.js)
Object.assign(window.NW,{api,esc,$,loadMsgs,showAssistDoc,TAB});
