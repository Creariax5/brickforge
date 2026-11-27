// Brick Forge Lab — interface (JS sans framework)
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null) el.append(k.nodeType ? k : document.createTextNode(k));
  return el;
};
const api = async (url, opts = {}) => {
  const r = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
};
const pct = (v) => (v == null ? "—" : Math.round(v * 100) + " %");
const KINDS = ["plate", "tile", "curved", "slope", "round", "wedge", "brick", "snot", "other"];
const KIND_FR = { plate: "plaque", tile: "tuile", curved: "pente courbe", slope: "pente", round: "ronde", wedge: "wedge", brick: "brique", snot: "SNOT", other: "autre" };
const kindVar = (k) => `var(--k-${["plate", "tile", "curved", "slope", "round", "wedge"].includes(k) ? k : "other"})`;
const DIR_ARROW = { N: "↑", S: "↓", E: "→", W: "←" };
const dirOf = (v) => {
  if (!v) return null;
  const [dx, dy] = v;
  return Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "E" : "W") : (dy > 0 ? "S" : "N");
};

const S = {
  subjects: [], subject: null, detail: null, runId: null,
  pred: [], evalr: null, gt: null, catalog: { parts: [], colors: [] },
  sel: new Set(), mode: "select", draft: [], tab: "assembler",
  view: { s: 1, x: 0, y: 0 }, img: { w: 1, h: 1 }, saveTimer: null, evalTimer: null,
};
// palette de travail d'abord, puis toutes les couleurs LDraw (LDConfig) pour les modèles officiels ou reconstruits
const colorName = (c) => (S.catalog.colors.find((x) => x.code === c) || {}).name || (S.ldcolors && S.ldcolors[c] && S.ldcolors[c].name) || (c == null ? "—" : String(c));
const colorHex = (c) => (S.catalog.colors.find((x) => x.code === c) || {}).hex || (S.ldcolors && S.ldcolors[c] && S.ldcolors[c].hex) || "#999";
const partInfo = (p) => S.catalog.parts.find((x) => x.part === p);

// ------------------------------------------------------------------ chargement

// Appelé une fois par shell.js ; la navigation (sujet, onglet) est pilotée par le routeur.
async function initApp() {
  [S.catalog, S.ldcolors] = await Promise.all([api("/api/catalog"), api("/api/ldcolors")]);
  $("#partList").replaceChildren(...S.catalog.parts.map((p) => h("option", { value: p.part }, `${p.part} — ${p.name}`)));
  bindUi();
  pollJobs();
}

async function loadSubjects() {
  S.subjects = await api("/api/subjects");
  if (window.renderNav) window.renderNav();
}

const SAM_TABS = ["annoter", "mesures", "historique"];
async function ensureSamData() {          // données SAM (vérité terrain, détections) : chargées à la demande
  if (S.samLoadedFor === S.subject + ":" + S.runId) return;
  S.gt = await api(`/api/subjects/${S.subject}/gt`);
  await loadRun();
  S.samLoadedFor = S.subject + ":" + S.runId;
}

async function selectSubject(name, runId) {
  S.subject = name;
  localStorage.setItem("bf.subject", name);
  S.detail = await api(`/api/subjects/${name}`);
  S.gt = { pieces: [] };
  S.samLoadedFor = null;
  S.pred = []; S.evalr = null;
  const main = S.detail.views.find((v) => v.name === S.detail.main_view);
  S.img = main ? { w: main.w, h: main.h, url: main.url } : { w: 1, h: 1, url: null };
  const runs = S.detail.runs.filter((r) => r.has_pieces);
  $("#runSelect").replaceChildren(
    ...(runs.length ? runs.map((r) => h("option", { value: r.id }, runLabel(r))) : [h("option", { value: "" }, "aucun lancement")]));
  S.runId = runId && runs.some((r) => r.id === runId) ? runId : (runs[0] || {}).id || null;
  $("#runSelect").value = S.runId || "";
  ["runMobile", "runVith"].forEach((id) => ($("#" + id).disabled = !main));
  S.sel.clear();
  S.view = null;
}

function runLabel(r) {
  const d = r.created ? r.created.replace("T", " ").slice(5, 16) : r.id;
  const f = r.metrics && r.metrics.f1 != null ? ` · F1 ${Math.round(r.metrics.f1 * 100)}` : "";
  return `${d} · ${r.model === "vit_h" ? "SAM complet" : "MobileSAM"}${r.label ? " · " + r.label : ""}${f}`;
}

async function loadRun() {
  S.pred = []; S.evalr = null;
  if (!S.runId) return;
  try {
    const r = await api(`/api/subjects/${S.subject}/runs/${S.runId}/pieces`);
    S.pred = r.pieces; S.evalr = r.eval;
  } catch (e) { /* lancement sans pièces */ }
}

async function refreshEval() {
  clearTimeout(S.evalTimer);
  S.evalTimer = setTimeout(async () => {
    await loadRun();
    renderOverlay(); renderEditor();
    if (S.tab === "mesures") renderMesures();
  }, 400);
}

async function renderAll() {
  if (SAM_TABS.includes(S.tab)) await ensureSamData();
  renderTab(S.tab);
}

// ------------------------------------------------------------------ annoter : vue et zoom

function fitView() {
  const wrap = $("#canvasWrap");
  if (!wrap.clientWidth || !wrap.clientHeight) return; // onglet caché : on recadrera à l'affichage
  const s = Math.min(wrap.clientWidth / S.img.w, wrap.clientHeight / S.img.h) * 0.96;
  S.view = { s, x: (wrap.clientWidth - S.img.w * s) / 2, y: (wrap.clientHeight - S.img.h * s) / 2 };
  applyView();
  renderOverlay();
}
function applyView() {
  if (!S.view) return;
  $("#stage").style.transform = `translate(${S.view.x}px, ${S.view.y}px) scale(${S.view.s})`;
}
function toImage(ev) {
  const r = $("#canvasWrap").getBoundingClientRect();
  return [(ev.clientX - r.left - S.view.x) / S.view.s, (ev.clientY - r.top - S.view.y) / S.view.s];
}

function renderAnnot() {
  const img = $("#mainImg"), stage = $("#stage"), empty = $("#annotEmpty");
  if (!S.img.url) {
    stage.hidden = true; empty.hidden = false;
    empty.replaceChildren(h("div", { class: "box" }, h("b", {}, "Pas de vue de dessus"),
      h("span", {}, "Ajoute un fichier dessus.jpeg dans le dossier du sujet pour pouvoir l'annoter.")));
    renderEditor(); return;
  }
  stage.hidden = false;
  stage.style.width = S.img.w + "px"; stage.style.height = S.img.h + "px";
  img.width = S.img.w; img.height = S.img.h;
  if (img.getAttribute("src") !== S.img.url) img.src = S.img.url;
  $("#overlay").setAttribute("viewBox", `0 0 ${S.img.w} ${S.img.h}`);
  if (!S.view) requestAnimationFrame(fitView); else applyView();
  if (!S.pred.length && !S.gt.pieces.length) {
    empty.hidden = false;
    empty.replaceChildren(h("div", { class: "box" }, h("b", {}, "Aucune détection pour ce sujet"),
      h("span", {}, "Lance un découpage avec les boutons en haut à droite : MobileSAM tourne sur ce PC en ~3 min, SAM complet sur le Mac Studio.")));
  } else empty.hidden = true;
  renderOverlay(); renderEditor();
}

function centroid(poly) {
  let x = 0, y = 0;
  for (const [a, b] of poly) { x += a; y += b; }
  return [x / poly.length, y / poly.length];
}
const pts = (poly) => poly.map((p) => p.join(",")).join(" ");
const svgEl = (tag, attrs) => {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
};

function renderOverlay() {
  const svg = $("#overlay");
  svg.replaceChildren();
  const showPred = $("#layerPred").checked, showGt = $("#layerGt").checked, showErr = $("#layerErr").checked, labels = $("#layerLabels").checked;
  const fs = Math.max(8, 10.5 / (S.view ? S.view.s : 1));
  if (showPred) for (const p of S.pred) if (p.polygon)
    svg.append(svgEl("polygon", { points: pts(p.polygon), class: "pred", style: `stroke:${kindVar(p.kind.replace("?", ""))}` }));
  if (showErr && S.evalr) {
    const gtById = Object.fromEntries(S.gt.pieces.map((g) => [g.id, g]));
    const attrErr = new Set(S.evalr.errors.filter((e) => !["manquée", "en trop"].includes(e.type)).map((e) => e.gt));
    for (const e of S.evalr.errors) {
      if (e.type === "manquée" && gtById[e.gt]) svg.append(svgEl("polygon", { points: pts(gtById[e.gt].polygon), class: "errpoly" }));
      if (e.type === "en trop" && S.pred[e.pred]) svg.append(svgEl("polygon", { points: pts(S.pred[e.pred].polygon), class: "errpoly fp" }));
    }
    for (const id of attrErr) if (gtById[id]) svg.append(svgEl("polygon", { points: pts(gtById[id].polygon), class: "errpoly attr" }));
  }
  if (showGt) for (const g of S.gt.pieces) {
    const k = g.kind || "other";
    const poly = svgEl("polygon", { points: pts(g.polygon), class: "gt" + (g.verified ? " verified" : "") + (S.sel.has(g.id) ? " sel" : ""),
      style: `fill:${kindVar(k)};stroke:${kindVar(k)}`, "data-id": g.id });
    poly.append(svgEl("title", {}));
    poly.firstChild.textContent = `${g.id} · ${g.part || "?"} · ${colorName(g.color)}`;
    svg.append(poly);
    if (labels) {
      const [cx, cy] = centroid(g.polygon);
      const t = svgEl("text", { x: cx, y: cy, class: "lbl" + (g.verified ? " ok" : ""), "text-anchor": "middle", "font-size": fs });
      t.textContent = (g.part || "?") + (g.dir ? " " + DIR_ARROW[g.dir] : "");
      svg.append(t);
    }
  }
  if (S.draft.length) {
    svg.append(svgEl("polyline", { points: pts(S.draft), class: "draft" }));
    for (const [x, y] of S.draft) svg.append(svgEl("circle", { cx: x, cy: y, r: 4 / S.view.s, style: "fill:var(--accent)" }));
  }
  const n = S.gt.pieces.length, v = S.gt.pieces.filter((g) => g.verified).length;
  $("#gtProgress").textContent = n ? `${v}/${n} vérifiées` : "";
}

// ------------------------------------------------------------------ annoter : inspecteur

function matchedPred(gid) {
  if (!S.evalr) return null;
  const pair = S.evalr.pairs.find((p) => p.gt === gid);
  return pair ? { ...S.pred[pair.pred], iou: pair.iou } : null;
}

function renderEditor() {
  const ed = $("#editor");
  if (!S.img.url) { ed.replaceChildren(); return; }
  if (!S.gt.pieces.length) {
    ed.replaceChildren(
      h("h3", {}, "Vérité terrain"),
      h("p", { class: "muted" }, "La vérité terrain est la liste des pièces réellement visibles sur la vue de dessus. Elle sert à mesurer chaque lancement."),
      S.runId
        ? h("button", { class: "btn primary", onclick: createGtFromRun }, "Créer à partir de ce lancement")
        : h("p", { class: "muted" }, "Lance d'abord un découpage."),
      h("p", { class: "muted" }, "Chaque détection devient une pièce à vérifier : corrige ce qui est faux, supprime ce qui n'est pas une pièce, dessine ce qui manque."));
    return;
  }
  const ids = [...S.sel];
  if (!ids.length) {
    const n = S.gt.pieces.length, v = S.gt.pieces.filter((g) => g.verified).length;
    ed.replaceChildren(
      h("h3", {}, "Vérité terrain ", h("span", { class: "badge" + (v === n ? " ok" : "") }, `${v}/${n}`)),
      h("p", { class: "muted" }, "Clique une pièce sur l'image pour la corriger, ou passe à la suivante à vérifier."),
      h("div", { class: "actions" },
        h("button", { class: "btn primary", onclick: nextUnverified }, "Pièce suivante à vérifier (N)"),
        h("button", { class: "btn", onclick: () => setMode("draw") }, "Dessiner une pièce manquante (D)")),
      S.runId ? h("button", { class: "btn small danger", onclick: () => createGtFromRun(true) }, "Repartir de ce lancement (écrase la vérité terrain)") : null);
    return;
  }
  if (ids.length > 1) {
    ed.replaceChildren(
      h("h3", {}, `${ids.length} pièces sélectionnées`),
      h("p", { class: "muted" }, "Fusionner les réunit en une seule pièce (contour englobant) : utile quand une pièce a été découpée en morceaux."),
      h("div", { class: "actions" },
        h("button", { class: "btn primary", onclick: mergeSel }, "Fusionner"),
        h("button", { class: "btn", onclick: () => { ids.forEach((id) => (gtPiece(id).verified = true)); changed(); } }, "Tout valider"),
        h("button", { class: "btn danger", onclick: deleteSel }, "Supprimer")));
    return;
  }
  const g = gtPiece(ids[0]);
  if (!g) { S.sel.clear(); renderEditor(); return; }
  const m = matchedPred(g.id);
  const info = partInfo(g.part);
  const cmp = (label, a, b, fmt = (x) => x ?? "—") => h("div", { class: "row" }, h("span", {}, label),
    h("span", { class: a === b || (Array.isArray(a) && JSON.stringify(a) === JSON.stringify(b)) ? "good" : "bad" }, fmt(b)));
  const partInput = h("input", { list: "partList", value: g.part || "", placeholder: "ex. 3069b", id: "f-part",
    onchange: (e) => {
      g.part = e.target.value.trim() || null;
      const pi = partInfo(g.part);
      if (pi) { g.kind = pi.kind; g.size = [...pi.size]; }
      changed(); renderEditor();
    } });
  ed.replaceChildren(
    h("h3", {}, `Pièce ${g.id}`, h("span", { class: "badge" + (g.verified ? " ok" : "") }, g.verified ? "vérifiée" : "à vérifier")),
    h("div", { class: "compare" },
      m ? [h("div", { class: "row" }, h("b", {}, "Détection appariée"), h("span", { class: "muted" }, `IoU ${m.iou}`)),
           cmp("Référence", g.part, m.part), cmp("Couleur", g.color, m.color, colorName),
           cmp("Taille", g.size, m.size, (s) => (s ? s.join("×") : "—")),
           g.dir || dirOf(m.slope_dir) ? cmp("Sens", g.dir, dirOf(m.slope_dir), (d) => (d ? DIR_ARROW[d] : "—")) : null,
           h("button", { class: "btn small", onclick: () => acceptPred(g, m) }, "Reprendre la détection")]
        : h("span", { class: "bad" }, "Aucune détection appariée : le moteur a raté cette pièce.")),
    h("label", { class: "field" }, h("span", {}, "Référence"), partInput,
      h("span", { class: "partname" }, info ? info.name + (info.known ? "" : " · inconnue du moteur") : (g.part ? "hors catalogue" : ""))),
    h("label", { class: "field" }, h("span", {}, "Type"),
      h("select", { id: "f-kind", onchange: (e) => { g.kind = e.target.value; changed(); } },
        KINDS.map((k) => h("option", { value: k, selected: g.kind === k }, KIND_FR[k])))),
    h("div", { class: "field" }, h("span", {}, "Taille (largeur × profondeur, en tenons)"),
      h("div", { class: "sizes" },
        h("input", { type: "number", min: 1, max: 16, value: (g.size || [1, 1])[0], id: "f-w", onchange: (e) => { g.size = [+e.target.value, (g.size || [1, 1])[1]]; changed(); } }),
        h("span", {}, "×"),
        h("input", { type: "number", min: 1, max: 16, value: (g.size || [1, 1])[1], id: "f-d", onchange: (e) => { g.size = [(g.size || [1, 1])[0], +e.target.value]; changed(); } }))),
    h("div", { class: "field" }, h("span", {}, "Couleur"),
      h("div", { class: "swatches" }, S.catalog.colors.map((c) =>
        h("button", { class: "swatch", style: `background:${c.hex}`, title: c.name, "aria-pressed": String(g.color === c.code),
          onclick: () => { g.color = c.code; changed(); renderEditor(); } }))),
      h("span", { class: "colorname" }, colorName(g.color))),
    h("div", { class: "field" }, h("span", {}, "Sens de descente (pentes)"),
      h("div", { class: "dirs" },
        h("span"), dirBtn(g, "N"), h("span"),
        dirBtn(g, "W"), h("button", { title: "aucun", "aria-pressed": String(!g.dir), onclick: () => { g.dir = null; changed(); renderEditor(); } }, "·"), dirBtn(g, "E"),
        h("span"), dirBtn(g, "S"), h("span"))),
    h("div", { class: "actions" },
      h("button", { class: "btn primary", onclick: () => { g.verified = !g.verified; changed(); if (g.verified) nextUnverified(); else renderEditor(); } },
        g.verified ? "Marquer à vérifier" : "Valider (V)"),
      h("button", { class: "btn", onclick: nextUnverified }, "Suivante (N)"),
      h("button", { class: "btn danger", onclick: deleteSel, title: "Ce n'est pas une pièce (Suppr)" }, "Supprimer")));
}
function dirBtn(g, d) {
  return h("button", { "aria-pressed": String(g.dir === d), title: d, onclick: () => { g.dir = d; changed(); renderEditor(); } }, DIR_ARROW[d]);
}

const gtPiece = (id) => S.gt.pieces.find((g) => g.id === id);
function newId() {
  let n = 1;
  const used = new Set(S.gt.pieces.map((g) => g.id));
  while (used.has("g" + n)) n++;
  return "g" + n;
}
function acceptPred(g, m) {
  Object.assign(g, { part: m.part, kind: m.kind.replace("?", ""), color: m.color, size: m.size ? [...m.size] : g.size, dir: dirOf(m.slope_dir) });
  changed(); renderEditor();
}
function select(id, add) {
  if (!add) S.sel.clear();
  if (id) { if (S.sel.has(id) && add) S.sel.delete(id); else S.sel.add(id); }
  renderOverlay(); renderEditor();
}
function nextUnverified() {
  const cur = [...S.sel][0];
  const list = S.gt.pieces;
  const start = Math.max(0, list.findIndex((g) => g.id === cur));
  for (let k = 1; k <= list.length; k++) {
    const g = list[(start + k) % list.length];
    if (!g.verified) { select(g.id); focusPiece(g); return; }
  }
  select(null);
}
function focusPiece(g) {
  if (!S.view) return;
  const [cx, cy] = centroid(g.polygon);
  const wrap = $("#canvasWrap");
  const sx = cx * S.view.s + S.view.x, sy = cy * S.view.s + S.view.y;
  if (sx < 40 || sy < 40 || sx > wrap.clientWidth - 40 || sy > wrap.clientHeight - 40) {
    S.view.x = wrap.clientWidth / 2 - cx * S.view.s;
    S.view.y = wrap.clientHeight / 2 - cy * S.view.s;
    applyView();
  }
}
function deleteSel() {
  if (!S.sel.size) return;
  S.gt.pieces = S.gt.pieces.filter((g) => !S.sel.has(g.id));
  S.sel.clear(); changed(); renderOverlay(); renderEditor();
}
function hull(points) {
  const p = points.map(([x, y]) => [x, y]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo = [], up = [];
  for (const q of p) { while (lo.length >= 2 && cross(lo.at(-2), lo.at(-1), q) <= 0) lo.pop(); lo.push(q); }
  for (const q of p.reverse()) { while (up.length >= 2 && cross(up.at(-2), up.at(-1), q) <= 0) up.pop(); up.push(q); }
  return lo.slice(0, -1).concat(up.slice(0, -1));
}
function mergeSel() {
  const items = S.gt.pieces.filter((g) => S.sel.has(g.id));
  if (items.length < 2) return;
  const big = items.reduce((a, b) => (a.polygon.length >= b.polygon.length ? a : b));
  big.polygon = hull(items.flatMap((g) => g.polygon));
  big.verified = false;
  S.gt.pieces = S.gt.pieces.filter((g) => !S.sel.has(g.id) || g === big);
  S.sel = new Set([big.id]);
  changed(); renderOverlay(); renderEditor();
}
async function createGtFromRun(force) {
  if (force === true && !window.__confirmForce) {
    window.__confirmForce = true;
    $("#saveState").textContent = "Clique encore pour confirmer l'écrasement";
    setTimeout(() => (window.__confirmForce = false), 4000);
    return;
  }
  await api(`/api/subjects/${S.subject}/gt/from-run/${S.runId}${force === true ? "?force=true" : ""}`, { method: "POST" });
  window.__confirmForce = false;
  S.gt = await api(`/api/subjects/${S.subject}/gt`);
  await loadRun(); await loadSubjects();
  renderAnnot();
}
function changed() {
  $("#saveState").textContent = "Modifié…";
  renderOverlay();
  clearTimeout(S.saveTimer);
  S.saveTimer = setTimeout(async () => {
    try {
      await api(`/api/subjects/${S.subject}/gt`, { method: "PUT", body: JSON.stringify(S.gt) });
      $("#saveState").textContent = "Enregistré";
      refreshEval();
    } catch (e) { $("#saveState").textContent = "Échec de l'enregistrement : " + e.message; }
  }, 500);
}

// ------------------------------------------------------------------ annoter : souris et clavier

function setMode(m) {
  S.mode = m; S.draft = [];
  $("#modeSelect").setAttribute("aria-pressed", String(m === "select"));
  $("#modeDraw").setAttribute("aria-pressed", String(m === "draw"));
  $("#canvasWrap").classList.toggle("drawing", m === "draw");
  renderOverlay();
}
function finishDraft() {
  if (S.draft.length >= 3) {
    const g = { id: newId(), polygon: S.draft.map(([x, y]) => [Math.round(x * 10) / 10, Math.round(y * 10) / 10]),
      kind: "plate", part: null, color: null, size: [1, 1], dir: null, verified: false, manual: true };
    S.gt.pieces.push(g);
    S.sel = new Set([g.id]);
    changed();
  }
  setMode("select");
  renderEditor();
}

function bindCanvas() {
  const wrap = $("#canvasWrap");
  let drag = null;
  wrap.addEventListener("wheel", (e) => {
    e.preventDefault();
    const r = wrap.getBoundingClientRect();
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    const k = Math.exp(-e.deltaY * 0.0015);
    const s = Math.min(12, Math.max(0.05, S.view.s * k));
    S.view.x = mx - ((mx - S.view.x) * s) / S.view.s;
    S.view.y = my - ((my - S.view.y) * s) / S.view.s;
    S.view.s = s; applyView(); renderOverlay();
  }, { passive: false });
  wrap.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 && e.button !== 1) return;
    drag = { x: e.clientX, y: e.clientY, vx: S.view.x, vy: S.view.y, moved: false, target: e.target };
    wrap.setPointerCapture(e.pointerId);
  });
  wrap.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) { drag.moved = true; wrap.classList.add("panning"); }
    if (drag.moved) { S.view.x = drag.vx + dx; S.view.y = drag.vy + dy; applyView(); }
  });
  wrap.addEventListener("pointerup", (e) => {
    wrap.classList.remove("panning");
    if (!drag) return;
    const d = drag; drag = null;
    if (d.moved) return;
    if (S.mode === "draw") { S.draft.push(toImage(e)); renderOverlay(); return; }
    const el = document.elementFromPoint(e.clientX, e.clientY);
    const id = el && el.dataset ? el.dataset.id : null;
    select(id || null, e.shiftKey);
  });
  wrap.addEventListener("dblclick", () => { if (S.mode === "draw") finishDraft(); });
  window.addEventListener("resize", () => S.view && fitView());
}

function bindKeys() {
  window.addEventListener("keydown", (e) => {
    if (S.tab !== "annoter" || ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
    const g = S.sel.size === 1 ? gtPiece([...S.sel][0]) : null;
    if (e.key === "v" || e.key === "V") { if (g) { g.verified = true; changed(); nextUnverified(); } }
    else if (e.key === "n" || e.key === "N") nextUnverified();
    else if (e.key === "Delete" || e.key === "Backspace") { deleteSel(); e.preventDefault(); }
    else if (e.key === "d" || e.key === "D") setMode(S.mode === "draw" ? "select" : "draw");
    else if (e.key === "s" || e.key === "S") setMode("select");
    else if (e.key === "Enter" && S.mode === "draw") finishDraft();
    else if (e.key === "Escape") { if (S.mode === "draw") setMode("select"); else select(null); }
    else if (e.key === "0") fitView();
    else if (g && DIR_ARROW[{ ArrowUp: "N", ArrowDown: "S", ArrowLeft: "W", ArrowRight: "E" }[e.key]]) {
      g.dir = { ArrowUp: "N", ArrowDown: "S", ArrowLeft: "W", ArrowRight: "E" }[e.key]; changed(); renderEditor(); e.preventDefault();
    }
  });
}

// ------------------------------------------------------------------ mesures

function kpi(label, v, sub) {
  return h("div", { class: "kpi" }, h("dt", {}, label), h("dd", {}, typeof v === "number" ? pct(v) : v ?? "—"),
    sub ? h("small", {}, sub) : null, typeof v === "number" ? h("div", { class: "bar" }, h("i", { style: `width:${v * 100}%` })) : null);
}

function renderMesures() {
  const el = $("#tab-mesures");
  const ev = S.evalr;
  if (!S.runId) { el.replaceChildren(h("p", { class: "muted" }, "Aucun lancement pour ce sujet.")); return; }
  if (!ev) {
    el.replaceChildren(h("div", { class: "notice" }, "Pas encore de vérité terrain pour ce sujet : crée-la dans l'onglet Annoter pour obtenir des mesures."),
      predStats());
    return;
  }
  const n = S.gt.pieces.length, v = S.gt.pieces.filter((g) => g.verified).length;
  const byType = {};
  for (const e of ev.errors) (byType[e.type] = byType[e.type] || []).push(e);
  const TYPE_FR = { "manquée": "manquées", "en trop": "en trop", part: "mauvaise réf.", color: "mauvaise couleur", size: "mauvaise taille", kind: "mauvais type", dir: "mauvais sens" };
  const confusion = {};
  for (const e of ev.errors.filter((e) => e.type === "part")) {
    const k = `${e.attendu || "?"} → ${e.obtenu || "?"}`;
    confusion[k] = (confusion[k] || 0) + 1;
  }
  el.replaceChildren(
    v < n ? h("div", { class: "notice" }, `La vérité terrain n'est vérifiée qu'à ${v}/${n} : les mesures sont provisoires (les pièces non vérifiées reprennent la détection d'origine, donc elles gonflent les scores).`) : null,
    h("dl", { class: "kpis" },
      kpi("Rappel", ev.recall, `${ev.n_matched}/${ev.n_gt} pièces retrouvées`),
      kpi("Précision", ev.precision, `${ev.n_matched}/${ev.n_pred} détections justes`),
      kpi("F1", ev.f1),
      kpi("Pièces parfaites", ev.perfect_rate, `${ev.perfect} avec bonne réf. et bonne couleur`),
      kpi("Bonne référence", ev.part_acc, "parmi les pièces retrouvées"),
      kpi("Bonne couleur", ev.color_acc),
      kpi("Bonne taille", ev.size_acc),
      kpi("Bon sens de pente", ev.dir_acc)),
    h("div", { class: "grid2" },
      h("div", { class: "card" }, h("h4", {}, "Erreurs (cliquer pour voir)"),
        h("ul", { class: "errlist" }, ev.errors.slice(0, 300).map((e) =>
          h("li", { onclick: () => gotoError(e) }, h("span", { class: "etype" }, TYPE_FR[e.type] || e.type),
            h("span", {}, e.gt ? e.gt + " · " : "", e.type === "en trop" ? `détection ${e.pred} (${e.obtenu || "?"})` :
              e.type === "manquée" ? `attendu ${e.attendu || "?"}` :
              `attendu ${fmtVal(e.type, e.attendu)}, obtenu ${fmtVal(e.type, e.obtenu)}`))))),
      h("div", { class: "card" }, h("h4", {}, "Répartition des erreurs"),
        h("div", { class: "bars" }, Object.entries(TYPE_FR).map(([t, fr]) => {
          const c = (byType[t] || []).length, max = Math.max(1, ...Object.values(byType).map((x) => x.length));
          return h("div", { class: "b" }, h("span", {}, fr), h("div", { class: "track" }, h("i", { class: "pr", style: `width:${(c / max) * 100}%; height:100%; top:0` })), h("span", { class: "muted" }, String(c)));
        })),
        h("h4", { style: "margin-top:16px" }, "Confusions de référence (attendu → obtenu)"),
        Object.keys(confusion).length
          ? h("table", { class: "data" }, h("tbody", {}, Object.entries(confusion).sort((a, b) => b[1] - a[1]).slice(0, 12).map(([k, c]) =>
              h("tr", {}, h("td", {}, k), h("td", { class: "num" }, String(c))))))
          : h("p", { class: "muted" }, "Aucune.")),
      predStats()));
}
function fmtVal(type, v) {
  if (type === "color") return colorName(v);
  if (type === "size") return v ? v.join("×") : "—";
  if (type === "dir") return v ? DIR_ARROW[v] : "aucun";
  return v ?? "—";
}
function predStats() {
  const count = (arr, f) => arr.reduce((m, x) => ((m[f(x)] = (m[f(x)] || 0) + 1), m), {});
  const pk = count(S.pred, (p) => p.kind.replace("?", ""));
  const gk = count(S.gt.pieces, (g) => g.kind || "other");
  const max = Math.max(1, ...Object.values(pk), ...Object.values(gk));
  return h("div", { class: "card" }, h("h4", {}, "Types : vérité terrain (gris) / détection (couleur)"),
    h("div", { class: "bars" }, KINDS.filter((k) => pk[k] || gk[k]).map((k) =>
      h("div", { class: "b" }, h("span", {}, KIND_FR[k]),
        h("div", { class: "track" }, h("i", { class: "gt", style: `width:${((gk[k] || 0) / max) * 100}%` }), h("i", { class: "pr", style: `width:${((pk[k] || 0) / max) * 100}%; background:${kindVar(k)}` })),
        h("span", { class: "muted" }, `${gk[k] || 0} / ${pk[k] || 0}`)))),
    h("p", { class: "muted", style: "margin:10px 0 0;font-size:12px" }, `${S.pred.length} détections, dont ${S.pred.filter((p) => !p.part).length} sans référence.`));
}
function gotoError(e) {
  location.hash = `#/sujet/${S.subject}/annoter`;
  if (e.gt) { select(e.gt); const g = gtPiece(e.gt); if (g) focusPiece(g); }
  else if (e.pred != null && S.pred[e.pred]) { $("#layerErr").checked = true; select(null); focusPiece(S.pred[e.pred]); }
}

// ------------------------------------------------------------------ historique

async function renderHistorique() {
  const el = $("#tab-historique");
  const runs = await api("/api/runs");
  const mine = runs.filter((r) => r.subject === S.subject).slice().reverse();
  const metricKeys = [["f1", "F1", "var(--accent)"], ["part_acc", "Bonne réf.", "var(--k-curved)"], ["color_acc", "Bonne couleur", "var(--k-plate)"], ["perfect_rate", "Parfaites", "var(--k-slope)"]];
  el.replaceChildren(
    h("div", { class: "card" }, h("h4", {}, `Évolution — ${S.subject.replace(/^lego_/, "")}`),
      mine.some((r) => r.metrics) ? chart(mine, metricKeys) : h("p", { class: "muted" }, "Les courbes apparaissent dès qu'une vérité terrain existe pour ce sujet.")),
    h("div", { class: "card", style: "margin-top:14px" }, h("h4", {}, "Tous les lancements"),
      h("div", { class: "tablewrap" }, h("table", { class: "data" },
        h("thead", {}, h("tr", {}, ["Date", "Sujet", "Découpage", "Étiquette", "Code", "Statut", "Détections", "Sans réf.", "F1", "Réf.", "Couleur", "Sens", "Parfaites", "Pièces 3D", "Durée", ""].map((t) => h("th", {}, t)))),
        h("tbody", {}, runs.map((r) => {
          const m = r.metrics || {};
          const dur = Object.values(r.timings || {}).reduce((a, b) => a + b, 0);
          return h("tr", { class: r.id === S.runId && r.subject === S.subject ? "current" : "" },
            h("td", {}, (r.created || "").replace("T", " ").slice(0, 16)),
            h("td", {}, r.subject.replace(/^lego_/, "")),
            h("td", {}, r.model === "vit_h" ? "SAM complet" : "MobileSAM", r.segments_from ? h("span", { class: "muted" }, " (réutilisé)") : null),
            h("td", {}, h("input", { value: r.label || "", placeholder: "—", onchange: (e) => api(`/api/subjects/${r.subject}/runs/${r.id}`, { method: "PATCH", body: JSON.stringify({ label: e.target.value }) }) })),
            h("td", { class: "muted" }, r.code || ""),
            h("td", {}, r.status || ""),
            h("td", { class: "num" }, r.n_pred ?? "—"), h("td", { class: "num" }, r.unknown ?? "—"),
            h("td", { class: "num" }, pct(m.f1)), h("td", { class: "num" }, pct(m.part_acc)), h("td", { class: "num" }, pct(m.color_acc)),
            h("td", { class: "num" }, pct(m.dir_acc)), h("td", { class: "num" }, pct(m.perfect_rate)),
            h("td", { class: "num" }, r.model_parts ?? "—"), h("td", { class: "num" }, dur ? dur + " s" : "—"),
            h("td", {}, h("button", { class: "btn small", onclick: () => { S.pendingRun = r.id; location.hash = `#/sujet/${r.subject}/annoter`; } }, "Ouvrir"), " ",
              h("button", { class: "btn small danger", onclick: async (e) => {
                if (e.currentTarget.dataset.armed) { await api(`/api/subjects/${r.subject}/runs/${r.id}`, { method: "DELETE" }); await selectSubject(S.subject); renderHistorique(); }
                else { e.currentTarget.dataset.armed = "1"; e.currentTarget.textContent = "Confirmer"; }
              } }, "Supprimer")));
        }))))));
}
function chart(runs, keys) {
  const W = 720, H = 230, L = 40, R = 12, T = 26, B = 30;
  const n = runs.length;
  const x = (i) => L + (n === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (n - 1));
  const y = (v) => T + (1 - v) * (H - T - B);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", width: "100%" });
  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    svg.append(svgEl("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "axis" }));
    const t = svgEl("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end" }); t.textContent = v * 100 + "%"; svg.append(t);
  }
  runs.forEach((r, i) => {
    const t = svgEl("text", { x: x(i), y: H - 12, "text-anchor": "middle" });
    t.textContent = (r.label || (r.created || "").slice(11, 16)).slice(0, 12); svg.append(t);
  });
  keys.forEach(([k, label, col], ki) => {
    const p = runs.map((r, i) => (r.metrics && r.metrics[k] != null ? [x(i), y(r.metrics[k])] : null)).filter(Boolean);
    if (p.length > 1) svg.append(svgEl("polyline", { points: p.map((q) => q.join(",")).join(" "), style: `fill:none;stroke:${col};stroke-width:2` }));
    for (const q of p) svg.append(svgEl("circle", { cx: q[0], cy: q[1], r: 3.5, style: `fill:${col}` }));
    const lx = L + 8 + ki * 130;
    svg.append(svgEl("rect", { x: lx, y: 0, width: 10, height: 10, style: `fill:${col}` }));
    const t = svgEl("text", { x: lx + 14, y: 9 }); t.textContent = label; svg.append(t);
  });
  return svg;
}

// ------------------------------------------------------------------ modèle 3D

let three = null;
async function renderModele() {
  const side = $("#modelSide"), box = $("#model3d");
  const run = S.detail.runs.find((r) => r.id === S.runId);
  if (!run || !run.has_model) {
    side.replaceChildren(h("div", { class: "card" }, h("p", { class: "muted" }, "Pas de modèle 3D pour ce lancement (il faut les vues dessus, profil et face).")));
    if (three) three.clear();
    return;
  }
  const m = await api(`/api/subjects/${S.subject}/runs/${S.runId}/model`);
  const K = m.kinds || {};
  side.replaceChildren(
    h("div", { class: "card" }, h("h4", {}, "Modèle reconstruit"), h("dl", {},
      h("div", {}, h("dt", {}, "Pièces"), h("dd", {}, m.nParts)), h("div", {}, h("dt", {}, "Références"), h("dd", {}, m.nRefs)),
      h("div", {}, h("dt", {}, "Emprise"), h("dd", {}, `${m.size[0]}×${m.size[1]}`)), h("div", {}, h("dt", {}, "Hauteur"), h("dd", {}, `${m.size[2]} pl.`)),
      h("div", {}, h("dt", {}, "Pentes"), h("dd", {}, (K.curved || 0) + (K.cheese || 0))), h("div", {}, h("dt", {}, "Tuiles / plaques"), h("dd", {}, `${K.tile || 0} / ${K.plate || 0}`)))),
    h("div", { class: "card" }, h("h4", {}, "Couleurs"), h("div", { class: "bars" }, m.palette.map((c) =>
      h("div", { class: "b" }, h("span", {}, c.name), h("div", { class: "track" }, h("i", { class: "pr", style: `width:${(c.n / m.palette[0].n) * 100}%;height:100%;top:0;background:${c.hex}` })), h("span", { class: "muted" }, String(c.n)))))),
    h("p", { class: "muted", style: "font-size:12px" }, "Ce modèle vient encore de la reconstruction par silhouettes. Les pièces reconnues sur la vue de dessus n'y sont pas encore intégrées."));
  if (!three) three = makeViewer(box);
  three.load(m);
}

function makeViewer(box) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  box.prepend(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 1000);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8170, 0.75));
  const sun = new THREE.DirectionalLight(0xffffff, 0.75); sun.position.set(20, 40, 30); scene.add(sun);
  const controls = new THREE.OrbitControls(camera, renderer.domElement); controls.enableDamping = true;
  let root = null;
  const PH = 0.4;
  const SH = {
    cheese: (D) => [[0, 0], [D, 0], [D, 0.8], [0, 0.07]],
    curved: (D) => { const p = [[0, 0], [D, 0], [D, 0.8], [D * 0.63, 0.8]]; for (let a = 1; a <= 10; a++) { const t = (a / 10) * Math.PI / 2; p.push([D * 0.63 * (1 - Math.sin(t)), 0.07 + 0.73 * Math.cos(t)]); } return p; },
  };
  function load(m) {
    if (root) scene.remove(root);
    root = new THREE.Group();
    const [W, L, H] = m.size;
    root.position.set(-W / 2, 0, -L / 2);
    scene.add(root);
    const mat = new THREE.MeshStandardMaterial({ roughness: 0.45 });
    const matS = new THREE.MeshStandardMaterial({ roughness: 0.4, side: THREE.DoubleSide });
    const col = new THREE.Color(), m4 = new THREE.Matrix4();
    const groups = {};
    m.pieces.forEach((p) => {
      const [kind, , , , di, dj, , , si] = p;
      const flat = kind === "plate" || kind === "tile";
      const key = flat ? "flat" : `${kind}:${si !== 0 ? dj : di}:${si !== 0 ? di : dj}`;
      (groups[key] = groups[key] || []).push(p);
    });
    for (const [key, items] of Object.entries(groups)) {
      let geo;
      if (key === "flat") { geo = new THREE.BoxGeometry(1, 1, 1); geo.translate(0.5, 0.5, 0.5); }
      else { const [kind, w, D] = key.split(":"); geo = new THREE.ExtrudeGeometry(new THREE.Shape(SH[kind](+D).map(([a, b]) => new THREE.Vector2(a, b))), { depth: +w, bevelEnabled: false }); }
      const mesh = new THREE.InstancedMesh(geo, key === "flat" ? mat : matS, items.length);
      items.forEach(([kind, i, j, k, di, dj, dk, c, si, sj], n) => {
        if (key === "flat") { m4.makeScale(di - 0.03, dk * PH - 0.015, dj - 0.03); m4.setPosition(i + 0.015, k * PH, j + 0.015); }
        else {
          const xa = new THREE.Vector3(-si, 0, -sj), ya = new THREE.Vector3(0, 1, 0), za = new THREE.Vector3().crossVectors(xa, ya);
          m4.makeBasis(xa, ya, za);
          m4.setPosition(i + (si > 0 || za.x < 0 ? di : 0), k * PH, j + (sj > 0 || za.z < 0 ? dj : 0));
        }
        mesh.setMatrixAt(n, m4); mesh.setColorAt(n, col.set(m.colorHex[c]));
      });
      root.add(mesh);
    }
    if (m.studs.length) {
      const st = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.3, 0.3, 0.17, 14), new THREE.MeshStandardMaterial({ roughness: 0.45 }), m.studs.length);
      m.studs.forEach(([i, j, k, c], n) => { m4.makeTranslation(i + 0.5, (k + 1) * PH + 0.085, j + 0.5); st.setMatrixAt(n, m4); st.setColorAt(n, col.set(m.colorHex[c])); });
      root.add(st);
    }
    const r = Math.max(W, L) * 1.6;
    camera.position.set(r * 0.65, r * 0.6, -r * 0.75);
    controls.target.set(0, H * PH * 0.4, 0); controls.update();
  }
  function resize() { const w = box.clientWidth, hh = box.clientHeight; if (!w || !hh) return; renderer.setSize(w, hh, false); camera.aspect = w / hh; camera.updateProjectionMatrix(); }
  new ResizeObserver(resize).observe(box);
  (function loop() { controls.update(); renderer.render(scene, camera); requestAnimationFrame(loop); })();
  return { load, clear: () => { if (root) scene.remove(root); root = null; } };
}

// ------------------------------------------------------------------ vues

function renderVues() {
  const el = $("#tab-vues");
  const figs = S.detail.views.map((v) => ({ src: v.thumb || v.url, full: v.url, cap: v.name }));
  if (S.runId) {
    figs.push({ src: `/thumb/out/runs/${S.subject}/${S.runId}/segments.jpg?w=720`, full: `/runs/${S.subject}/${S.runId}/segments.jpg`, cap: "découpage SAM (archive)" });
    figs.push({ src: `/thumb/out/runs/${S.subject}/${S.runId}/pieces.jpg?w=720`, full: `/runs/${S.subject}/${S.runId}/pieces.jpg`, cap: "pièces reconnues par règles (archive)" });
  }
  el.replaceChildren(h("div", { class: "views" }, figs.map((f) =>
    h("figure", { onclick: () => openLightbox(f.full || f.src) }, h("img", { src: f.src, alt: f.cap, loading: "lazy", onerror: (e) => e.target.closest("figure").remove() }), h("figcaption", {}, f.cap)))));
}
function openLightbox(src) {
  const lb = $("#lightbox");
  lb.replaceChildren(h("img", { src, alt: "" }));
  lb.hidden = false;
}

// ------------------------------------------------------------------ tâches

let lastJobsState = "";
async function pollJobs() {
  let jobs = [];
  try { jobs = await api("/api/jobs"); } catch (e) { /* serveur redémarré */ }
  const bar = $("#jobbar");
  const active = jobs.filter((j) => ["en cours", "en attente"].includes(j.status));
  const recent = jobs.filter((j) => !active.includes(j)).slice(0, 2);
  const show = active.concat(recent);
  bar.hidden = !show.length;
  bar.replaceChildren(...show.map((j) => {
    const cls = j.status === "terminé" ? "ok" : j.status === "échec" ? "ko" : "run";
    return h("div", { class: "job" },
      h("span", { class: "st " + cls }, j.status),
      h("span", {}, h("b", {}, `#${j.id} ${j.subject.replace(/^lego_/, "")}`), ` · ${j.model === "vit_h" ? "SAM complet" : "MobileSAM"} · ${j.step}`),
      h("span", { class: "muted" }, j.elapsed ? j.elapsed + " s" : ""),
      h("details", {}, h("summary", { class: "muted" }, "journal"), h("pre", {}, j.log.join("\n"))));
  }));
  const state = JSON.stringify(jobs.map((j) => [j.id, j.status]));
  if (lastJobsState && state !== lastJobsState) {
    const done = jobs.find((j) => j.status === "terminé" && !lastJobsState.includes(`[${j.id},"terminé"]`));
    await loadSubjects();
    if (done && done.subject === S.subject) { await selectSubject(S.subject, done.run); renderAll(); }
  }
  lastJobsState = state;
  setTimeout(pollJobs, active.length ? 1500 : 5000);
}
async function startRun(model) {
  try {
    await api("/api/runs", { method: "POST", body: JSON.stringify({ subject: S.subject, model, reuse: $("#reuseSeg").checked, label: $("#runLabel").value }) });
    $("#runLabel").value = "";
    lastJobsState = lastJobsState || "[]";
    setTimeout(pollJobs, 300);
  } catch (e) { alertBar(e.message); }
}
function alertBar(msg) {
  const bar = $("#jobbar"); bar.hidden = false;
  bar.prepend(h("div", { class: "job" }, h("span", { class: "st ko" }, "erreur"), h("span", {}, msg), h("span")));
}

// ------------------------------------------------------------------ onglets et liaisons

function renderTab(t) {
  if (t === "annoter") renderAnnot();
  if (t === "assembler") renderAssembler();
  if (t === "comparer") renderComparer();
  if (t === "entrainement") renderTraining();
  if (t === "mesures") renderMesures();
  if (t === "historique") renderHistorique();
  if (t === "modele") renderModele();
  if (t === "vues") renderVues();
}

function bindUi() {
  $("#runSelect").addEventListener("change", async (e) => { S.runId = e.target.value; S.samLoadedFor = null; renderAll(); });
  $("#runMobile").addEventListener("click", () => startRun("mobile"));
  $("#runVith").addEventListener("click", () => startRun("vit_h"));
  $("#modeSelect").addEventListener("click", () => setMode("select"));
  $("#modeDraw").addEventListener("click", () => setMode("draw"));
  $("#zoomReset").addEventListener("click", fitView);
  ["layerPred", "layerGt", "layerErr", "layerLabels"].forEach((id) => $("#" + id).addEventListener("change", renderOverlay));
  $("#lightbox").addEventListener("click", () => ($("#lightbox").hidden = true));
  bindCanvas(); bindKeys();
}


