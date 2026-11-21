// inbox.js (W1): drop zone for Outlook .eml / .ics files and client documents (.pdf .docx .xlsx .csv) in #inboxSlot -> POST /api/inbox/import. Uses window.NW.
(() => {
  const slot = document.getElementById("inboxSlot");
  if (!slot || !window.NW || !NW.api) return;
  const { api, esc } = NW;

  // Show the card at the top of the Assistant tab unless the layout already placed it inside a tab.
  const assist = document.getElementById("assist");
  if (assist && !slot.closest(".tab")) assist.prepend(slot);

  const css = document.createElement("style");
  css.textContent = `
    .nw-inbox{margin-bottom:14px}
    .nw-inbox .dz{border:2px dashed var(--line,#3a4254);border-radius:12px;padding:18px;text-align:center;cursor:pointer}
    .nw-inbox .dz.over{border-color:#ff6a2b;background:rgba(255,106,43,.08)}
    .nw-inbox .dz small{display:block;opacity:.7;margin-top:4px}
    .nw-inbox ul{list-style:none;margin:10px 0 0;padding:0;display:grid;gap:8px}
    .nw-inbox li{border:1px solid var(--line,#3a4254);border-radius:10px;padding:10px;display:grid;gap:4px}
    .nw-inbox li b{display:block}
    .nw-inbox .tag{font-size:11px;opacity:.7;text-transform:uppercase;letter-spacing:.04em}
    .nw-inbox .row{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
    .nw-inbox .err{color:#ff7a7a}
    .nw-inbox .sync{border:1px solid var(--line,#3a4254);border-radius:12px;padding:12px;margin-bottom:12px;display:grid;gap:8px}
    .nw-inbox .sync details{font-size:13px}
    .nw-inbox .sync summary{cursor:pointer;opacity:.85}
    .nw-inbox .sync input[type=url]{width:100%;box-sizing:border-box;margin:8px 0 6px}
    .nw-inbox .sync label{display:flex;gap:6px;align-items:flex-start;opacity:.85}`;
  document.head.appendChild(css);

  slot.innerHTML = `<div class="card nw-inbox">
    <h3 style="margin:0 0 8px">Outlook-Import</h3>
    <div class="sync">
      <div class="row"><button class="s" data-sync>Sync Demo Inbox &amp; Calendar</button><span class="mut">nur auf Klick · Personendaten werden lokal maskiert</span></div>
      <details><summary>Connect iCal URL (Read-Only, 7-Day Window)</summary>
        <input type="url" placeholder="https://…/calendar.ics" autocomplete="off" aria-label="iCal URL">
        <label><input type="checkbox" data-consent> Allow Nachweis to read upcoming meetings for the next 7 days; PII is masked locally</label>
      </details>
    </div>
    <div class="dz" tabindex="0" role="button" aria-label="E-Mails, Kalendereinträge und Dokumente hochladen">
      Dateien hierher ziehen oder tippen<small>.eml (E-Mails), .ics (Kalender), .pdf / .docx / .xlsx / .csv (Dokumente, Tabellen), mehrere Dateien möglich</small>
      <button class="s" type="button" data-upload style="margin-top:8px">Dateien hochladen …</button>
    </div>
    <input type="file" accept=".eml,.ics,.pdf,.docx,.xlsx,.csv,message/rfc822,text/calendar,application/pdf,text/csv,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" multiple hidden>
    <ul class="out"></ul></div>`;
  const dz = slot.querySelector(".dz"), input = slot.querySelector("input[type=file]"), out = slot.querySelector(".out");

  const openBtn = d => `<button class="s" data-open="${esc(d.id)}">Entwurf öffnen: ${esc(d.title)}</button>`;
  const labels = a => (a || []).map(esc).join(", ");

  function mailCard(m) {
    const drafts = m.drafts.map(d => `<div class="row">${openBtn(d)}<span class="mut">${d.created ? "neuer Entwurf" : "bestehender Entwurf"}${
      d.proposals.length ? ` · Vorschlag: ${labels(d.proposal_labels)}` : ""}${d.filled.length ? ` · ergänzt: ${labels(d.filled_labels)}` : ""}</span></div>`).join("");
    const items = m.open_items.map(i => `<li style="border:0;padding:0">• ${esc(i.item)}${i.deadline ? ` <span class="mut">(bis ${esc(i.deadline)})</span>` : ""}</li>`).join("");
    return `<li><span class="tag">E-Mail · ${esc(m.evidence_id)}${m.duplicate ? " · bereits importiert" : ""}</span>
      <b>${esc(m.subject || m.file)}</b><span class="mut">von ${esc(m.from)}${m.masked.length ? ` · maskiert: ${esc(m.masked.join(", "))}` : ""}</span>
      ${(m.summary || []).slice(1).map(s => `<span>${esc(s)}</span>`).join("")}${items ? `<ul>${items}</ul>` : ""}${drafts}</li>`;
  }
  const calCard = r => `<li><span class="tag">Erinnerung · ${esc(r.evidence_id)}</span><b>${esc(r.message)}</b>
    <span class="mut">${esc(r.location)}${r.attendees.length ? " · " + esc(r.attendees.join(", ")) : ""}</span>
    ${r.open_items.map(i => `<span>• ${esc(i.item)}</span>`).join("")}</li>`;

  function docCard(m) {
    const drafts = m.drafts.map(d => `<div class="row">${openBtn(d)}<span class="mut">${
      d.proposals.length ? `Vorschlag: ${labels(d.proposal_labels)}` : ""}${d.filled.length ? ` · ergänzt: ${labels(d.filled_labels)}` : ""}</span></div>`).join("");
    const items = m.open_items.map(i => `<li style="border:0;padding:0">• ${esc(i.item)}${i.deadline ? ` <span class="mut">(bis ${esc(i.deadline)})</span>` : ""}</li>`).join("");
    const cite = m.locators.slice(0, 6).map(esc).join(" · ") + (m.locators.length > 6 ? " …" : "");
    return `<li><span class="tag">Dokument · ${esc(m.format)} · ${esc(m.evidence_id)}${m.duplicate ? " · bereits importiert" : ""}</span>
      <b>${esc(m.file)}</b><span class="mut">${m.units} Abschnitt(e): ${cite}${m.masked.length ? ` · maskiert: ${esc(m.masked.join(", "))}` : ""}</span>
      ${(m.summary || []).slice(0, 3).map(s => `<span>${esc(s)}</span>`).join("")}${items ? `<ul>${items}</ul>` : ""}${drafts}
      ${!m.drafts.length && !m.duplicate ? `<span class="mut">Kein passender offener Entwurf – es wurde nichts angelegt.</span>` : ""}
      ${m.truncated ? `<span class="mut">Nur die ersten Abschnitte wurden zugeordnet.</span>` : ""}</li>`;
  }

  function render(res) {
    const cards = res.emails.map(mailCard).concat((res.documents || []).map(docCard)).concat(res.reminders.map(calCard))
      .concat(res.skipped.map(s => `<li><span class="err"><b>${esc(s.file)}</b>: ${esc(s.reason)}</span></li>`));
    out.innerHTML = cards.join("") || `<li class="mut">Nichts importiert.</li>`;
    out.querySelectorAll("[data-open]").forEach(b => b.onclick = () => { NW.TAB("assist"); NW.showAssistDoc(b.dataset.open); });
    if (res.notifications.length && NW.loadMsgs) NW.loadMsgs();
  }

  async function upload(files) {
    files = [...files];
    if (!files.length) return;
    const fd = new FormData();
    files.forEach(f => fd.append("files", f));
    out.innerHTML = `<li class="mut">Importiere ${files.length} Datei(en) …</li>`;
    try { render(await api("/api/inbox/import", { method: "POST", body: fd })); }
    catch (e) { out.innerHTML = `<li><span class="err">${esc(e.message)}</span></li>`; }
    input.value = "";
  }

  const syncBtn = slot.querySelector("[data-sync]"), urlIn = slot.querySelector("input[type=url]"), consent = slot.querySelector("[data-consent]");
  syncBtn.onclick = async () => {
    const url = urlIn.value.trim(), body = { include_samples: true };
    if (url && consent.checked) body.ics_url = url;
    syncBtn.disabled = true;
    out.innerHTML = `<li class="mut">Synchronisiere …</li>`;
    try {
      const res = await api("/api/inbox/sync", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      render(res);
      const bad = (res.sources_synced || []).filter(s => !s.ok).map(s => `<li><span class="err">${esc(s.source)}: ${esc(s.error)}</span></li>`).join("");
      if (url && !consent.checked) out.insertAdjacentHTML("afterbegin", `<li class="mut">iCal-URL ignoriert: Einwilligung nicht angehakt.</li>`);
      out.insertAdjacentHTML("afterbegin", bad);
    } catch (e) { out.innerHTML = `<li><span class="err">${esc(e.message)}</span></li>`; }
    syncBtn.disabled = false;
  };

  slot.querySelector("[data-upload]").onclick = e => { e.stopPropagation(); input.click(); };
  dz.onclick = () => input.click();
  dz.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } };
  input.onchange = () => upload(input.files);
  ["dragenter", "dragover"].forEach(t => dz.addEventListener(t, e => { e.preventDefault(); dz.classList.add("over"); }));
  ["dragleave", "drop"].forEach(t => dz.addEventListener(t, e => { e.preventDefault(); dz.classList.remove("over"); }));
  dz.addEventListener("drop", e => upload(e.dataTransfer.files));
})();
