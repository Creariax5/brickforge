// Brick Forge Lab — explorateur des vrais sets LEGO : tout le catalogue Rebrickable (~20 000 sets),
// avec la 3D et la notice de l'OMR LDraw quand le set y est modélisé (~1 500).
//   #/explorateur                       catalogue : recherche, thème, années, pièces, tri, animaux, 3D, téléchargés
//   #/explorateur/<num>[/<fichier>]     un set OMR : vue 3D, notice étape par étape, statistiques, pièces
//   #/explorateur/<num>/@inventaire     inventaire officiel (Rebrickable) ; c'est la fiche des sets sans 3D
"use strict";

const ANIMAL_RX = /\b(animal|animals|cat|kitten|dog|puppy|bird|owl|parrot|eagle|duck|chick|horse|pony|unicorn|dragon|dino|dinosaur|t-rex|raptor|lion|tiger|bear|panda|fox|rabbit|bunny|deer|reindeer|sheep|cow|pig|goat|monkey|gorilla|elephant|giraffe|zebra|hippo|rhino|shark|whale|dolphin|fish|squid|octopus|crab|turtle|frog|snake|bee|butterfly|spider|scorpion|penguin|seal|turkey|creature|beast|pet|pets|animaux|wolf|bat|mouse|camel|crocodile|alligator|lizard|swan|flamingo|peacock|hedgehog|koala|kangaroo|squirrel|raccoon|otter|beaver|llama)\b/i;

const DUPLO_RX = /\b(duplo|primo|quatro)\b/i;   // gros éléments pour tout-petits : autre système que la brique classique

const NOT_ANIMAL_RX = /\b(cat d\d+|locomotive|bulldozer|excavator|truck|tractor|loader)\b/i;   // « Cat D11 », « Crocodile Locomotive »…

const EX = {
  sets: null, colors: null, shown: 0, obs: null,
  f: { q: "", theme: "", sort: "recent", y0: "", y1: "", p0: "", p1: "", animals: false, ds: "", noduplo: true, dl: false, ...JSON.parse(sessionStorage.getItem("exFilters") || "{}") },
  three: null, geo: {}, model: null, step: null, groups: [], play: null, cur: null,
};

// d'où vient chaque set : 3 jeux de données
const SOURCES = {
  omr:   { label: "OMR LDraw", short: "OMR · 3D", tip: "Modèle 3D + notice, dépôt officiel LDraw (licence CCAL 2.0)" },
  forum: { label: "Forum LDraw", short: "Forum · 3D", tip: "Modèle 3D + notice publié sur le forum LDraw, pas encore entré dans l'OMR" },
  rb:    { label: "Rebrickable", short: "Inventaire", tip: "Inventaire de la boîte seulement (Rebrickable) : pièces, couleurs, quantités, sans positions" },
};
const srcOf = (s) => (s.source === "forum" ? "forum" : s.src === "omr" ? "omr" : "rb");

const kids = (...xs) => xs.flat(2).filter((x) => x != null && x !== false);   // replaceChildren n'accepte pas null ni les tableaux

// ------------------------------------------------------------------ catalogue

async function pageExplorer(num, file) {
  S.tab = "explorer";
  showPanels(["page-explorer"]);
  if (!EX.sets) {
    $("#page-explorer").replaceChildren(h("p", { class: "muted" }, "Chargement du catalogue…"));
    const [sets, cols] = await Promise.all([api("/api/sets"), api("/api/ldcolors")]);
    EX.sets = sets; EX.colors = cols;
  }
  if (num) return exDetail(num, file);
  exStop();
  $("#pageHead").replaceChildren(
    h("div", { class: "ph-meta" }, h("span", {}, "Données"), h("span", {}, "/"), h("span", {}, "Rebrickable (inventaires) · OMR LDraw (3D, licence CCAL 2.0)")),
    h("h1", {}, "Explorateur de vrais sets"),
    h("p", { class: "lede" }, `${EX.sets.length.toLocaleString("fr-FR")} sets officiels LEGO, des années 1950 aux sorties récentes, avec leur inventaire de pièces. ` +
      `${EX.sets.filter((s) => s.src === "omr").length.toLocaleString("fr-FR")} d'entre eux (badge 3D) sont aussi modélisés pièce par pièce avec l'ordre de montage de la notice ` +
      `(OMR LDraw, plus ${EX.sets.filter((s) => s.source === "forum").length} sets récents publiés sur le forum LDraw).`));
  const themes = {};
  for (const s of EX.sets) { const t = s.theme.split(" > ")[0]; themes[t] = (themes[t] || 0) + 1; }
  const f = EX.f;
  const save = () => { sessionStorage.setItem("exFilters", JSON.stringify(f)); exRenderGrid(); };
  const inp = (attrs, key) => h("input", { ...attrs, value: f[key], oninput: (e) => { f[key] = e.target.value; save(); } });
  const toggle = (key, label) => h("button", { class: "chip", "aria-pressed": String(f[key]), onclick: (e) => { f[key] = !f[key]; e.currentTarget.setAttribute("aria-pressed", String(f[key])); save(); } }, label);
  $("#page-explorer").replaceChildren(
    h("div", { class: "ex-bar" },
      inp({ class: "ex-search", placeholder: "Rechercher : nom, numéro, thème (ex. shark, 10294, castle)", type: "search" }, "q"),
      h("select", { title: "Jeu de données d'origine", onchange: (e) => { f.ds = e.target.value; save(); } },
        h("option", { value: "" }, "Toutes les sources"),
        h("option", { value: "3d", selected: f.ds === "3d" }, `3D + notice : OMR et forum (${EX.sets.filter((x) => srcOf(x) !== "rb").length.toLocaleString("fr-FR")})`),
        Object.entries(SOURCES).map(([k, v]) => h("option", { value: k, selected: f.ds === k },
          `${v.label} (${EX.sets.filter((x) => srcOf(x) === k).length.toLocaleString("fr-FR")})`))),
      h("select", { onchange: (e) => { f.theme = e.target.value; save(); } },
        h("option", { value: "" }, "Tous les thèmes"),
        Object.entries(themes).sort((a, b) => b[1] - a[1]).map(([t, n]) => h("option", { value: t, selected: f.theme === t }, `${t} (${n})`))),
      h("label", { class: "ex-years" }, "Années", inp({ type: "number", placeholder: "1949", min: 1949, max: 2030 }, "y0"), "–", inp({ type: "number", placeholder: "2025", min: 1949, max: 2030 }, "y1")),
      h("label", { class: "ex-years" }, "Pièces", inp({ type: "number", placeholder: "min", min: 0, step: 10 }, "p0"), "–", inp({ type: "number", placeholder: "max", min: 0, step: 10 }, "p1")),
      h("select", { onchange: (e) => { f.sort = e.target.value; save(); } },
        [["num", "Numéro"], ["recent", "Plus récents"], ["old", "Plus anciens"], ["name", "Nom (A→Z)"], ["models", "Nb de modèles"], ["pieces", "Moins de pièces"], ["pieces_desc", "Plus de pièces"]]
          .map(([v, l]) => h("option", { value: v, selected: f.sort === v }, "Tri : " + l))),
      toggle("noduplo", "Sans Duplo"), toggle("animals", "Animaux"), toggle("dl", "Déjà téléchargés"),
      h("span", { class: "muted ex-count", id: "exCount" })),
    h("div", { class: "ex-grid", id: "exGrid" }),
    h("div", { id: "exMore", class: "ex-more" }));
  exRenderGrid();
}

function exFiltered() {
  const f = EX.f, q = f.q.trim().toLowerCase();
  let L = EX.sets.filter((s) =>
    (!q || `${s.num} ${s.name} ${s.theme} ${s.keywords || ""}`.toLowerCase().includes(q)) &&
    (!f.theme || s.theme.split(" > ")[0] === f.theme) &&
    (!f.y0 || s.year >= +f.y0) && (!f.y1 || s.year <= +f.y1) &&
    (!f.p0 || (s.pieces ?? s.parts ?? 0) >= +f.p0) && (!f.p1 || (s.pieces ?? s.parts ?? Infinity) <= +f.p1) &&
    (!f.animals || (ANIMAL_RX.test(`${s.name} ${s.keywords || ""}`) && !NOT_ANIMAL_RX.test(s.name))) &&
    (!f.noduplo || !DUPLO_RX.test(`${s.theme} ${s.name}`)) &&
    (!f.ds || (f.ds === "3d" ? srcOf(s) !== "rb" : srcOf(s) === f.ds)) && (!f.dl || s.downloaded));
  const by = {
    num: (a, b) => a.num.localeCompare(b.num, "fr", { numeric: true }),
    recent: (a, b) => b.year - a.year || a.num.localeCompare(b.num, "fr", { numeric: true }),
    old: (a, b) => a.year - b.year || a.num.localeCompare(b.num, "fr", { numeric: true }),
    name: (a, b) => a.name.localeCompare(b.name, "fr"),
    models: (a, b) => (b.models || 0) - (a.models || 0),
    pieces: (a, b) => (a.pieces ?? 1e9) - (b.pieces ?? 1e9),
    pieces_desc: (a, b) => (b.pieces ?? -1) - (a.pieces ?? -1),
    parts: (a, b) => (b.pieces ?? -1) - (a.pieces ?? -1),
  }[f.sort] || ((a, b) => 0);
  return L.sort(by);
}

function exRenderGrid() {
  const L = exFiltered();
  $("#exCount").textContent = `${L.length.toLocaleString("fr-FR")} set(s)`;
  const grid = $("#exGrid");
  grid.replaceChildren();
  EX.shown = 0;
  const more = () => {
    const next = L.slice(EX.shown, EX.shown + 96);
    grid.append(...next.map(exCard));
    EX.shown += next.length;
    $("#exMore").textContent = EX.shown < L.length ? "…" : (L.length ? "" : "Aucun set ne correspond.");
  };
  more();
  if (EX.obs) EX.obs.disconnect();
  EX.obs = new IntersectionObserver((ents) => { if (ents[0].isIntersecting && EX.shown < L.length) more(); }, { rootMargin: "600px" });
  EX.obs.observe($("#exMore"));
}

function exCard(s) {
  return h("a", { class: "excard", href: `#/explorateur/${encodeURIComponent(s.num)}` },
    h("div", { class: "ex-img" }, h("img", { src: s.thumb, alt: "", loading: "lazy", decoding: "async" }),
      h("span", { class: `ex-src ex-src-${srcOf(s)}`, title: SOURCES[srcOf(s)].tip }, SOURCES[srcOf(s)].short),
      s.downloaded ? h("i", { class: "ex-dl", title: "Déjà téléchargé" }) : null),
    h("div", { class: "ex-body" },
      h("small", { class: "mono" }, s.num), h("b", {}, s.name),
      h("small", { class: "muted" }, `${s.theme.replace(/ > /g, " · ")} · ${s.year}`),
      h("div", { class: "ex-tags" },
        s.models > 1 ? h("span", { class: "tag" }, `${s.models} modèles`) : null,
        (s.pieces ?? s.parts) ? h("span", { class: "tag" }, `${s.pieces ?? s.parts} pièces`) : null)));
}

// ------------------------------------------------------------------ fiche d'un set

async function exDetail(num, file) {
  const s = EX.sets.find((x) => x.num === num);
  if (!s) throw new Error(`Set ${num} inconnu`);
  if (s.src !== "omr" || file === "@inventaire") return exInventory(s);
  $("#pageHead").replaceChildren(
    h("div", { class: "ph-subject" }, h("img", { src: s.thumb, alt: "" }),
      h("div", {}, h("div", { class: "ph-meta" }, h("a", { href: "#/explorateur" }, "Explorateur"), h("span", {}, "/"),
        h("span", { class: "mono" }, s.num), h("span", {}, s.theme.replace(/ > /g, " · ")), h("span", {}, String(s.year)),
        h("span", { class: `ex-src-inline ex-src-${srcOf(s)}`, title: SOURCES[srcOf(s)].tip }, SOURCES[srcOf(s)].label)),
        h("h1", {}, s.name))));
  const el = $("#page-explorer");
  if (!EX.cur || EX.cur.num !== num) {
    el.replaceChildren(h("p", { class: "muted" }, s.downloaded ? "Chargement…" : "Téléchargement depuis l'OMR LDraw…"));
    EX.cur = await api(`/api/omr/set/${encodeURIComponent(num)}`);
    s.downloaded = true;
  }
  const set = EX.cur;
  const m = set.models.find((x) => x.file === file) || set.models[0];
  el.replaceChildren(...kids(
    set.models.length > 1 ? h("nav", { class: "subtabs ex-models" }, set.models.map((x) =>
      h("a", { class: "subtab", href: `#/explorateur/${encodeURIComponent(num)}/${encodeURIComponent(x.file)}`, "aria-current": String(x.file === m.file) },
        x.title))) : null,
    h("div", { class: "ex-detail" },
      h("div", { class: "ex-view" },
        h("div", { class: "ex3d", id: "ex3d" }, h("div", { class: "ex-loading", id: "exLoading" }, "Chargement des pièces…")),
        h("div", { class: "ex-steps" },
          h("button", { class: "tool", id: "exPlay", title: "Lecture (espace)" }, "▶"),
          h("button", { class: "tool", title: "Étape précédente (←)", onclick: () => exGo(-1) }, "◀"),
          h("input", { type: "range", id: "exRange", min: 0, max: Math.max(0, m.steps - 1), value: m.steps - 1, oninput: (e) => exSetStep(+e.target.value) }),
          h("button", { class: "tool", title: "Étape suivante (→)", onclick: () => exGo(1) }, "▶|"),
          h("span", { class: "mono ex-steplbl", id: "exStepLbl" }),
          Photo.button(() => EX.three, null, () => EX.model && { three: EX.three, name: `${num}-${m.file}`, parts: EX.model.parts.filter((p) => EX.step == null || p.step <= EX.step) }),
          Photo.hdButton(() => EX.model && { three: EX.three, name: `${num}-${m.file}`,
            parts: EX.model.parts.filter((p) => EX.step == null || p.step <= EX.step) }),
          h("button", { class: "tool", title: "Enregistrer l'image (PNG)", onclick: () => Photo.snapshot(EX.three, `${num}-${m.file}`) }, "Photo")),
        h("p", { class: "hint" }, "Glisser : tourner · clic droit glissé : déplacer · molette : zoom · ← → : étapes · espace : lecture")),
      h("aside", { class: "ex-side", id: "exSide" }))));
  $("#exPlay").onclick = exTogglePlay;
  exSide(set, m, null);
  exScene();
  const model = await api(`/api/omr/set/${encodeURIComponent(num)}/model/${encodeURIComponent(m.file)}`);
  if (location.hash.split("/")[2] !== encodeURIComponent(num)) return;   // l'utilisateur est parti
  await exBuild(model);
  exSide(set, m, model);
}

function exSide(set, m, model) {
  const kv = (k, v) => h("div", { class: "kpi" }, h("dt", {}, k), h("dd", {}, String(v)));
  const top = model ? Object.entries(model.parts.reduce((a, p) => ((a[p.part] = (a[p.part] || 0) + 1), a), {})).sort((a, b) => b[1] - a[1]).slice(0, 14) : [];
  const cols = model ? Object.entries(model.parts.reduce((a, p) => ((a[p.color] = (a[p.color] || 0) + 1), a), {})).sort((a, b) => b[1] - a[1]) : [];
  $("#exSide").replaceChildren(...kids(
    h("dl", { class: "kpis ex-kpis" }, kv("Pièces", m.parts), kv("Références", m.unique), kv("Couleurs", m.colors), kv("Étapes", m.steps)),
    h("div", { class: "actions" },
      h("button", { class: "btn primary", onclick: async (e) => {
        e.currentTarget.disabled = true; e.currentTarget.textContent = "Import…";
        const r = await api(`/api/omr/set/${encodeURIComponent(set.num)}/model/${encodeURIComponent(m.file)}/subject`, { method: "POST" });
        await loadSubjects(); location.hash = `#/sujet/${r.subject}/modele`;
      } }, "Ouvrir comme sujet"),
      h("a", { class: "btn", href: `/api/omr/set/${encodeURIComponent(set.num)}/model/${encodeURIComponent(m.file)}.mpd`, download: "" }, "Télécharger .mpd"),
      h("a", { class: "btn", href: `#/explorateur/${encodeURIComponent(set.num)}/@inventaire` }, "Inventaire officiel")),
    h("p", { class: "muted small" }, `Modèle LDraw de ${m.author || "auteur inconnu"}` + (m.keywords ? ` · ${m.keywords}` : "")),
    set.source === "forum" ? h("p", { class: "muted small" }, "Publié sur le ", h("a", { href: set.thread, target: "_blank", rel: "noopener" }, "forum LDraw"),
      " et pas encore entré dans l'OMR : en principe conforme, mais pas encore relu par l'admin.") : null,
    m.subs.length > 1 ? [h("h3", {}, `Sous-ensembles (${m.subs.length})`),
      h("div", { class: "ex-subs" }, m.subs.map((sb) => h("span", { class: "tag" }, sb.replace(/^\S+ - /, ""))))] : null,
    cols.length ? [h("h3", {}, "Couleurs"), h("div", { class: "ex-cols" }, cols.map(([c, n]) => {
      const k = EX.colors[c] || { hex: "#999", name: c };
      return h("span", { class: "ex-col", title: `${k.name} · ${n}` }, h("i", { style: `background:${k.hex}` }), n);
    }))] : null,
    top.length ? [h("h3", {}, "Pièces les plus utilisées"), h("ol", { class: "ex-parts" }, top.map(([p, n]) =>
      h("li", {}, h("b", { class: "mono" }, p), h("span", {}, (EX.geo[p] && EX.geo[p].title) || ""), h("small", {}, "×" + n))))] : null));
}

// ------------------------------------------------------------------ vue 3D (une géométrie fusionnée par étape)

function exScene() {
  const box = $("#ex3d");
  if (EX.three) { box.prepend(EX.three.renderer.domElement); if (EX.three.photo) { EX.three.box.classList.remove("photo-stage"); box.classList.add("photo-stage"); } EX.three.box = box; EX.three.resize(); return; }
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  box.prepend(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 5000);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x7d756a, 0.8));
  const d1 = new THREE.DirectionalLight(0xffffff, 0.6); d1.position.set(15, 30, -20); scene.add(d1);
  const d2 = new THREE.DirectionalLight(0xffffff, 0.25); d2.position.set(-20, 10, 25); scene.add(d2);
  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };
  const root = new THREE.Group(); root.scale.set(1 / 20, -1 / 20, 1 / 20); scene.add(root);
  const resize = () => { const b = renderer.domElement.parentElement; if (!b) return; const w = b.clientWidth, hh = b.clientHeight; if (!w || !hh) return; renderer.setSize(w, hh, false); camera.aspect = w / hh; camera.updateProjectionMatrix(); };
  new ResizeObserver(resize).observe(box);
  const loop = () => { if (S.tab === "explorer" && renderer.domElement.isConnected) { controls.update(); Photo.tick(EX.three); Photo.render(EX.three); } requestAnimationFrame(loop); };
  EX.three = { renderer, scene, camera, controls, root, resize, box };
  resize(); loop();
  const mat = (o) => new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.4, metalness: 0, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1, ...o });
  EX.mats = { solid: mat({}), trans: mat({ transparent: true, opacity: 0.5, depthWrite: false }),
    hi: mat({ emissive: new THREE.Color("#00b8ff"), emissiveIntensity: 0.45 }),
    edge: new THREE.LineBasicMaterial({ color: 0x1b1b1b, transparent: true, opacity: 0.35 }) };
  window.addEventListener("keydown", (e) => {
    if (S.tab !== "explorer" || !EX.model || /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName) && document.activeElement.type !== "range") return;
    if (e.key === "ArrowLeft") { exGo(-1); e.preventDefault(); }
    else if (e.key === "ArrowRight") { exGo(1); e.preventDefault(); }
    else if (e.key === " ") { exTogglePlay(); e.preventDefault(); }
  });
}

function b64f(b64) {
  const bin = atob(b64), buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return new Float32Array(buf.buffer);
}

async function exGeometries(parts) {
  const need = [...new Set(parts)].filter((p) => !(p in EX.geo));
  for (let i = 0; i < need.length; i += 120) {
    const chunk = need.slice(i, i + 120);
    const lbl = $("#exLoading");
    if (lbl) lbl.textContent = `Chargement des pièces… ${Math.min(i + 120, need.length)} / ${need.length}`;
    const r = await api("/api/parts-batch", { method: "POST", body: JSON.stringify(chunk) });
    for (const p of chunk) EX.geo[p] = r[p] ? { tris: b64f(r[p].tris), edges: b64f(r[p].edges), title: r[p].title } : null;
  }
}

async function exBuild(model) {
  exStop();
  const { root, camera, controls } = EX.three;
  root.children.slice().forEach((c) => { root.remove(c); c.traverse((o) => o.geometry && o.geometry.dispose()); });
  EX.model = model; EX.groups = [];
  await exGeometries(model.parts.map((p) => p.part));
  const n = Math.max(1, model.steps);
  // tailles par étape
  const cnt = Array.from({ length: n }, () => ({ s: 0, t: 0, e: 0 }));
  const col = new THREE.Color();
  for (const p of model.parts) {
    const g = EX.geo[p.part]; if (!g) continue;
    const c = EX.colors[p.color] || {};
    cnt[p.step][c.alpha < 1 ? "t" : "s"] += g.tris.length; cnt[p.step].e += g.edges.length;
  }
  const buf = cnt.map((k) => ({ s: new Float32Array(k.s), sc: new Float32Array(k.s), t: new Float32Array(k.t), tc: new Float32Array(k.t), e: new Float32Array(k.e), o: { s: 0, t: 0, e: 0 } }));
  const put = (src, dst, cdst, off, M, rgb) => {
    const [x, y, z, a, b, c, d, e, f, g, hh, i] = M;
    for (let k = 0; k < src.length; k += 3) {
      const vx = src[k], vy = src[k + 1], vz = src[k + 2];
      dst[off + k] = a * vx + b * vy + c * vz + x; dst[off + k + 1] = d * vx + e * vy + f * vz + y; dst[off + k + 2] = g * vx + hh * vy + i * vz + z;
      if (cdst) { cdst[off + k] = rgb.r; cdst[off + k + 1] = rgb.g; cdst[off + k + 2] = rgb.b; }
    }
  };
  for (const p of model.parts) {
    const g = EX.geo[p.part]; if (!g) continue;
    const c = EX.colors[p.color] || { hex: "#9a9a9a", alpha: 1 };
    col.set(c.hex);
    const B = buf[p.step], key = c.alpha < 1 ? "t" : "s";
    put(g.tris, B[key], B[key + "c"], B.o[key], p.m, col); B.o[key] += g.tris.length;
    put(g.edges, B.e, null, B.o.e, p.m, null); B.o.e += g.edges.length;
  }
  const mk = (pos, colr) => { const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.BufferAttribute(pos, 3)); if (colr) geo.setAttribute("color", new THREE.BufferAttribute(colr, 3)); return geo; };
  for (const B of buf) {
    const grp = new THREE.Group();
    if (B.s.length) { const g = mk(B.s, B.sc); g.computeVertexNormals(); const m = new THREE.Mesh(g, EX.mats.solid); m.userData.solid = true; grp.add(m); }
    if (B.t.length) { const g = mk(B.t, B.tc); g.computeVertexNormals(); const m = new THREE.Mesh(g, EX.mats.trans); m.renderOrder = 2; grp.add(m); }
    if (B.e.length) grp.add(new THREE.LineSegments(mk(B.e), EX.mats.edge));
    root.add(grp); EX.groups.push(grp);
  }
  const lbl = $("#exLoading"); if (lbl) lbl.remove();
  // cadrage
  root.updateMatrixWorld(true);
  const bb = new THREE.Box3().setFromObject(root), center = bb.getCenter(new THREE.Vector3()), size = bb.getSize(new THREE.Vector3());
  const r = Math.max(size.x, size.y, size.z) * 1.7 + 2;
  camera.position.copy(center).add(new THREE.Vector3(0.75, 0.6, -0.9).normalize().multiplyScalar(r));
  camera.near = r / 200; camera.far = r * 20; camera.updateProjectionMatrix();
  controls.target.copy(center); controls.update();
  const range = $("#exRange"); if (range) range.max = n - 1;
  exSetStep(n - 1);
}

function exSetStep(k) {
  if (!EX.model) return;
  const n = EX.groups.length;
  k = Math.max(0, Math.min(n - 1, k));
  EX.step = k;
  const last = k === n - 1;
  EX.groups.forEach((g, i) => {
    g.visible = i <= k;
    const solid = g.children.find((o) => o.userData.solid);
    if (solid) solid.material = i === k && !last ? EX.mats.hi : EX.mats.solid;
  });
  const here = EX.model.parts.filter((p) => p.step === k);
  const done = EX.model.parts.filter((p) => p.step <= k).length;
  $("#exRange").value = k;
  $("#exStepLbl").textContent = `Étape ${k + 1} / ${n} · +${here.length} pièce(s) · ${done} posées` +
    (here[0] ? ` · ${here[0].sub.replace(/^\S+ - /, "")}` : "");
}
const exGo = (d) => exSetStep((EX.step ?? 0) + d);
function exTogglePlay() {
  if (EX.play) return exStop();
  if (EX.step >= EX.groups.length - 1) exSetStep(0);
  $("#exPlay").textContent = "❚❚";
  EX.play = setInterval(() => { if (EX.step >= EX.groups.length - 1) exStop(); else exGo(1); }, 450);
}
function exStop() {
  clearInterval(EX.play); EX.play = null;
  const b = $("#exPlay"); if (b) b.textContent = "▶";
}

// ------------------------------------------------------------------ inventaire officiel (Rebrickable)

async function exInventory(s) {
  exStop();
  const el = $("#page-explorer");
  $("#pageHead").replaceChildren(
    h("div", { class: "ph-subject" }, h("img", { src: s.thumb, alt: "" }),
      h("div", {}, h("div", { class: "ph-meta" }, h("a", { href: "#/explorateur" }, "Explorateur"), h("span", {}, "/"),
        h("span", { class: "mono" }, s.num), h("span", {}, s.theme.replace(/ > /g, " · ")), h("span", {}, String(s.year)),
        h("span", { class: `ex-src-inline ex-src-${srcOf(s)}`, title: SOURCES[srcOf(s)].tip }, SOURCES[srcOf(s)].label)),
        h("h1", {}, s.name))));
  el.replaceChildren(h("p", { class: "muted" }, "Chargement de l'inventaire…"));
  const inv = await api(`/api/rb/set/${encodeURIComponent(s.num)}`);
  if (location.hash.split("/")[2] !== encodeURIComponent(s.num)) return;
  let only = null;                                       // filtre couleur
  const byCol = Object.values(inv.parts.reduce((a, p) => {
    const k = a[p.color] || (a[p.color] = { color: p.color, cname: p.cname, rgb: p.rgb, trans: p.trans, qty: 0 });
    k.qty += p.qty; return a;
  }, {})).sort((a, b) => b.qty - a.qty);
  const swatch = (rgb, trans) => h("i", { style: `background:#${rgb}${trans ? ";opacity:.55" : ""}` });
  const grid = h("div", { class: "ex-inv" });
  const draw = () => grid.replaceChildren(...inv.parts.filter((p) => only == null || p.color === only).map((p) =>
    h("a", { class: "ex-invcard", href: `https://rebrickable.com/parts/${encodeURIComponent(p.part)}/`, target: "_blank", rel: "noopener", title: `${p.part} · ${p.name} · ${p.cname}` },
      h("div", { class: "ex-invimg" }, p.img ? h("img", { src: p.img, alt: "", loading: "lazy", decoding: "async" }) : h("span", { class: "muted" }, p.part)),
      h("b", { class: "ex-qty" }, "×" + p.qty),
      h("small", { class: "ex-pname" }, p.name || p.part),
      h("small", { class: "ex-pcol" }, swatch(p.rgb, p.trans), p.cname))));
  const csv = () => {
    const lines = [["part", "name", "color_id", "color", "rgb", "qty", "spare"].join(",")]
      .concat([...inv.parts, ...inv.spares].map((p) => [p.part, `"${(p.name || "").replace(/"/g, '""')}"`, p.color, `"${p.cname}"`, p.rgb, p.qty, p.spare ? 1 : 0].join(",")));
    const a = h("a", { href: URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" })), download: `${s.num}-inventaire.csv` });
    a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  const kv = (k, v) => h("div", { class: "kpi" }, h("dt", {}, k), h("dd", {}, String(v)));
  const cols = h("div", { class: "ex-cols ex-colsel" }, byCol.map((c) =>
    h("button", { class: "ex-col", "aria-pressed": "false", title: `${c.cname} · ${c.qty} pièces`, onclick: (e) => {
      only = only === c.color ? null : c.color;
      cols.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", "false"));
      if (only != null) e.currentTarget.setAttribute("aria-pressed", "true");
      draw();
    } }, swatch(c.rgb, c.trans), c.qty)));
  el.replaceChildren(...kids(
    s.src === "omr" ? h("nav", { class: "subtabs ex-models" },
      h("a", { class: "subtab", href: `#/explorateur/${encodeURIComponent(s.num)}` }, "Vue 3D et notice"),
      h("a", { class: "subtab", href: "#", "aria-current": "true", onclick: (e) => e.preventDefault() }, "Inventaire officiel")) : null,
    h("div", { class: "ex-detail" },
      h("div", { class: "ex-view" },
        h("div", { class: "ex-photo" }, h("img", { src: inv.img, alt: s.name })),
        h("h3", { class: "ex-invtitle" }, `Pièces (${inv.parts.length} lignes)`),
        grid),
      h("aside", { class: "ex-side" },
        h("dl", { class: "kpis ex-kpis" }, kv("Pièces", inv.count), kv("Références", inv.unique), kv("Couleurs", inv.colors), kv("Minifigs", inv.minifigs.reduce((n, f) => n + f.qty, 0))),
        h("div", { class: "actions" },
          h("button", { class: "btn", onclick: csv }, "Télécharger l'inventaire (CSV)"),
          h("a", { class: "btn", href: `https://rebrickable.com/sets/${encodeURIComponent(s.num)}/`, target: "_blank", rel: "noopener" }, "Voir sur Rebrickable")),
        h("p", { class: "muted small" }, s.src === "omr" ? "Inventaire de la boîte d'après Rebrickable." :
          "Pas de modèle 3D pour ce set dans l'OMR LDraw : on a l'inventaire exact de la boîte (Rebrickable), sans positions ni étapes."),
        h("h3", {}, "Couleurs (clic : filtrer)"), cols,
        inv.minifigs.length ? [h("h3", {}, "Minifigs"), h("div", { class: "ex-figs" }, inv.minifigs.map((f) =>
          h("div", { class: "ex-fig", title: f.name }, f.img ? h("img", { src: f.img, alt: "", loading: "lazy" }) : null, h("small", {}, `${f.qty > 1 ? f.qty + " × " : ""}${f.name}`))))] : null,
        inv.spares.length ? h("p", { class: "muted small" }, `+ ${inv.spares.reduce((n, p) => n + p.qty, 0)} pièces de rechange (incluses dans le CSV).`) : null))));
  draw();
}
