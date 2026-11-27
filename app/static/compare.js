// Brick Forge Lab — onglet Comparer : rendu du modèle superposé aux vues Gemini, scores, historique
"use strict";

let cmpPoll = null;
const VIEW_FR = { concept: "concept", dessus: "dessus", profil: "profil", face: "face", dos: "dos", dessous: "dessous" };
const pill = (v, good, mid, fmt) => h("span", { class: "pill " + (v >= good ? "good" : v >= mid ? "mid" : "bad") }, fmt(v));
const pillLow = (v, good, mid, fmt) => h("span", { class: "pill " + (v <= good ? "good" : v <= mid ? "mid" : "bad") }, fmt(v));

async function renderComparer() {
  const el = $("#tab-comparer");
  const d = await api(`/api/subjects/${S.subject}/compare`);
  const t = Date.now();
  const running = d.status === "en cours";
  const sm = d.summary;
  const head = h("div", { class: "cmp-head" },
    h("button", { class: "btn primary", disabled: running, onclick: () => startCompare(false) }, running ? "Comparaison en cours… (~30 s)" : "Comparer le modèle actuel"),
    h("button", { class: "btn small", disabled: running, onclick: () => startCompare(true), title: "Recherche des caméras depuis zéro (plus long)" }, "Recaler les caméras"),
    d.status && d.status.startsWith("échec") ? h("span", { class: "bad" }, d.status) : null,
    sm ? h("span", { class: "muted" }, `Dernière comparaison : ${(d.updated || "").replace("T", " ").slice(0, 16)} · ${d.n_parts} pièces`) : null);
  if (!sm) {
    el.replaceChildren(head, h("p", { class: "muted" }, "Pas encore de comparaison pour ce sujet. Le modèle de l'onglet Assembler est rendu avec la même caméra que chaque vue Gemini (calée automatiquement), puis comparé."));
  } else {
    const hist = d.history || [];
    const prev = hist.length > 1 ? hist[hist.length - 2] : null;
    const delta = (k, inv) => {
      if (!prev) return null;
      const dv = sm[k] - prev[k];
      if (Math.abs(dv) < 1e-3) return h("small", { class: "muted" }, " =");
      const good = inv ? dv < 0 : dv > 0;
      return h("small", { style: `color:var(--${good ? "ok" : "bad"})` }, ` ${dv > 0 ? "+" : ""}${k === "contour_pct" ? dv.toFixed(2) : Math.round(dv * 100)}`);
    };
    el.replaceChildren(head,
      h("dl", { class: "kpis" },
        h("div", { class: "kpi" }, h("dt", {}, "Silhouette (moyenne)"), h("dd", {}, Math.round(sm.silhouette * 100) + " %", delta("silhouette")), h("small", {}, "recouvrement des formes, 100 % = identique")),
        h("div", { class: "kpi" }, h("dt", {}, "Écart de contour"), h("dd", {}, sm.contour_pct.toFixed(2) + " %", delta("contour_pct", true)), h("small", {}, "distance moyenne des bords, en % de la taille")),
        h("div", { class: "kpi" }, h("dt", {}, "Couleur (indicatif)"), h("dd", {}, Math.round(sm.couleur_ok * 100) + " %", delta("couleur_ok")), h("small", {}, "zones dont la famille de couleur correspond"))),
      h("div", { class: "cmp-legend", style: "margin-bottom:10px" },
        h("span", {}, h("i", { style: "background:#e62828" }), "sur la photo, absent du modèle"),
        h("span", {}, h("i", { style: "background:#1e78e6" }), "dans le modèle, absent de la photo"),
        h("span", {}, h("i", { style: "background:#ffa500" }), "bonne forme, couleur différente")),
      h("div", { class: "cmp-grid" }, Object.entries(d.views).map(([v, r]) => cmpCard(v, r, t))));
  }
  clearTimeout(cmpPoll);
  if (running) cmpPoll = setTimeout(() => S.tab === "comparer" && renderComparer(), 2500);
}

function cmpCard(view, r, t) {
  const base = `/compare/${S.subject}/${view}`;
  const photo = h("img", { src: `${base}_photo.jpg?t=${t}`, alt: "Vue Gemini " + view });
  const rend = h("img", { class: "top", src: `${base}_render.png?t=${t}`, alt: "Rendu du modèle", style: "opacity:.5" });
  const diff = h("img", { class: "top", src: `${base}_diff.png?t=${t}`, alt: "Carte des différences", hidden: true });
  const slider = h("input", { type: "range", min: 0, max: 100, value: 50, "aria-label": "Transparence du rendu",
    oninput: (e) => (rend.style.opacity = e.target.value / 100) });
  const diffChk = h("input", { type: "checkbox", onchange: (e) => { diff.hidden = !e.target.checked; rend.hidden = e.target.checked; slider.disabled = e.target.checked; } });
  return h("article", { class: "cmp-card" },
    h("header", {}, h("b", {}, VIEW_FR[view] || view),
      h("span", {}, "silhouette ", pill(r.silhouette, 0.8, 0.65, (v) => Math.round(v * 100) + " %"), " contour ",
        pillLow(r.contour_pct, 1.5, 3, (v) => v.toFixed(1) + " %"), " couleur ", pill(r.couleur_ok, 0.7, 0.5, (v) => Math.round(v * 100) + " %"))),
    h("div", { class: "cmp-stage" }, photo, rend, diff),
    h("div", { class: "cmp-ctrl" }, h("span", {}, "photo"), slider, h("span", {}, "modèle"),
      h("label", { class: "chk" }, diffChk, " différences"),
      h("span", {}, `manque ${r.manque_pct} % · en trop ${r.en_trop_pct} %`)));
}

async function startCompare(refit) {
  try { await api(`/api/subjects/${S.subject}/compare${refit ? "?refit=true" : ""}`, { method: "POST" }); }
  catch (e) { alertBar(e.message); }
  renderComparer();
}
