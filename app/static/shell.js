// Brick Forge Lab — coquille : routeur, navigation, cahier de recherche, indicateur en direct.
//
// Routes :
//   #/                         cahier de recherche (accueil)
//   #/note/<id>                une entrée du cahier (research/notes/<id>.md), avec son suivi en direct
//   #/sujet/<nom>/<onglet>     un sujet : modele | comparer | vues | annoter | mesures | historique
//   #/bac-a-sable              construire soi-même
//   #/explorateur[/<num>]      vrais sets LEGO (Rebrickable + 3D OMR LDraw) : catalogue, inventaire, vue 3D, notice
//
// Ajouter une recherche : écrire research/notes/NN-titre.md (en-tête title/date/status/summary/cover/
// metrics/live/subject). Elle apparaît dans la navigation et sur l'accueil, sans toucher au code.
"use strict";

const SUBJECT_TABS = [
  { id: "modele", tab: "assembler", label: "Modèle 3D" },
  { id: "comparer", tab: "comparer", label: "Comparer aux photos" },
  { id: "vues", tab: "vues", label: "Vues Gemini" },
];
const ARCHIVE_TABS = [
  { id: "annoter", tab: "annoter", label: "Annoter" },
  { id: "mesures", tab: "mesures", label: "Mesures" },
  { id: "historique", tab: "historique", label: "Historique" },
];
const LIVE_PANELS = { training: "entrainement", compare: "comparer" };
const STATUS_CLASS = { "en cours": "run", "terminé": "ok", "écarté": "off", "archivé": "off", "abandonné": "off" };

const SH = { notes: [], route: null };

function showPanels(ids) {
  $$(".panel").forEach((p) => (p.hidden = !ids.includes(p.id)));
}
const statusChip = (st) => h("span", { class: "status " + (STATUS_CLASS[st] || "") }, st || "—");

// ------------------------------------------------------------------ navigation

window.renderNav = function renderNav() {
  const r = SH.route || {};
  $$('[data-nav="home"]').forEach((a) => a.setAttribute("aria-current", String(r.kind === "home")));
  $$('[data-nav="sandbox"]').forEach((a) => a.setAttribute("aria-current", String(r.kind === "sandbox")));
  $$('[data-nav="explorer"]').forEach((a) => a.setAttribute("aria-current", String(r.kind === "explorer")));
  $("#navNotes").replaceChildren(...SH.notes.slice().reverse().map((n) =>
    h("a", { class: "navnote", href: `#/note/${n.id}`, "aria-current": String(r.kind === "note" && r.id === n.id) },
      h("i", { class: "dot " + (STATUS_CLASS[n.status] || "") }), h("span", {}, n.title))));
  $("#navSubjects").replaceChildren(...(S.subjects || []).map((s) =>
    h("a", { class: "navsubj", href: `#/sujet/${s.name}/modele`, "aria-current": String(r.kind === "subject" && r.subject === s.name) },
      s.thumb ? h("img", { src: s.thumb, alt: "", loading: "lazy" }) : h("span", { class: "noimg" }),
      h("span", {}, h("b", {}, s.name.replace(/^lego_/, "").replace(/_/g, " ")), h("small", {}, `${s.views.length} vues`)))));
};

function parseRoute() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] === "note" && parts[1]) return { kind: "note", id: parts[1] };
  if (parts[0] === "sujet" && parts[1]) return { kind: "subject", subject: parts[1], tab: parts[2] || "modele" };
  if (parts[0] === "bac-a-sable") return { kind: "sandbox" };
  if (parts[0] === "explorateur") return { kind: "explorer", num: parts[1], file: parts[2] };
  return { kind: "home" };
}

async function route() {
  const r = parseRoute();
  SH.route = r;
  renderNav();
  $("#segBar").hidden = true;
  window.scrollTo(0, 0);
  try {
    if (r.kind === "home") await pageHome();
    else if (r.kind === "note") await pageNote(r.id);
    else if (r.kind === "sandbox") await pageSandbox();
    else if (r.kind === "explorer") await pageExplorer(r.num, r.file);
    else await pageSubject(r.subject, r.tab);
  } catch (e) {
    $("#pageHead").replaceChildren(h("h1", {}, "Erreur"));
    showPanels(["page-home"]);
    $("#page-home").replaceChildren(h("div", { class: "notice" }, e.message));
  }
}

// ------------------------------------------------------------------ accueil

async function pageHome() {
  S.tab = "home";
  $("#pageHead").replaceChildren();
  showPanels(["page-home"]);
  const el = $("#page-home");
  const ov = await api("/api/overview");
  const latest = SH.notes[0];
  const steps = [
    ["Photo", "le sujet à reproduire"], ["Concept Gemini", "modèle en briques imaginé"], ["6 vues", "face, profil, dessus…"],
    ["Pièces", "reconnues dans les images"], ["Assemblage", "emboîté et vérifié"], ["Notice", "étape par étape"]];
  const done = { 0: "ok", 1: "ok", 2: "ok", 3: "run", 4: "run", 5: "" };
  el.replaceChildren(
    h("section", { class: "hero" },
      h("p", { class: "eyebrow" }, "Cahier de recherche · Brick Forge"),
      h("h1", {}, "De la photo au modèle en briques constructible"),
      h("p", { class: "lede" }, "Une image de chat, de voiture ou de tortue devient un vrai modèle : pièces réelles, assemblage vérifié, notice de montage. Ce cahier suit chaque piste explorée, ses résultats et ce qui tourne en ce moment."),
      h("div", { class: "pipeline" }, steps.map(([t, d], i) =>
        h("div", { class: "step " + (done[i] || "") }, h("b", {}, t), h("small", {}, d))))),
    h("dl", { class: "kpis hero-kpis" },
      kpiTile("Recherches menées", ov.notes),
      kpiTile("Sujets", ov.subjects),
      kpiTile("Pièces posées dans les modèles", ov.parts_placed.toLocaleString("fr-FR")),
      kpiTile("Meilleure ressemblance", ov.best_silhouette ? Math.round(ov.best_silhouette.value * 100) + " %" : "—",
        ov.best_silhouette ? "silhouette, " + ov.best_silhouette.subject.replace(/^lego_/, "") : "")),
    latest ? h("a", { class: "now", href: `#/note/${latest.id}` },
      h("span", { class: "eyebrow" }, "En ce moment"), h("b", {}, latest.title), h("span", {}, latest.summary),
      h("span", { class: "live-inline", id: "nowLive" })) : null,
    h("h2", { class: "sec" }, "Toutes les recherches"),
    h("div", { class: "timeline" }, SH.notes.map(noteCard)));
  updateLive();
}

function kpiTile(label, value, sub) {
  return h("div", { class: "kpi" }, h("dt", {}, label), h("dd", {}, String(value)), sub ? h("small", {}, sub) : null);
}

function noteCard(n) {
  return h("a", { class: "notecard", href: `#/note/${n.id}` },
    n.cover ? h("img", { src: n.cover, alt: "", loading: "lazy" }) : h("div", { class: "nocover" }),
    h("div", { class: "nc-body" },
      h("div", { class: "nc-meta" }, statusChip(n.status), h("span", {}, n.date)),
      h("h3", {}, n.title),
      h("p", {}, n.summary),
      n.metrics.length ? h("ul", { class: "nc-metrics" }, n.metrics.slice(0, 3).map((m) => h("li", {}, h("small", {}, m.label), h("b", {}, m.value)))) : null));
}

// ------------------------------------------------------------------ entrée du cahier

async function pageNote(id) {
  const n = await api(`/api/journal/${id}`);
  $("#pageHead").replaceChildren(
    h("div", { class: "ph-meta" }, h("a", { href: "#/" }, "Cahier"), h("span", {}, "/"), statusChip(n.status), h("span", {}, n.date),
      n.tags.map((t) => h("span", { class: "tag" }, t))),
    h("h1", {}, n.title),
    h("p", { class: "lede" }, n.summary),
    n.authors && n.authors.length ? h("p", { class: "authors" }, "Auteurs : " + n.authors.join(", ")) : null);
  const body = h("article", { class: "note" });
  body.innerHTML = n.html;
  const g3d = ["galerie-bh", "i3d", "fill-live", "train-fill"].includes(n.live) ? h("div", { class: n.live === "fill-live" || n.live === "train-fill" ? "flv-host" : "bhg-host" }) : null;
  $("#page-note").replaceChildren(
    n.metrics.length ? h("dl", { class: "kpis" }, n.metrics.map((m) => kpiTile(m.label, m.value))) : null,
    g3d || "",
    body,
    n.live ? h("h2", { class: "sec live-title" }, h("i", { class: "dot run" }), "Suivi en direct") : "");
  if (g3d) (n.live === "i3d" ? I3D.mount(g3d) : n.live === "fill-live" ? FLV.mount(g3d) : n.live === "train-fill" ? TRF.mount(g3d) : BHG.mount(g3d, body));
  else body.querySelectorAll("img").forEach((img) => img.addEventListener("click", () => openLightbox(img.src.replace(/\/thumb\/(.*?)\?w=\d+/, "/$1"))));
  const panels = ["page-note"];
  if (n.live === "training") {
    S.tab = "entrainement";
    panels.push("tab-entrainement");
    showPanels(panels);
    renderTraining();
  } else if (n.live === "compare" && n.subject) {
    if (S.subject !== n.subject || !S.detail) await selectSubject(n.subject);
    S.tab = "comparer";
    panels.push("tab-comparer");
    showPanels(panels);
    renderComparer();
  } else {
    S.tab = "note";
    showPanels(panels);
  }
}

// ------------------------------------------------------------------ sujet

async function pageSubject(name, tabId) {
  const all = SUBJECT_TABS.concat(ARCHIVE_TABS);
  const t = all.find((x) => x.id === tabId) || SUBJECT_TABS[0];
  if (S.subject !== name || !S.detail) await selectSubject(name, S.pendingRun);
  else if (S.pendingRun) await selectSubject(name, S.pendingRun);
  S.pendingRun = null;
  const subj = (S.subjects || []).find((s) => s.name === name);
  const link = (x) => h("a", { class: "subtab", href: `#/sujet/${name}/${x.id}`, "aria-current": String(x.id === t.id) }, x.label);
  $("#pageHead").replaceChildren(
    h("div", { class: "ph-subject" },
      subj && subj.thumb ? h("img", { src: subj.thumb, alt: "" }) : null,
      h("div", {}, h("div", { class: "ph-meta" }, h("span", {}, "Sujet")), h("h1", {}, name.replace(/^lego_/, "").replace(/_/g, " ")))),
    h("nav", { class: "subtabs" }, SUBJECT_TABS.map(link), h("span", { class: "subsep" }, "Archive SAM"), ARCHIVE_TABS.map(link)));
  $("#segBar").hidden = !SAM_TABS.includes(t.tab);
  S.tab = t.tab;
  showPanels(["tab-" + t.tab]);
  await renderAll();
}

// ------------------------------------------------------------------ indicateur en direct (Mac Studio)

let liveTimer = null, liveData = null;
async function updateLive() {
  clearTimeout(liveTimer);
  try { liveData = await api("/api/train/status"); }
  catch (e) { liveData = null; }
  const b = $("#liveBadge");
  if (liveData) {
    const ep = Math.max((liveData.epochs || []).length, liveData.current_epoch || 0);
    const txt = liveData.phase === "génération" ? `génération ${Math.round(100 * liveData.images / liveData.images_total)} %`
      : liveData.phase === "entraînement" ? `entraînement ${ep}/${liveData.epochs_total}` : liveData.phase;
    const active = ["génération", "entraînement"].includes(liveData.phase);
    b.replaceChildren(h("i", { class: "dot " + (active ? "run pulse" : "ok") }), h("span", {}, h("small", {}, "Mac Studio · détecteur"), h("b", {}, txt)));
    b.hidden = false;
    const now = $("#nowLive");
    if (now) now.replaceChildren(h("i", { class: "dot " + (active ? "run pulse" : "ok") }), " ", txt);
  } else {
    b.hidden = true;
  }
  liveTimer = setTimeout(updateLive, 15000);
}

// ------------------------------------------------------------------ démarrage

async function boot() {
  // le cahier et les sujets en parallèle ; le catalogue et la 3D ne bloquent pas l'affichage
  const [notes] = await Promise.all([api("/api/journal"), loadSubjects(), initApp()]);
  SH.notes = notes;
  window.addEventListener("hashchange", route);
  await route();
  setTimeout(updateLive, 800);
}
boot().catch((e) => document.body.prepend(h("div", { class: "notice" }, "Erreur au démarrage : " + e.message)));
