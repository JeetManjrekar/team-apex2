/* BauBuddy · "Geld & Zeit" panel (GET /api/costs, backend/core/cost_model.py).
   German by design (COST_MODEL.md §6): big numbers with their range, the top-3 ranking with one action each, every
   number expandable to its explanation, assumptions and sources. Footer: "Schätzung, intern · … · kein Nachtragsbetrag".
   Internal only: nothing here ever goes into an outgoing document. */
(() => {
  "use strict";
  const NW = window.NW; if (!NW) return;
  const q = (s, r = document) => r.querySelector(s), qa = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = NW.esc, api = NW.api;
  const DE = (() => { try { return localStorage.getItem("nw-lang") === "de"; } catch { return false; } })();
  const L = (en, de) => (DE ? de : en);
  const LOC = DE ? "de-DE" : "en-GB";
  const EUR = x => (x == null ? "––" : "€" + new Intl.NumberFormat(LOC, { maximumFractionDigits: 0 }).format(x));
  const K = x => (x == null ? "––" : x >= 10000 ? `€${new Intl.NumberFormat(LOC, { maximumFractionDigits: 0 }).format(x / 1000)}k` : EUR(x));
  const DEC = (x, d = 1) => new Intl.NumberFormat(LOC, { maximumFractionDigits: d, minimumFractionDigits: d }).format(x);
  const BAND = { low: "ok", medium: "warn", high: "bad" };
  const bandOf = x => (x >= 25000 ? "high" : x >= 5000 ? "medium" : "low");
  let last = null;

  function kpi(title, value, sub, band, extra = "") {
    return `<div class="cm-kpi ${band ? "b-" + BAND[band] : ""}"><span>${esc(title)}</span><b>${value}</b><small>${sub}</small>${extra}</div>`;
  }
  function row(x, i) {
    const band = BAND[x.band] || "ok";
    const act = x.action ? `<button class="s cm-act" data-act="${esc(x.key)}">${esc(x.action)}</button>` : (x.accepted ? `<span class="cm-done">✓ ${L("accepted", "angenommen")}</span>` : "");
    return `<div class="cm-row b-${band}" data-k="${esc(x.key)}">
      <div class="cm-rank">${i + 1}</div>
      <div class="cm-main"><b>${esc(x.title)}</b><span>${EUR(x.expected_eur)} <em>(${EUR(x.low_eur)} – ${EUR(x.high_eur)})</em></span></div>
      ${act}<button class="cm-more" aria-label="${L("Explanation", "Erklärung")}">ⓘ</button>
      <div class="cm-why">${esc(x.explanation)}<ul>${(x.assumptions || []).map(a => `<li>${esc(a)}</li>`).join("")}</ul>
        <code>${esc((x.sources || []).join(" · "))}</code></div></div>`;
  }
  function html(s) {
    const nd = s.nachtrag_documented, no = s.nachtrag_open, ia = s.idle_avoided, iv = s.idle_avoidable, d = s.delay_open, doc = s.documentation;
    const nVal = nd.count ? nd : no;
    return `<div class="cm card">
      <div class="cm-h"><div><b>${L("Money &amp; time", "Geld &amp; Zeit")}</b><span>${L("today", "heute")} · ${esc(s.as_of)}</span></div><span class="cm-tag">${esc(s.label)}</span></div>
      <div class="cm-kpis">
        ${kpi(nd.count ? L("Change order potential documented", "Nachtrag-Potenzial dokumentiert") : L("Change order potential open", "Nachtrag-Potenzial offen"), K(nVal.expected_eur),
              nd.count ? `${EUR(nd.low_eur)} – ${EUR(nd.high_eur)}` : (no.count ? L("not documented yet", "noch nicht dokumentiert") : L("no deviation measured", "keine Abweichung gemessen")),
              nVal.expected_eur ? bandOf(nVal.expected_eur) : null)}
        ${kpi(ia.count ? L("Idle cost avoided", "Stillstand vermieden") : L("Idle cost avoidable", "Stillstand vermeidbar"), K(ia.count ? ia.expected_eur : iv.expected_eur),
              iv.count || ia.count ? L(`stoppage costs about ${EUR(iv.cost_eur)}`, `Stillstand kostet ca. ${EUR(iv.cost_eur)}`) : L("no stoppage reported", "kein Stillstand gemeldet"), null)}
        ${kpi(L("Delay risk open", "Terminrisiko offen"), d ? K(d.expected_eur) : "––",
              d ? `+${DEC(d.slip_days.exp)} ${L("working days", "AT")} · ${EUR(d.low_eur)} – ${EUR(d.high_eur)}` : L("no delay forecast", "kein Verzug prognostiziert"),
              d ? bandOf(d.expected_eur) : null)}
        ${kpi(L("Paperwork time", "Doku-Zeit"), doc.docs ? `${DEC(doc.assisted_min, 0)} <i>${L("instead of", "statt")}</i> ${doc.manual_min} min` : "––",
              doc.docs ? `${doc.docs} ${L("docs", "Dok.")} · ${EUR(doc.saved_eur)} ${L("saved", "gespart")} · ${L("AI", "KI")} ${doc.ai_cost_total_eur != null ? "€" + DEC(doc.ai_cost_total_eur, 3) : L("not recorded", "nicht erfasst")}`
                       : L("no documents yet", "noch keine Dokumente"), null)}
      </div>
      <div class="cm-top">
        ${(s.top || []).map(row).join("") || `<div class="mut pad">${L("Nothing open.", "Nichts offen.")}</div>`}</div></div>`;
  }
  function bind(root) {
    qa(".cm-more", root).forEach(b => b.onclick = () => b.closest(".cm-row").classList.toggle("open"));
    qa("[data-act]", root).forEach(b => b.onclick = async () => {
      const key = b.dataset.act;
      if (key.startsWith("idle:")) {
        b.disabled = true;
        try { await api("/api/costs/decide", { json: { key, accepted: true } }); window.SFX?.done(L("Reassignment accepted", "Umsetzung angenommen"), b); } catch (e) { b.disabled = false; return; }
        return refresh();
      }
      if (key.startsWith("nachtrag:")) {
        const id = last?.items?.nachtrag?.find(x => x.key === key)?.doc_id;
        if (id) return NW.openDocInTab(id);
        NW.TAB("command"); const inp = q("#bbInp"); if (inp) { const n = key.replace(/\D/g, "").replace(/^0/, ""); inp.value = L(`Pile ${n}: rock, check change order`, `Pfahl ${n}: Fels, Nachtrag prüfen`); inp.focus(); }
        return;
      }
      if (key.startsWith("delay:")) NW.TAB("plan");
    });
  }
  async function refresh(target) {
    try { last = await api("/api/costs"); } catch { return null; }
    qa(".cm-host").forEach(h => { h.innerHTML = html(last); bind(h); });
    if (target) { target.innerHTML = html(last); bind(target); }
    pins();
    return last;
  }
  function pins() {
    if (!last || !window.SiteTwin?.setCostPins) return;
    // one delay badge: the largest milestone risk (site overhead accrues once), where its chain starts
    const delay = (last.items.delay || []).filter(x => x.status === "ok" && x.zone).sort((a, b) => b.expected_eur - a.expected_eur)[0];
    const items = [...(last.items.nachtrag || []), ...(delay ? [delay] : []), ...(last.items.idle || [])]
      .filter(x => x.status === "ok" && x.zone);
    window.SiteTwin.setCostPins(items.map(x => ({ zone: x.zone, band: x.band, kind: x.kind, text: `${x.kind === "nachtrag" ? L("Change order", "Nachtrag") : x.kind === "delay" ? L("Delay", "Termin") : L("Idle", "Stillstand")} ~${K(x.expected_eur)}` })));
  }

  // dashboard host: above the existing dashboard content
  function mount() {
    const dash = q("#dash"); if (!dash || q(".cm-host", dash)) return !!dash;
    const host = document.createElement("div"); host.className = "cm-host";
    dash.prepend(host);
    refresh();
    return true;
  }
  if (!mount()) addEventListener("load", () => setTimeout(mount, 300));
  document.addEventListener("click", e => { if (e.target.closest?.('#nav [data-t="dash"]')) setTimeout(refresh, 200); }, true);
  setInterval(() => { if (q("#dash")?.classList.contains("on")) refresh(); }, 20000);
  document.addEventListener("sitetwin-ready", () => setTimeout(pins, 1500));
  window.Costs = { refresh, html, get last() { return last; } };
})();
