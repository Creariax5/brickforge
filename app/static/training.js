// Brick Forge Lab — onglet Entraînement : suivi en direct (Mac Studio) et galerie des données
"use strict";

let trTimer = null, trSamples = null, trSeed = 1;

async function renderTraining() {
  const el = $("#tab-entrainement");
  if (!el.dataset.ready) {
    el.dataset.ready = "1";
    el.replaceChildren(
      h("div", { id: "trStatus" }, h("p", { class: "muted" }, "Connexion au Mac Studio…")),
      h("div", { class: "card", style: "margin-top:14px" },
        h("div", { style: "display:flex;align-items:center;gap:10px;margin-bottom:10px" },
          h("h4", { style: "margin:0" }, "Données d'entraînement (cliquer : étiquettes vraies et prédictions du modèle)"),
          h("button", { class: "btn small", onclick: () => { trSeed++; trSamples = null; loadSamples(); } }, "Autres exemples")),
        h("div", { class: "tr-grid", id: "trGrid" })),
      h("div", { class: "card", style: "margin-top:14px" },
        h("div", { style: "display:flex;align-items:center;gap:10px;margin-bottom:6px;flex-wrap:wrap" },
          h("h4", { style: "margin:0" }, "Le vrai test : prédictions sur les vues Gemini de la tortue"),
          h("button", { class: "btn small primary", onclick: (e) => geminiPredictions(e.currentTarget) }, "Analyser les 6 vues"),
          h("span", { class: "muted", id: "trGeminiNote", style: "font-size:12px" })),
        h("p", { class: "muted", style: "margin:0 0 10px;font-size:13px" }, "Le modèle n'a jamais vu de photo : seulement nos rendus. Ce test montre s'il reconnaît les pièces dans les images de Gemini."),
        h("div", { class: "views", id: "trGemini" })),
      h("div", { class: "card", style: "margin-top:14px", id: "trPlots" }));
    loadSamples();
  }
  pollTraining();
}

async function pollTraining() {
  clearTimeout(trTimer);
  if (S.tab !== "entrainement") return;
  try { drawStatus(await api("/api/train/status")); }
  catch (e) { $("#trStatus").replaceChildren(h("div", { class: "notice" }, e.message)); }
  trTimer = setTimeout(pollTraining, 4000);
}

// ---------------------------------------------------------------- tableau de bord d'entraînement
// Chaque chiffre a son explication : ce qu'il mesure, comment le lire, ce qu'on en conclut.

const METRICS = [
  { key: "metrics/mAP50(M)", label: "Note globale (mAP50)", color: "var(--accent)",
    what: "La note de synthèse du détecteur. Elle combine la précision et le rappel pour chaque référence de pièce, puis fait la moyenne sur les 45 références. Une pièce compte comme trouvée si le contour prédit recouvre le vrai contour à au moins 50 %.",
    read: "0 % = ne trouve rien, 100 % = parfait. C'est le chiffre à suivre en premier." },
  { key: "metrics/mAP50-95(M)", label: "Finesse des contours (mAP50-95)", color: "var(--k-curved)",
    what: "La même note, mais en exigeant des contours de plus en plus précis (recouvrement de 50 % jusqu'à 95 %). Elle mesure si les bords des pièces tombent au bon endroit.",
    read: "Toujours plus basse que la note globale. Importante pour nous : un contour précis permet de placer la pièce au bon tenon." },
  { key: "metrics/precision(M)", label: "Précision", color: "var(--k-plate)",
    what: "Parmi les pièces que le modèle annonce, la part qui est juste (bonne référence, bon endroit).",
    read: "Basse = il invente des pièces ou se trompe de référence." },
  { key: "metrics/recall(M)", label: "Rappel", color: "var(--k-slope)",
    what: "Parmi les pièces réellement présentes dans l'image, la part que le modèle retrouve.",
    read: "Bas = il rate des pièces (souvent les petites ou celles à moitié cachées)." },
];
const LOSSES = [
  { key: "cls_loss", label: "Erreur de référence", what: "Le modèle se trompe-t-il de pièce ? (pente 2×2 au lieu de 4×1, plaque 1×3 au lieu de 1×4…). C'est l'erreur la plus importante pour nous." },
  { key: "seg_loss", label: "Erreur de contour", what: "Écart entre le contour dessiné par le modèle et le vrai contour de la pièce, au pixel près." },
  { key: "box_loss", label: "Erreur de position", what: "Écart sur le rectangle qui entoure chaque pièce : position et taille." },
  { key: "dfl_loss", label: "Finesse des bords", what: "Terme technique : à quel point le modèle est sûr de l'emplacement exact de chaque bord du rectangle." },
];
const pctf = (v) => (v == null || !isFinite(v) ? "—" : (v * 100).toFixed(1) + " %");
const hms = (s) => { if (s == null) return "—"; s = Math.round(s); const h_ = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return h_ ? `${h_} h ${String(m).padStart(2, "0")}` : `${m} min`; };

function trendVerdict(vals) {
  const v = vals.filter((x) => x != null && isFinite(x));
  if (v.length < 3) return { txt: "Pas encore assez de passes pour juger la tendance.", cls: "" };
  const k = Math.min(4, v.length - 1);
  const slope = (v[v.length - 1] - v[v.length - 1 - k]) / k;
  if (slope > 0.01) return { txt: `Progresse nettement : +${(slope * 100).toFixed(1)} point par passe en moyenne sur les ${k} dernières passes.`, cls: "good" };
  if (slope > 0.002) return { txt: `Progresse lentement : +${(slope * 100).toFixed(1)} point par passe. Les gains ralentissent, c'est normal en fin d'entraînement.`, cls: "mid" };
  if (slope > -0.003) return { txt: "Plafonne : presque plus de progrès d'une passe à l'autre. Continuer l'entraînement n'apportera plus grand-chose avec ces données.", cls: "mid" };
  return { txt: `Recule : ${(slope * 100).toFixed(1)} point par passe. À surveiller (apprentissage par cœur ou instabilité).`, cls: "bad" };
}

function overfitVerdict(ep) {
  const tr = ep.map((e) => e["train/cls_loss"]), va = ep.map((e) => e["val/cls_loss"]);
  if (ep.length < 5) return { txt: "Trop tôt pour savoir s'il apprend par cœur.", cls: "" };
  const minVa = Math.min(...va), iMin = va.indexOf(minVa), last = va[va.length - 1];
  const trDown = tr[tr.length - 1] < tr[Math.max(0, tr.length - 4)];
  if (last > minVa * 1.05 && trDown && iMin < va.length - 2)
    return { txt: `Attention : l'erreur sur les images jamais vues remonte depuis la passe ${iMin + 1}, alors qu'elle baisse sur les images d'entraînement. Le modèle commence à apprendre par cœur.`, cls: "bad" };
  return { txt: "Sain : l'erreur baisse aussi sur les images jamais vues. Le modèle généralise, il n'apprend pas par cœur.", cls: "good" };
}

function lineChart({ series, n, ymin = 0, ymax = null, fmt = (v) => v.toFixed(2), marks = [], height = 200, livePoint = null, width = 760 }) {
  const W = width, H = height, L = 48, R = 14, T = 24, B = 24;
  const all = series.flatMap((s) => s.values.filter((v) => v != null && isFinite(v))).concat(livePoint ? [livePoint.value] : []);
  const hi = ymax != null ? ymax : Math.max(...all, 1e-3) * 1.08;
  const lo = ymin;
  const N = Math.max(n, 2);
  const x = (i) => L + (i * (W - L - R)) / (N - 1);
  const y = (v) => T + (1 - (v - lo) / (hi - lo || 1)) * (H - T - B);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", width: "100%" });
  for (const f of [0, 0.25, 0.5, 0.75, 1]) {
    const v = lo + (hi - lo) * f;
    svg.append(svgEl("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "axis" }));
    const t = svgEl("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end" }); t.textContent = fmt(v); svg.append(t);
  }
  for (const m of marks) {
    svg.append(svgEl("line", { x1: x(m.i), x2: x(m.i), y1: T, y2: H - B, style: "stroke:var(--muted);stroke-dasharray:3 3" }));
    const t = svgEl("text", { x: x(m.i) + 4, y: T + 10 }); t.textContent = m.label; svg.append(t);
  }
  for (let i = 0; i < n; i += Math.max(1, Math.ceil(n / 10))) {
    const t = svgEl("text", { x: x(i), y: H - 6, "text-anchor": "middle" }); t.textContent = i + 1; svg.append(t);
  }
  series.forEach((s, si) => {
    const pts = s.values.map((v, i) => (v != null && isFinite(v) ? [x(i), y(v)] : null)).filter(Boolean);
    if (pts.length > 1) svg.append(svgEl("polyline", { points: pts.map((p) => p.join(",")).join(" "), style: `fill:none;stroke:${s.color};stroke-width:2;${s.dash ? "stroke-dasharray:5 4" : ""}` }));
    if (pts.length) { const p = pts[pts.length - 1]; svg.append(svgEl("circle", { cx: p[0], cy: p[1], r: 3.5, style: `fill:${s.color}` })); }
    const lx = L + si * Math.min(175, (W - L) / Math.max(series.length, 1));
    svg.append(svgEl("line", { x1: lx, x2: lx + 14, y1: 8, y2: 8, style: `stroke:${s.color};stroke-width:2;${s.dash ? "stroke-dasharray:4 3" : ""}` }));
    const t = svgEl("text", { x: lx + 18, y: 12 }); t.textContent = s.label; svg.append(t);
  });
  if (livePoint) {
    const cx = x(livePoint.i), cy = y(livePoint.value);
    svg.append(svgEl("circle", { cx, cy, r: 5, class: "livept", style: `fill:${livePoint.color}` }));
    const t = svgEl("text", { x: cx + 8, y: cy - 6 }); t.textContent = "en cours"; svg.append(t);
  }
  return svg;
}

function drawStatus(st) {
  const ep = st.epochs || [];
  const live = st.live;
  const n = st.epochs_total || ep.length;
  const last = ep[ep.length - 1] || {}, prev = ep[ep.length - 2] || {};
  const marks = (st.segments || []).slice(1).map((sg) => ({ i: sg.start, label: `reprise (lots de ${sg.batch !== "?" ? sg.batch : 8})` }));
  const cur = st.current_epoch || ep.length;
  const end = st.eta_s ? new Date(Date.now() + st.eta_s * 1000) : null;

  // A. en direct
  const liveCard = h("section", { class: "dash-live" },
    h("div", { class: "dl-head" }, h("span", { class: "phase" }, st.phase),
      live ? h("b", {}, live.stage === "validation" ? `Passe ${cur} sur ${n} · contrôle sur les images de validation` : `Passe ${cur} sur ${n}`) : h("b", {}, `${ep.length} passes terminées`),
      h("span", { class: "muted" }, "mis à jour toutes les 4 s")),
    live ? h("div", { class: "dl-bar" }, h("i", { style: `width:${live.pct}%` }), h("span", {}, `${live.stage === "validation" ? "Validation" : "Entraînement"} de la passe : ${live.pct} % · étape ${live.step} sur ${live.steps}`)) : null,
    h("div", { class: "dl-grid" },
      dlItem("Passes", `${cur} / ${n}`, h("div", { class: "pbar" }, h("i", { style: `width:${(100 * Math.max(0, cur - (live ? 1 : 0))) / n}%` }))),
      dlItem("Fin estimée", end ? end.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) : "—", end ? `dans ${hms(st.eta_s)}` : ""),
      dlItem("Vitesse", live && live.rate ? `${live.rate.toFixed(1)} lots/s` : "—", live && live.instances ? `${live.instances} pièces dans le lot en cours` : "un lot = quelques images traitées ensemble"),
      dlItem("Mémoire graphique", live && live.gpu_gb ? `${live.gpu_gb.toFixed(1)} Go` : "—", st.mem_free_pct != null ? `${st.mem_free_pct} % de mémoire libre sur le Mac Studio (machine partagée)` : "")),
    live && live.stage === "entraînement" ? h("p", { class: "dl-note" }, "Les erreurs de la passe en cours, mises à jour à chaque lot : ",
      ...LOSSES.map((l) => h("span", { class: "dl-loss" }, `${l.label.toLowerCase()} `, h("b", {}, live[l.key].toFixed(3)),
        last["train/" + l.key] != null ? h("small", { class: live[l.key] < last["train/" + l.key] ? "good" : "bad" }, live[l.key] < last["train/" + l.key] ? " ↓" : " ↑") : null))) : null);

  // B. la note du modèle
  const notes = h("div", { class: "dash-metrics" }, METRICS.map((m) => {
    const vals = ep.map((e) => e[m.key]);
    const d = last[m.key] != null && prev[m.key] != null ? last[m.key] - prev[m.key] : null;
    return h("article", { class: "dm" },
      h("header", {}, h("span", {}, m.label), d != null ? h("small", { class: d >= 0 ? "good" : "bad" }, `${d >= 0 ? "+" : ""}${(d * 100).toFixed(1)} pt`) : null),
      h("b", { class: "dm-v" }, pctf(last[m.key])),
      lineChart({ series: [{ values: vals, color: m.color, label: "" }], n: Math.max(n, ep.length), ymin: 0, ymax: 1, fmt: (v) => Math.round(v * 100) + "%", height: 150, width: 380, marks: marks.map((m) => ({ ...m, label: "reprise" })) }),
      h("p", {}, m.what), h("p", { class: "muted" }, m.read));
  }));
  const tv = trendVerdict(ep.map((e) => e["metrics/mAP50(M)"]));

  // C. erreurs : entraînement vs validation
  const lossCards = h("div", { class: "dash-losses" }, LOSSES.map((l) => {
    const tr = ep.map((e) => e["train/" + l.key]), va = ep.map((e) => e["val/" + l.key]);
    return h("article", { class: "dm" },
      h("header", {}, h("span", {}, l.label), h("small", { class: "muted" }, `${(last["train/" + l.key] || 0).toFixed(3)} / ${(last["val/" + l.key] || 0).toFixed(3)}`)),
      lineChart({ series: [{ values: tr, color: "var(--accent)", label: "entraînement" }, { values: va, color: "var(--k-curved)", label: "jamais vues", dash: true }],
        n: Math.max(n, ep.length), height: 170, width: 380, marks: marks.map((m) => ({ ...m, label: "reprise" })),
        livePoint: live && live.stage === "entraînement" && live[l.key] != null ? { i: cur - 1, value: live[l.key], color: "var(--accent)" } : null }),
      h("p", {}, l.what));
  }));
  const ov = overfitVerdict(ep);

  // D. taux d'apprentissage
  const lr = ep.map((e) => e["lr/pg0"]);

  $("#trStatus").replaceChildren(
    liveCard,
    h("h2", { class: "sec" }, "La note du modèle"),
    h("p", { class: "dash-intro" }, "Mesurée à la fin de chaque passe sur ", h("b", {}, "des images de validation que le modèle n'a jamais vues pendant l'entraînement"), " (10 % des scènes, mises de côté). Ce sont des rendus synthétiques : le vrai test sur les photos Gemini est plus bas."),
    h("div", { class: "verdict " + tv.cls }, h("b", {}, "Tendance : "), tv.txt),
    notes,
    h("details", { class: "dash-more" }, h("summary", {}, "Les quatre notes sur un seul graphique, et la différence boîtes / contours"),
      lineChart({ series: METRICS.map((m) => ({ values: ep.map((e) => e[m.key]), color: m.color, label: m.label.replace(/ \(.*\)/, "") })), n: Math.max(n, ep.length), ymin: 0, ymax: 1, fmt: (v) => Math.round(v * 100) + "%", height: 240, marks }),
      h("p", { class: "muted" }, `Le modèle prédit deux choses pour chaque pièce : un rectangle (« boîte ») et un contour exact (« masque »). Les notes ci-dessus portent sur les contours. Sur les boîtes, la note globale est de ${pctf(last["metrics/mAP50(B)"])} : quasi identique, ce qui veut dire que quand le modèle situe une pièce, il en dessine aussi bien le contour.`)),
    h("h2", { class: "sec" }, "Est-ce qu'il apprend encore ?"),
    h("p", { class: "dash-intro" }, "Les « erreurs » (pertes) sont ce que le modèle cherche à faire baisser. ", h("b", {}, "Plus bas = mieux."),
      " Trait plein : sur les images d'entraînement. Pointillés : sur les images jamais vues. Si les deux baissent, il apprend vraiment. Si les pointillés remontent alors que le trait plein baisse, il apprend par cœur. Le point « en cours » montre la passe actuelle, lot après lot."),
    h("div", { class: "verdict " + ov.cls }, h("b", {}, "Diagnostic : "), ov.txt),
    lossCards,
    h("details", { class: "dash-more" }, h("summary", {}, "Taux d'apprentissage"),
      lineChart({ series: [{ values: lr, color: "var(--k-plate)", label: "taux d'apprentissage" }], n: Math.max(n, ep.length), fmt: (v) => v.toExponential(1), height: 140, marks }),
      h("p", { class: "muted" }, "La taille des pas que fait le modèle pour corriger ses erreurs. Grande au début pour apprendre vite, puis de plus en plus petite pour affiner sans tout casser. La reprise après le plantage repart volontairement avec un pas petit.")),
    h("details", { class: "dash-more" }, h("summary", {}, "Lexique"),
      h("dl", { class: "lexique" },
        lex("Passe (epoch)", "Le modèle a vu une fois toutes les images d'entraînement (environ 6 300)."),
        lex("Lot (batch)", "Groupe d'images traitées ensemble avant chaque correction. Après le plantage, lots de 8 au lieu de 16 pour consommer moins de mémoire."),
        lex("Validation", "Contrôle à la fin de chaque passe, sur des images mises de côté que le modèle n'apprend jamais."),
        lex("Confiance", "Pour chaque pièce détectée, à quel point le modèle est sûr de lui (0 à 100 %). Les détections sous 25 % sont ignorées."),
        lex("Surapprentissage", "Le modèle retient les images d'entraînement au lieu d'apprendre à reconnaître les pièces : il devient bon sur elles et mauvais sur le reste."),
        lex("Plantage de la passe 18", "Le Mac Studio est partagé : un autre programme a pris 26 Go de mémoire. L'entraînement a repris avec des lots plus petits."))),
    h("details", { class: "dash-more" }, h("summary", {}, "Journal brut"), h("pre", { class: "tr-log" }, (st.log || []).join("\n") || "—")));

  const plots = (st.plots || []).filter((p) => /results|val_batch\d_pred|confusion_matrix_normalized|labels/.test(p));
  const PLOT_FR = { "results.png": "Toutes les courbes (format Ultralytics)", "labels.jpg": "Répartition des pièces dans les données", "confusion_matrix_normalized.png": "Confusions entre références (fin d'entraînement)" };
  const t = Math.floor(Date.now() / 60000);
  $("#trPlots").replaceChildren(h("h4", {}, "Images produites par l'entraînement"),
    plots.length ? h("div", { class: "views" }, plots.map((p) =>
      h("figure", { onclick: () => openLightbox(`/api/train/file/runs/segment/${st.plots_run}/${p}?t=${Date.now()}`) },
        h("img", { src: `/api/train/file/runs/segment/${st.plots_run}/${p}?t=${t}`, alt: p, loading: "lazy" }),
        h("figcaption", {}, PLOT_FR[p] || (p.includes("_pred") ? "Prédictions sur des images de validation" : p))))) :
      h("p", { class: "muted" }, "Elles apparaissent au fil de l'entraînement (prédictions sur la validation à la fin, matrice de confusion à la fin)."));
}
const dlItem = (label, value, sub) => h("div", { class: "dl-item" }, h("small", {}, label), h("b", {}, value), typeof sub === "string" ? h("span", { class: "muted" }, sub) : sub);
const lex = (t, d) => [h("dt", {}, t), h("dd", {}, d)];

async function loadSamples() {
  const grid = $("#trGrid");
  grid.replaceChildren(h("p", { class: "muted" }, "Chargement…"));
  try {
    const r = await api(`/api/train/samples?n=24&seed=${trSeed}`);
    trSamples = r.ids;
    grid.replaceChildren(...trSamples.map((sid) =>
      h("button", { onclick: () => openSample(sid), title: sid }, h("img", { src: `/api/train/file/out/synth/images/${sid}.jpg?g=${r.gen}`, alt: "Exemple " + sid, loading: "lazy" }))));
  } catch (e) { grid.replaceChildren(h("p", { class: "bad" }, e.message)); }
}

async function openSample(sid) {
  const d = await api(`/api/train/sample/${sid}`);
  openViewer({
    title: `Exemple ${sid}`, image: d.image, truth: d.objects,
    loadPred: async () => (await api("/api/train/predict", { method: "POST", body: JSON.stringify({ images: [`out/synth/images/${sid}.jpg`] }) })).results[0].objects,
  });
}

// Visionneuse : étiquettes vraies et / ou prédictions du modèle, superposées à l'image
function openViewer({ title, image, truth = null, pred = null, loadPred = null, start = truth ? "truth" : "pred" }) {
  const modal = h("div", { class: "tr-modal", onclick: (e) => { if (e.target === modal) modal.remove(); } });
  const img = h("img", { src: image, alt: "" });
  const svg = svgEl("svg", { viewBox: "0 0 1 1", preserveAspectRatio: "none" });
  const side = h("div", { class: "tr-side" });
  const fit = h("div", { class: "tr-fit" }, img, svg);
  let mode = start, showLabels = true;
  const bigImg = h("img", { alt: "", width: 140, height: 140 });
  const bigTxt = h("div", {}, h("b", {}, "Survole une pièce"), h("span", { class: "muted" }, "pour voir à quoi elle ressemble"));
  const big = h("div", { class: "pbig" }, bigImg, bigTxt);
  async function showBig(o, isPred) {
    const r = await partPreview(o.part, isPred ? 71 : o.color, 140);
    if (!r) return;
    bigImg.src = r.src;
    bigTxt.replaceChildren(h("b", {}, o.part), h("span", {}, r.title),
      h("span", { class: "muted" }, isPred ? `confiance ${Math.round(o.conf * 100)} %` : (o.color_name || "")));
  }

  function draw(objs, isPred) {
    svg.replaceChildren(); const items = [];
    objs.forEach((o, i) => {
      const hue = isPred ? (o.part.split("").reduce((a, c) => a + c.charCodeAt(0), 0) * 37) % 360 : (i * 47) % 360;
      const poly = svgEl("polygon", { points: o.poly.map((q) => q.join(",")).join(" "), style: `fill:hsl(${hue} 75% 55%)` });
      poly.addEventListener("mouseenter", () => hl(i)); poly.addEventListener("mouseleave", () => hl(-1));
      svg.append(poly); items.push({ poly, o });
    });
    const sorted = items.map((it, i) => [it, i]);
    if (isPred) sorted.sort((a, b) => b[0].o.conf - a[0].o.conf);
    const ul = h("ul", {}, sorted.map(([it, i]) => {
      const pic = h("img", { class: "pthumb", alt: "", width: 40, height: 40 });
      const nm = h("span", {}, isPred ? `${partName(it.o.part)} · ${Math.round(it.o.conf * 100)} %` : `${it.o.name} · ${it.o.color_name}`);
      partPreview(it.o.part, isPred ? 71 : it.o.color).then((r) => {
        if (!r) return; pic.src = r.src;
        if (isPred) nm.textContent = `${r.title} · ${Math.round(it.o.conf * 100)} %`;
      });
      return (it.li = h("li", { onmouseenter: () => hl(i), onmouseleave: () => hl(-1) },
        isPred ? h("i", { style: `background:hsl(${(it.o.part.split("").reduce((a, c) => a + c.charCodeAt(0), 0) * 37) % 360} 75% 55%)` }) : h("i", { style: `background:${colorHex(it.o.color)}` }),
        pic, h("b", {}, it.o.part), nm));
    }));
    function hl(k) {
      items.forEach((it, i) => { it.poly.classList.toggle("hl", i === k); it.li && it.li.classList.toggle("hl", i === k); });
      if (k >= 0) showBig(items[k].o, isPred);
    }
    const counts = {}; objs.forEach((o) => (counts[o.part] = (counts[o.part] || 0) + 1));
    return [h("div", { class: "muted", style: "font-size:12px" }, `${objs.length} pièces ${isPred ? "détectées" : "visibles"} · ${Object.keys(counts).length} références`), ul];
  }

  async function render() {
    const tabs = h("div", { class: "seg" },
      truth ? h("button", { class: "tool", "aria-pressed": String(mode === "truth"), onclick: () => { mode = "truth"; render(); } }, "Vérité") : null,
      (pred || loadPred) ? h("button", { class: "tool", "aria-pressed": String(mode === "pred"), onclick: () => { mode = "pred"; render(); } }, "Prédiction du modèle") : null);
    const head = [h("h3", { style: "margin:0;font:600 15px var(--font-display)" }, title), tabs,
      h("div", { class: "actions" },
        h("button", { class: "btn small", onclick: (e) => { showLabels = !showLabels; svg.style.display = showLabels ? "" : "none"; e.target.textContent = showLabels ? "Masquer" : "Afficher"; } }, showLabels ? "Masquer" : "Afficher"),
        h("button", { class: "btn small", onclick: () => modal.remove() }, "Fermer"))];
    if (mode === "pred" && !pred) {
      side.replaceChildren(...head, h("p", { class: "muted" }, "Le modèle analyse l'image sur le Mac Studio… (5 à 15 s)"));
      try { pred = await loadPred(); } catch (e) { side.replaceChildren(...head, h("p", { class: "bad" }, e.message)); return; }
    }
    side.replaceChildren(...head, big, ...(mode === "pred" ? draw(pred, true) : draw(truth, false)));
  }
  modal.append(h("div", { class: "tr-box" }, h("div", { class: "tr-stage" }, fit), side));
  document.body.append(modal);
  render();
}
const partName = (p) => (S.catalog.parts.find((x) => x.part === p) || {}).name || p;

// Prédictions sur les vraies vues Gemini d'un sujet
async function geminiPredictions(btn) {
  const subject = "lego_tortue";
  const det = await api(`/api/subjects/${subject}`);
  const views = det.views;
  const grid = $("#trGemini");
  btn.disabled = true; btn.textContent = "Analyse en cours… (~30 s)";
  grid.replaceChildren(h("p", { class: "muted" }, "Le modèle analyse les 6 vues Gemini sur le Mac Studio…"));
  try {
    const r = await api("/api/train/predict", { method: "POST", body: JSON.stringify({ images: views.map((v) => v.url.replace(/^\//, "")), imgsz: 1024 }) });
    grid.replaceChildren(...r.results.map((res, i) => {
      const v = views[i];
      const svg = svgEl("svg", { viewBox: "0 0 1 1", preserveAspectRatio: "none" });
      res.objects.forEach((o) => svg.append(svgEl("polygon", { points: o.poly.map((q) => q.join(",")).join(" "),
        style: `fill:hsl(${(o.part.split("").reduce((a, c) => a + c.charCodeAt(0), 0) * 37) % 360} 75% 55%);fill-opacity:.45;stroke:#111;stroke-width:.002` })));
      return h("figure", { class: "gem", onclick: () => openViewer({ title: `Vue Gemini : ${v.name}`, image: v.thumb.replace("w=720", "w=1200"), pred: res.objects, start: "pred" }) },
        h("div", { class: "tr-fit" }, h("img", { src: v.thumb, alt: v.name }), svg),
        h("figcaption", {}, `${v.name} · ${res.objects.length} pièces détectées`));
    }));
    $("#trGeminiNote").textContent = `Modèle après ${r.epoch} passe(s) d'entraînement.`;
  } catch (e) { grid.replaceChildren(h("p", { class: "bad" }, e.message)); }
  btn.disabled = false; btn.textContent = "Relancer l'analyse";
}

// Aperçu 3D d'une pièce (géométrie LDraw), mis en cache : { src, title }
const _prevCache = {};
async function partPreview(part, color = 71) {
  const key = part + ":" + color;
  if (!_prevCache[key]) {
    _prevCache[key] = (async () => {
      try {
        if (!window.THREE) return null;
        const g = await partGeo(part);
        return { src: await thumb(part, color), title: (g.info.title || part).replace(/^~?Moved to.*/, part) };
      } catch (e) { return null; }
    })();
  }
  return _prevCache[key];
}
