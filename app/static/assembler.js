// Brick Forge Lab — Assembler : éditeur 3D avec la vraie géométrie LDraw
"use strict";

const ASM = {
  doc: null, ready: false, sel: null, undo: [], saveTimer: null,
  geo: {}, geoPending: {}, mats: {}, objs: {}, thumbs: {},
  showStruct: true, highlight: true, cam: "34",
};
const LDU = 1 / 20; // 1 tenon = 20 LDU

// ------------------------------------------------------------------ géométrie des pièces

function b64f32(b64) {
  const bin = atob(b64), buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return new Float32Array(buf.buffer);
}
async function partGeo(part) {
  if (ASM.geo[part]) return ASM.geo[part];
  if (!ASM.geoPending[part]) {
    ASM.geoPending[part] = api(`/api/parts/${encodeURIComponent(part)}`).then((m) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(b64f32(m.tris), 3));
      g.computeVertexNormals();
      const e = new THREE.BufferGeometry();
      e.setAttribute("position", new THREE.BufferAttribute(b64f32(m.edges), 3));
      const lo = m.bbox[0], hi = m.bbox[1];
      return (ASM.geo[part] = { mesh: g, edges: e, info: m, center: [(lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2] });
    });
  }
  return ASM.geoPending[part];
}
function material(color, state) {
  const key = color + ":" + state;
  if (!ASM.mats[key]) {
    const c = new THREE.Color(colorHex(color));
    const opt = { color: c, roughness: 0.35, metalness: 0, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 };
    if (state === "sel") Object.assign(opt, { emissive: new THREE.Color("#00b8ff"), emissiveIntensity: 0.55 });
    if (state === "todo") Object.assign(opt, { emissive: new THREE.Color("#ff7a00"), emissiveIntensity: 0.28 });
    if (state === "unknown") Object.assign(opt, { emissive: new THREE.Color("#ff0030"), emissiveIntensity: 0.45 });
    if (state === "ghost") Object.assign(opt, { transparent: true, opacity: 0.28, depthWrite: false });
    ASM.mats[key] = new THREE.MeshStandardMaterial(opt);
  }
  return ASM.mats[key];
}
const EDGE_MAT = new THREE.LineBasicMaterial({ color: 0x1a1a1a, transparent: true, opacity: 0.55 });
const EDGE_SEL = new THREE.LineBasicMaterial({ color: 0x00b8ff });

// ------------------------------------------------------------------ scène

function makeScene() {
  const box = $("#asm3d");
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: false });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  box.prepend(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 2000);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x7d756a, 0.7));
  const d1 = new THREE.DirectionalLight(0xffffff, 0.65); d1.position.set(15, 30, -20); scene.add(d1);
  const d2 = new THREE.DirectionalLight(0xffffff, 0.25); d2.position.set(-20, 10, 25); scene.add(d2);
  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  const root = new THREE.Group();
  root.scale.set(LDU, -LDU, LDU); // LDraw : Y vers le bas -> Three : Y vers le haut
  scene.add(root);
  const grid = new THREE.GridHelper(60, 60, 0x999999, 0xcccccc);
  grid.material.transparent = true; grid.material.opacity = 0.35;
  scene.add(grid);
  ASM.three = { renderer, scene, camera, controls, root, box, grid };
  const resize = () => { const w = box.clientWidth, hh = box.clientHeight; if (!w || !hh) return; renderer.setSize(w, hh, false); camera.aspect = w / hh; camera.updateProjectionMatrix(); };
  new ResizeObserver(resize).observe(box); resize();
  (function loop() { controls.update(); Photo.tick(ASM.three); Photo.render(ASM.three); requestAnimationFrame(loop); })();

  // sélection au clic (sans glisser)
  let down = null;
  renderer.domElement.addEventListener("pointerdown", (e) => (down = [e.clientX, e.clientY]));
  renderer.domElement.addEventListener("pointerup", (e) => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
    const r = renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    const ray = new THREE.Raycaster(); ray.setFromCamera(ndc, camera);
    const meshes = Object.values(ASM.objs).filter((o) => o.visible).map((o) => o.children[0]);
    const hit = ray.intersectObjects(meshes, false)[0];
    asmSelect(hit ? hit.object.parent.userData.id : null);
  });
}

function partMatrix(m) {
  const M = new THREE.Matrix4();
  M.set(m[3], m[4], m[5], m[0], m[6], m[7], m[8], m[1], m[9], m[10], m[11], m[2], 0, 0, 0, 1);
  return M;
}
function partState(p) {
  if (ASM.sel === p.id) return "sel";
  if (p.src === "structure" && !ASM.showStruct) return "ghost";
  if (!ASM.highlight) return "plain";
  if (p.status === "inconnue") return "unknown";
  if (p.status === "à vérifier") return "todo";
  return "plain";
}
async function syncObject(p) {
  const g = await partGeo(p.part);
  let o = ASM.objs[p.id];
  if (!o || o.userData.part !== p.part) {
    if (o) ASM.three.root.remove(o);
    o = new THREE.Group();
    o.add(new THREE.Mesh(g.mesh), new THREE.LineSegments(g.edges, EDGE_MAT));
    o.matrixAutoUpdate = false;
    o.userData = { id: p.id, part: p.part };
    ASM.three.root.add(o);
    ASM.objs[p.id] = o;
  }
  o.matrix.copy(partMatrix(p.m));
  const st = partState(p);
  o.children[0].material = material(p.color, st);
  o.children[1].material = st === "sel" ? EDGE_SEL : EDGE_MAT;
  o.children[1].visible = st !== "ghost";
  o.visible = !(p.src === "structure" && ASM.structHidden) && !(ASM.step != null && p.step != null && p.step > ASM.step);
}
async function syncAll() {
  const ids = new Set(ASM.doc.parts.map((p) => p.id));
  for (const id of Object.keys(ASM.objs)) if (!ids.has(id)) { ASM.three.root.remove(ASM.objs[id]); delete ASM.objs[id]; }
  await Promise.all(ASM.doc.parts.map(syncObject));
  asmStats();
}

// ------------------------------------------------------------------ caméra

function modelBox() {
  const b = new THREE.Box3();
  for (const o of Object.values(ASM.objs)) if (o.visible) b.expandByObject(o);
  return b.isEmpty() ? new THREE.Box3(new THREE.Vector3(-5, 0, -5), new THREE.Vector3(5, 5, 5)) : b;
}
const CAMS = {
  "34": { dir: [0.75, 0.62, -0.9], up: [0, 1, 0], view: "concept", label: "3/4" },
  dessus: { dir: [0, 1, 0.0001], up: [0, 0, -1], view: "dessus", label: "Dessus" },
  profil: { dir: [1, 0.08, 0], up: [0, 1, 0], view: "profil", label: "Profil" },
  face: { dir: [0, 0.08, -1], up: [0, 1, 0], view: "face", label: "Face" },
  dos: { dir: [0, 0.08, 1], up: [0, 1, 0], view: "dos", label: "Dos" },
  dessous: { dir: [0, -1, 0.0001], up: [0, 0, -1], view: "dessous", label: "Dessous" },
};
function setCam(name) {
  ASM.cam = name;
  const c = CAMS[name], { camera, controls } = ASM.three;
  const b = modelBox(), center = b.getCenter(new THREE.Vector3()), size = b.getSize(new THREE.Vector3());
  const r = Math.max(size.x, size.y, size.z) * 1.9 + 4;
  const d = new THREE.Vector3(...c.dir).normalize();
  camera.up.set(...c.up);
  camera.position.copy(center).addScaledVector(d, r);
  controls.target.copy(center); controls.update();
  $$(".camBtn").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.cam === name)));
  const v = S.detail.views.find((x) => x.name === c.view) || S.detail.views[0];
  $("#asmRef").replaceChildren(v ? h("img", { src: v.thumb || v.url, alt: "Vue " + v.name, onclick: () => openLightbox(v.url) }) : "",
    h("figcaption", {}, v ? `Vue Gemini : ${v.name}` : "pas de vue"));
}

// ------------------------------------------------------------------ chargement de l'onglet

async function renderAssembler() {
  if (!ASM.three) { makeScene(); bindAsm(); }
  const subject = S.subject;
  if (ASM.doc && ASM.doc.subject === subject) { asmSide(); return; }
  if (ASM.loadingFor === subject) return; // déjà en cours de chargement
  ASM.loadingFor = subject;
  try { await loadAssembly(subject); } finally { ASM.loadingFor = null; }
}
async function loadAssembly(subject) {
  for (const o of Object.values(ASM.objs)) ASM.three.root.remove(o);
  ASM.objs = {}; ASM.sel = null; ASM.undo = []; ASM.step = null;
  try {
    ASM.doc = await api(`/api/subjects/${subject}/assembly`);
    ASM.doc.subject = subject;
    $("#asmEmpty").hidden = true;
    await syncAll();
    setCam(ASM.cam);
  } catch (e) {
    ASM.doc = null;
    $("#asmEmpty").hidden = false;
    const canBuild = S.detail.views.some((v) => v.name === "profil") && S.detail.views.some((v) => v.name === "face");
    $("#asmEmpty").replaceChildren(h("div", { class: "box" },
      h("b", {}, "Pas encore d'assemblage pour ce sujet"),
      canBuild && S.runId
        ? [h("span", {}, "Je construis le modèle 3D à partir des pièces reconnues du lancement sélectionné en haut. Tu pourras ensuite remplacer, tourner ou déplacer chaque pièce."),
           h("button", { class: "btn primary", onclick: buildAssembly }, "Construire le modèle 3D")]
        : h("span", {}, "Il faut un lancement et les vues dessus, profil et face.")));
  }
  asmSide();
}
async function buildAssembly(arg) {
  const force = arg === true;
  const btn = arg && arg.target ? arg.target : null;
  if (btn) { btn.disabled = true; btn.textContent = "Construction… (~10 s)"; }
  try {
    await api(`/api/subjects/${S.subject}/assembly/from-run/${S.runId}${force ? "?force=true" : ""}`, { method: "POST" });
    ASM.doc = null; await renderAssembler(); setCam(ASM.cam);
  } catch (e) { alertBar(e.message); if (btn) btn.disabled = false; }
}

// ------------------------------------------------------------------ inspecteur

function asmStats() {
  if (!ASM.doc) return;
  const det = ASM.doc.parts.filter((p) => p.src !== "structure");
  const ok = det.filter((p) => p.status === "ok").length;
  const unk = det.filter((p) => p.status === "inconnue").length;
  $("#asmStats").textContent = `${ok}/${det.length} pièces vérifiées · ${unk} inconnues · ${ASM.doc.parts.length} pièces au total`;
}
function selPart() { return ASM.doc && ASM.doc.parts.find((p) => p.id === ASM.sel); }

// notice : n'affiche que les pièces des étapes 0..ASM.step ; celles de l'étape courante sont mises en avant
function setStep(k) {
  const n = ASM.doc.steps;
  ASM.step = k == null || k >= n - 1 ? null : Math.max(0, k);
  for (const p of ASM.doc.parts) {
    const o = ASM.objs[p.id];
    if (!o) continue;
    o.visible = !(p.src === "structure" && ASM.structHidden) && !(ASM.step != null && p.step > ASM.step);
    o.children[0].material = material(p.color, ASM.step != null && p.step === ASM.step ? "sel" : partState(p));
  }
  const cur = ASM.step == null ? n - 1 : ASM.step;
  const here = ASM.doc.parts.filter((p) => p.step === cur);
  const lbl = $("#stepLbl");
  if (lbl) lbl.textContent = `Étape ${cur + 1} / ${n} · ${here.length} pièce(s)` + (here[0] ? ` · ${here[0].sub.replace(/^\d+ - /, "")}` : "");
  const r = $("#stepRange");
  if (r) r.value = cur;
}
function stepPanel() {
  const n = ASM.doc.steps, cur = ASM.step == null ? n - 1 : ASM.step;
  const go = (d) => setStep((ASM.step == null ? n - 1 : ASM.step) + d);
  const box = h("div", { class: "stepbox" },
    h("input", { type: "range", id: "stepRange", min: 0, max: n - 1, value: cur, style: "width:100%",
      oninput: (e) => setStep(+e.target.value) }),
    h("div", { class: "actions" },
      h("button", { class: "btn small", onclick: () => go(-1) }, "◀ Précédente"),
      h("button", { class: "btn small", onclick: () => go(1) }, "Suivante ▶"),
      h("button", { class: "btn small", onclick: () => setStep(0) }, "Début"),
      h("button", { class: "btn small", onclick: () => setStep(null) }, "Fin")),
    h("small", { id: "stepLbl", class: "muted" }));
  setTimeout(() => setStep(ASM.step), 0);
  return box;
}

function asmSide() {
  const el = $("#asmInspector");
  if (!ASM.doc) { el.replaceChildren(); return; }
  const p = selPart();
  if (!p && ASM.doc.steps) {   // vrai set (OMR) : notice étape par étape
    el.replaceChildren(h("h3", {}, "Notice"), stepPanel(),
      h("p", { class: "muted" }, `Set officiel importé de l'OMR LDraw (${ASM.doc.author || "auteur inconnu"}, licence CCAL 2.0). ${ASM.doc.parts.length} pièces, ${ASM.doc.steps} étapes.`));
    return;
  }
  if (!p) {
    el.replaceChildren(
      h("h3", {}, "Assemblage"),
      h("p", { class: "muted" }, "Clique une pièce dans la vue 3D. Les pièces en orange sont à vérifier, en rouge celles que le moteur n'a pas su identifier (posées comme plaque provisoire)."),
      h("div", { class: "actions" },
        h("button", { class: "btn primary", onclick: () => asmNext() }, "Pièce suivante à vérifier (N)"),
        h("button", { class: "btn", onclick: () => openGallery("add") }, "Ajouter une pièce (A)")),
      h("button", { class: "btn small danger", onclick: (e) => {
        if (e.currentTarget.dataset.armed) buildAssembly(true);
        else { e.currentTarget.dataset.armed = "1"; e.currentTarget.textContent = "Cliquer encore : tout reconstruire et perdre les corrections"; }
      } }, "Reconstruire à partir du lancement sélectionné"));
    return;
  }
  const g = ASM.geo[p.part];
  const title = g ? g.info.title : p.part;
  const det = p.det != null && S.pred[p.det] ? S.pred[p.det] : null;
  el.replaceChildren(
    h("h3", {}, p.part, h("span", { class: "badge" + (p.status === "ok" ? " ok" : "") }, p.status)),
    h("div", { class: "muted", style: "font-size:13px" }, title),
    h("div", { class: "muted", style: "font-size:12px" }, p.src === "structure" ? "Structure (volume reconstruit)" : p.src === "manuel" ? "Ajoutée à la main" :
      det ? `Détection n°${p.det + 1} · taille mesurée ${det.size.join("×")} · ${det.n_studs} tenon(s)` : "Détection"),
    h("div", { class: "actions" },
      h("button", { class: "btn primary", onclick: () => openGallery("replace") }, "Remplacer (E)"),
      h("button", { class: "btn", onclick: () => asmValidate(p) }, p.status === "ok" ? "Remettre à vérifier" : "Valider (V)")),
    h("div", { class: "field" }, h("span", {}, "Couleur"),
      h("div", { class: "swatches" }, S.catalog.colors.map((c) =>
        h("button", { class: "swatch", style: `background:${c.hex}`, title: c.name, "aria-pressed": String(p.color === c.code), onclick: () => asmEdit((q) => (q.color = c.code)) }))),
      h("span", { class: "colorname" }, colorName(p.color))),
    h("div", { class: "field" }, h("span", {}, "Position"),
      h("div", { class: "actions" },
        h("button", { class: "btn small", onclick: () => asmRotate(1), title: "R" }, "↻ 90°"),
        h("button", { class: "btn small", onclick: () => asmRotate(-1), title: "Maj+R" }, "↺ 90°"),
        h("button", { class: "btn small", onclick: () => asmMove(0, -8, 0), title: "Page préc." }, "▲ 1 plaque"),
        h("button", { class: "btn small", onclick: () => asmMove(0, 8, 0), title: "Page suiv." }, "▼ 1 plaque")),
      h("span", { class: "muted", style: "font-size:12px" }, "Flèches : déplacer d'un tenon (Alt : demi-tenon), selon l'angle de la caméra.")),
    h("div", { class: "actions" },
      h("button", { class: "btn", onclick: asmDuplicate, title: "Ctrl+D" }, "Dupliquer"),
      h("button", { class: "btn danger", onclick: asmDelete, title: "Suppr" }, "Supprimer"),
      h("button", { class: "btn", onclick: () => asmNext() }, "Suivante (N)")));
}

// ------------------------------------------------------------------ édition

function snapshot() {
  ASM.undo.push(JSON.stringify(ASM.doc.parts));
  if (ASM.undo.length > 150) ASM.undo.shift();
}
function asmChanged() {
  $("#asmSave").textContent = "Modifié…";
  clearTimeout(ASM.saveTimer);
  ASM.saveTimer = setTimeout(async () => {
    try { await api(`/api/subjects/${ASM.doc.subject}/assembly`, { method: "PUT", body: JSON.stringify(ASM.doc) }); $("#asmSave").textContent = "Enregistré"; }
    catch (e) { $("#asmSave").textContent = "Échec : " + e.message; }
  }, 600);
  asmStats();
}
async function asmEdit(fn) {
  const p = selPart(); if (!p) return;
  snapshot(); fn(p); await syncObject(p); asmChanged(); asmSide();
}
function asmSelect(id) {
  const prev = ASM.sel; ASM.sel = id;
  for (const pid of [prev, id]) { const p = ASM.doc && ASM.doc.parts.find((q) => q.id === pid); if (p) syncObject(p); }
  asmSide();
}
function asmValidate(p) {
  snapshot();
  p.status = p.status === "ok" ? (p.src === "structure" ? "structure" : "à vérifier") : "ok";
  syncObject(p); asmChanged();
  if (p.status === "ok") asmNext(); else asmSide();
}
function asmNext() {
  const list = ASM.doc.parts.filter((p) => p.src !== "structure");
  const start = Math.max(0, list.findIndex((p) => p.id === ASM.sel));
  const order = ["inconnue", "à vérifier"];
  for (const st of order) for (let k = 1; k <= list.length; k++) {
    const p = list[(start + k) % list.length];
    if (p.status === st) { asmSelect(p.id); focusObj(p.id); return; }
  }
  asmSelect(null);
}
function focusObj(id) {
  const o = ASM.objs[id]; if (!o) return;
  const c = new THREE.Box3().setFromObject(o).getCenter(new THREE.Vector3());
  const { camera, controls } = ASM.three;
  camera.position.add(c.clone().sub(controls.target));
  controls.target.copy(c);
}
function centerOf(p, g) { // centre de la boîte englobante, monde LDraw (x, z)
  const m = p.m, [cx, cz] = g.center;
  return [m[0] + m[3] * cx + m[5] * cz, m[2] + m[9] * cx + m[11] * cz];
}
async function asmReplace(part) {
  const p = selPart(); if (!p) return;
  const og = await partGeo(p.part), ng = await partGeo(part);
  snapshot();
  const [cx, cz] = centerOf(p, og);
  const top = p.m[1] + og.info.body_top;
  const m = p.m;
  const [nx, nz] = ng.center;
  m[0] = cx - (m[3] * nx + m[5] * nz);
  m[2] = cz - (m[9] * nx + m[11] * nz);
  m[1] = top - ng.info.body_top;
  p.part = part;
  p.status = "ok";
  await syncObject(p); asmChanged(); asmSide();
}
async function asmRotate(sign) {
  const p = selPart(); if (!p) return;
  const g = await partGeo(p.part);
  snapshot();
  const [cx, cz] = centerOf(p, g);
  const m = p.m;
  const R = [m[3], m[4], m[5], m[6], m[7], m[8], m[9], m[10], m[11]];
  const c = 0, s = sign; // rotation de 90° autour de Y : [[c,0,s],[0,1,0],[-s,0,c]]
  const Ry = [c, 0, s, 0, 1, 0, -s, 0, c];
  const mul = (A, B) => [0, 1, 2].flatMap((i) => [0, 1, 2].map((j) => A[i * 3] * B[j] + A[i * 3 + 1] * B[3 + j] + A[i * 3 + 2] * B[6 + j]));
  const N = mul(Ry, R).map((v) => Math.round(v * 1e6) / 1e6);
  for (let k = 0; k < 9; k++) m[3 + k] = N[k];
  const [nx, nz] = g.center;
  m[0] = cx - (m[3] * nx + m[5] * nz);
  m[2] = cz - (m[9] * nx + m[11] * nz);
  await syncObject(p); asmChanged();
}
function camAxes() { // directions « avant » et « droite » de la caméra, ramenées aux axes X/Z
  const { camera, controls } = ASM.three;
  const f = controls.target.clone().sub(camera.position); f.y = 0;
  if (f.lengthSq() < 1e-6) { const u = camera.up.clone(); f.set(u.x, 0, u.z); }
  const fwd = Math.abs(f.x) > Math.abs(f.z) ? [Math.sign(f.x), 0] : [0, Math.sign(f.z)];
  const right = [-fwd[1], fwd[0]];
  return { fwd, right };
}
async function asmMove(dx, dy, dz) {
  const p = selPart(); if (!p) return;
  snapshot(); p.m[0] += dx; p.m[1] += dy; p.m[2] += dz;
  await syncObject(p); asmChanged();
}
async function asmDuplicate() {
  const p = selPart(); if (!p) return;
  snapshot();
  const q = JSON.parse(JSON.stringify(p));
  q.id = "m" + Date.now().toString(36); q.src = "manuel"; q.status = "ok"; delete q.det;
  q.m[0] += 20;
  ASM.doc.parts.push(q);
  await syncObject(q); asmSelect(q.id); asmChanged();
}
async function asmDelete() {
  const p = selPart(); if (!p) return;
  snapshot();
  ASM.doc.parts = ASM.doc.parts.filter((q) => q !== p);
  ASM.three.root.remove(ASM.objs[p.id]); delete ASM.objs[p.id];
  ASM.sel = null; asmChanged(); asmSide();
}
async function asmAdd(part) {
  const ref = selPart();
  const g = await partGeo(part);
  snapshot();
  let x = 0, z = 0, top = 0;
  if (ref) {
    const rg = await partGeo(ref.part);
    [x, z] = centerOf(ref, rg);
    top = ref.m[1] + rg.info.body_top; // on pose la nouvelle pièce sur la pièce sélectionnée
  } else {
    const b = modelBox(); const c = b.getCenter(new THREE.Vector3());
    x = c.x / LDU; z = c.z / LDU; top = -b.max.y / LDU;
  }
  const [nx, nz] = g.center;
  const q = { id: "m" + Date.now().toString(36), part, color: ref ? ref.color : 71, src: "manuel", status: "ok",
    m: [x - nx, top - g.info.height - g.info.body_top, z - nz, 1, 0, 0, 0, 1, 0, 0, 0, 1] };
  ASM.doc.parts.push(q);
  await syncObject(q); asmSelect(q.id); asmChanged();
}
async function asmUndo() {
  const prev = ASM.undo.pop(); if (!prev) return;
  ASM.doc.parts = JSON.parse(prev);
  await syncAll(); asmSide(); asmChanged();
}

// ------------------------------------------------------------------ galerie de pièces

let thumbRenderer = null;
async function thumb(part, color) {
  const key = part + ":" + color;
  if (ASM.thumbs[key]) return ASM.thumbs[key];
  const g = await partGeo(part);
  if (!thumbRenderer) {
    thumbRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    thumbRenderer.setSize(140, 140); thumbRenderer.setPixelRatio(1);
  }
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x7d756a, 0.8));
  const d = new THREE.DirectionalLight(0xffffff, 0.6); d.position.set(10, 20, -15); scene.add(d);
  const grp = new THREE.Group(); grp.scale.set(1, -1, 1);
  grp.add(new THREE.Mesh(g.mesh, material(color, "plain")), new THREE.LineSegments(g.edges, EDGE_MAT));
  scene.add(grp);
  const box = new THREE.Box3().setFromObject(grp), c = box.getCenter(new THREE.Vector3()), s = box.getSize(new THREE.Vector3()).length();
  const cam = new THREE.PerspectiveCamera(30, 1, 0.1, 5000);
  cam.position.copy(c).add(new THREE.Vector3(0.9, 0.75, -1.05).normalize().multiplyScalar(s * 1.7));
  cam.lookAt(c);
  thumbRenderer.render(scene, cam);
  return (ASM.thumbs[key] = thumbRenderer.domElement.toDataURL());
}
let galleryMode = "replace", galleryKind = "", gallerySearch = "";
function openGallery(mode) {
  galleryMode = mode;
  const p = selPart();
  const info = p && S.catalog.parts.find((c) => c.part === p.part);
  galleryKind = info ? info.kind : "";
  gallerySearch = "";
  $("#gallery").hidden = false;
  $("#galTitle").textContent = mode === "replace" ? `Remplacer ${p ? p.part : ""} par…` : "Ajouter une pièce";
  $("#galSearch").value = "";
  renderGallery();
  setTimeout(() => $("#galSearch").focus(), 30);
}
function closeGallery() { $("#gallery").hidden = true; }
async function renderGallery() {
  const p = selPart();
  const color = p ? p.color : 71;
  const kinds = ["", "plate", "tile", "curved", "slope", "round", "wedge", "brick", "snot"];
  $("#galKinds").replaceChildren(...kinds.map((k) =>
    h("button", { class: "chip", "aria-pressed": String(galleryKind === k), onclick: () => { galleryKind = k; renderGallery(); } }, k ? KIND_FR[k] : "toutes")));
  const q = gallerySearch.toLowerCase();
  const cur = p && S.catalog.parts.find((c) => c.part === p.part);
  let list = S.catalog.parts.filter((c) => (!galleryKind || c.kind === galleryKind) && (!q || (c.part + " " + c.name).toLowerCase().includes(q)));
  if (cur) list = list.sort((a, b) => (Math.abs(a.size[0] * a.size[1] - cur.size[0] * cur.size[1]) - Math.abs(b.size[0] * b.size[1] - cur.size[0] * cur.size[1])));
  const grid = $("#galGrid");
  grid.replaceChildren(...list.map((c) => {
    const img = h("img", { alt: "", width: 140, height: 140 });
    const card = h("button", { class: "galcard" + (p && c.part === p.part ? " current" : ""), title: c.name, onclick: () => {
      closeGallery(); if (galleryMode === "replace") asmReplace(c.part); else asmAdd(c.part);
    } }, img, h("b", {}, c.part), h("span", {}, c.name.replace(/^~?Moved to.*/, c.part)), c.known ? null : h("small", {}, "inconnue du moteur"));
    thumb(c.part, color).then((u) => (img.src = u)).catch(() => card.remove());
    return card;
  }));
  if (!list.length) grid.replaceChildren(h("p", { class: "muted" }, "Aucune pièce ne correspond."));
}

// ------------------------------------------------------------------ liaisons

function bindAsm() {
  $$(".camBtn").forEach((b) => b.addEventListener("click", () => setCam(b.dataset.cam)));
  $("#asmPhoto").replaceChildren(Photo.button(() => ASM.three, null, () => ASM.doc && { three: ASM.three, name: S.subject, parts: ASM.doc.parts.filter((p) => ASM.objs[p.id] && ASM.objs[p.id].visible) }),
    Photo.hdButton(() => ASM.doc && { three: ASM.three, name: S.subject,
      parts: ASM.doc.parts.filter((p) => ASM.objs[p.id] && ASM.objs[p.id].visible) }),
    h("button", { class: "tool", title: "Enregistrer l'image (PNG)", onclick: () => Photo.snapshot(ASM.three, S.subject) }, "Photo"));
  $("#asmStruct").addEventListener("change", (e) => { ASM.structHidden = !e.target.checked; syncAll(); });
  $("#asmHighlight").addEventListener("change", (e) => { ASM.highlight = e.target.checked; syncAll(); });
  $("#asmUndo").addEventListener("click", asmUndo);
  $("#asmExport").addEventListener("click", () => { location.href = `/api/subjects/${S.subject}/assembly.ldr`; });
  $("#galClose").addEventListener("click", closeGallery);
  $("#gallery").addEventListener("click", (e) => { if (e.target.id === "gallery") closeGallery(); });
  $("#galSearch").addEventListener("input", (e) => { gallerySearch = e.target.value; renderGallery(); });
  window.addEventListener("keydown", (e) => {
    if (S.tab !== "assembler" || !ASM.doc) return;
    if (!$("#gallery").hidden) { if (e.key === "Escape") closeGallery(); return; }
    if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
    const p = selPart();
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { asmUndo(); e.preventDefault(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "d") { asmDuplicate(); e.preventDefault(); return; }
    const k = e.key.toLowerCase();
    if (k === "n") asmNext();
    else if (k === "a") openGallery("add");
    else if (!p) { if (e.key === "Escape") asmSelect(null); return; }
    else if (k === "e") openGallery("replace");
    else if (k === "v") asmValidate(p);
    else if (k === "r") asmRotate(e.shiftKey ? -1 : 1);
    else if (e.key === "Delete" || e.key === "Backspace") { asmDelete(); e.preventDefault(); }
    else if (e.key === "Escape") asmSelect(null);
    else if (e.key === "PageUp") { asmMove(0, -8, 0); e.preventDefault(); }
    else if (e.key === "PageDown") { asmMove(0, 8, 0); e.preventDefault(); }
    else if (e.key.startsWith("Arrow")) {
      const step = e.altKey ? 10 : 20, { fwd, right } = camAxes();
      const v = { ArrowUp: fwd, ArrowDown: [-fwd[0], -fwd[1]], ArrowRight: right, ArrowLeft: [-right[0], -right[1]] }[e.key];
      asmMove(v[0] * step, 0, v[1] * step); e.preventDefault();
    }
  });
}
