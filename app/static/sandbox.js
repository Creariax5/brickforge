// Brick Forge Lab — Bac à sable : construire soi-même, pièce par pièce, comme dans un logiciel LEGO.
//
// Choisir une pièce et une couleur -> la pièce fantôme suit la souris en s'alignant sur les tenons ;
// clic : poser (sur la plaque de base ou sur une autre pièce) ; R : tourner ; Maj+clic : supprimer ;
// Alt+clic : pipette (reprendre pièce et couleur) ; Ctrl+Z : annuler. Sauvegarde automatique.
"use strict";

const SB = {
  name: null, doc: null, three: null, objs: {}, ghost: null, part: "3001", color: 4, rot: 0,
  undo: [], saveTimer: null, kind: "", search: "", hover: null, place: null, floating: new Set(),
  snaps: {}, ci: 0, mode: "place", sel: null, fit: null, fitSeq: 0, redo: [],
};
const BASE = 32;                 // plaque de base : 32 x 32 tenons
const STUD = 20, PLATE = 8;

// les 24 rotations d'un quart de tour (matrices LDraw, par lignes)
const SB_ROT24 = (() => {
  const out = [], perms = [[0, 1, 2], [0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]];
  for (const p of perms) for (const a of [1, -1]) for (const b of [1, -1]) for (const c of [1, -1]) {
    const R = [0, 0, 0, 0, 0, 0, 0, 0, 0]; const sg = [a, b, c];
    p.forEach((col, row) => { R[row * 3 + col] = sg[row]; });
    const det = R[0] * (R[4] * R[8] - R[5] * R[7]) - R[1] * (R[3] * R[8] - R[5] * R[6]) + R[2] * (R[3] * R[7] - R[4] * R[6]);
    if (det > 0.5) out.push(R);
  }
  return out;
})();
const mulRv = (R, v) => [R[0] * v[0] + R[1] * v[1] + R[2] * v[2], R[3] * v[0] + R[4] * v[1] + R[5] * v[2], R[6] * v[0] + R[7] * v[1] + R[8] * v[2]];
const mulRR = (A, B) => { const C = []; for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) C.push(A[i * 3] * B[j] + A[i * 3 + 1] * B[3 + j] + A[i * 3 + 2] * B[6 + j]); return C; };
const rnd = (v) => Math.round(v * 100) / 100;

async function sbSnapsFor(parts) {
  const need = [...new Set(parts)].filter((p) => !(p in SB.snaps));
  for (let i = 0; i < need.length; i += 150) {
    const r = await api(`/api/snaps?parts=${encodeURIComponent(need.slice(i, i + 150).join(","))}`);
    Object.assign(SB.snaps, r);
  }
}
function sbWorldSnaps(p) {
  const R = p.m.slice(3), o = p.m.slice(0, 3);
  return (SB.snaps[p.part] || []).filter((s) => !s.slide).map((s) => {
    const q = mulRv(R, s.pos);
    return { g: s.g, pos: [q[0] + o[0], q[1] + o[1], q[2] + o[2]], axis: mulRv(R, s.axis) };
  });
}

function sbRy(q) {               // rotation de q quarts de tour autour de la verticale (matrice LDraw)
  const c = [1, 0, -1, 0][q % 4], s = [0, 1, 0, -1][q % 4];
  return [c, 0, s, 0, 1, 0, -s, 0, c];
}

// ------------------------------------------------------------------ scène

function sbScene() {
  const box = $("#sb3d");
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  box.prepend(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 3000);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x7d756a, 0.75));
  const d1 = new THREE.DirectionalLight(0xffffff, 0.6); d1.position.set(15, 30, -20); scene.add(d1);
  const d2 = new THREE.DirectionalLight(0xffffff, 0.25); d2.position.set(-20, 10, 25); scene.add(d2);
  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };
  // plaque de base (repère Three : 1 unité = 1 tenon, y vers le haut)
  const base = new THREE.Mesh(new THREE.BoxGeometry(BASE, 0.16, BASE), new THREE.MeshStandardMaterial({ color: 0x3f8f4f, roughness: 0.6 }));
  base.position.set(0, -0.08, 0);
  base.userData.base = true;
  scene.add(base);
  const studGeo = new THREE.CylinderGeometry(0.3, 0.3, 0.17, 12);
  const studs = new THREE.InstancedMesh(studGeo, base.material, BASE * BASE);
  const m4 = new THREE.Matrix4(); let n = 0;
  for (let i = 0; i < BASE; i++) for (let j = 0; j < BASE; j++) { m4.makeTranslation(i - BASE / 2 + 0.5, 0.085, j - BASE / 2 + 0.5); studs.setMatrixAt(n++, m4); }
  studs.raycast = () => {};       // les tenons décoratifs ne gênent pas la visée
  scene.add(studs);
  const root = new THREE.Group(); root.scale.set(1 / STUD, -1 / STUD, 1 / STUD); scene.add(root);
  camera.position.set(18, 16, 22); controls.target.set(0, 1, 0); controls.update();
  const resize = () => { const w = box.clientWidth, hh = box.clientHeight; if (!w || !hh) return; renderer.setSize(w, hh, false); camera.aspect = w / hh; camera.updateProjectionMatrix(); };
  new ResizeObserver(resize).observe(box); resize();
  (function loop() { controls.update(); renderer.render(scene, camera); sbCtxUpdate(); requestAnimationFrame(loop); })();
  SB.three = { renderer, scene, camera, controls, root, base, box };
  sbBindPointer();
}

function sbMatrix(m) { const M = new THREE.Matrix4(); M.set(m[3], m[4], m[5], m[0], m[6], m[7], m[8], m[1], m[9], m[10], m[11], m[2], 0, 0, 0, 1); return M; }

async function sbSync(p) {
  const g = await partGeo(p.part);
  let o = SB.objs[p.id];
  if (!o || o.userData.part !== p.part) {
    if (o) SB.three.root.remove(o);
    o = new THREE.Group();
    o.add(new THREE.Mesh(g.mesh), new THREE.LineSegments(g.edges, EDGE_MAT));
    o.matrixAutoUpdate = false; o.userData = { id: p.id, part: p.part };
    SB.three.root.add(o); SB.objs[p.id] = o;
  }
  o.matrix.copy(sbMatrix(p.m));
  const on = SB.hover === p.id || SB.sel === p.id;
  const st = SB.floating.has(p.id) ? "unknown" : on ? "sel" : "plain";
  o.children[0].material = material(p.color, st);
  o.children[1].material = on ? EDGE_SEL : EDGE_MAT;
}
async function sbSyncAll() {
  const ids = new Set(SB.doc.parts.map((p) => p.id));
  for (const id of Object.keys(SB.objs)) if (!ids.has(id)) { SB.three.root.remove(SB.objs[id]); delete SB.objs[id]; }
  await Promise.all(SB.doc.parts.map(sbSync));
  sbStats();
}

// ------------------------------------------------------------------ placement (aligné sur les tenons)

function rotatedBox(info, q) {   // boîte englobante de la pièce tournée de q quarts de tour (LDU)
  const [lo, hi] = info.bbox, R = sbRy(q), xs = [], zs = [];
  for (const x of [lo[0], hi[0]]) for (const z of [lo[2], hi[2]]) { xs.push(R[0] * x + R[2] * z); zs.push(R[6] * x + R[8] * z); }
  return { x0: Math.min(...xs), x1: Math.max(...xs), z0: Math.min(...zs), z1: Math.max(...zs), yBottom: hi[1] };
}

function sbComputePlacement(hit) {
  const g = ASM.geo[SB.part];
  if (!g) return null;
  if (!hit.object.userData.base) {                      // sur une pièce : on s'accroche au tenon ou au creux visé
    const tgt = SB.doc.parts.find((q) => q.id === hit.object.parent.userData.id);
    const snapped = tgt && sbSnapPlacement(sbWorldSnaps(tgt), hit, tgt.id);
    if (snapped) return snapped;
  } else {                                              // plaque de base : une grille de tenons (centres à 10 + 20 k LDU)
    const P = [hit.point.x * STUD, 0, hit.point.z * STUD];
    const studs = [];
    const gx = Math.round((P[0] - 10) / STUD) * STUD + 10, gz = Math.round((P[2] - 10) / STUD) * STUD + 10;
    for (let i = -3; i <= 3; i++) for (let j = -3; j <= 3; j++) studs.push({ g: "M", pos: [gx + i * STUD, 0, gz + j * STUD], axis: [0, 1, 0], base: true });
    const snapped = sbSnapPlacement(studs, hit, "base");
    if (snapped) return snapped;
  }
  return sbGridPlacement(hit, g);
}

// toutes les façons d'accrocher la pièce sur la cible : (point d'accroche de la pièce × orientation), triées par nombre de
// liaisons obtenues (la pose la plus « emboîtée » d'abord). R fait défiler les poses, C passe au point d'accroche suivant.
function sbSnapPlacement(ws, hit, targetId) {
  const mine = (SB.snaps[SB.part] || []).filter((s) => !s.slide);
  if (!mine.length) return null;
  const P = [hit.point.x * STUD, -hit.point.y * STUD, hit.point.z * STUD];      // point visé, en LDU (repère LDraw)
  let T = null, best = 1e9;
  for (const w of ws) {
    if (!mine.some((s) => s.g !== w.g)) continue;
    const d = Math.hypot(w.pos[0] - P[0], w.pos[1] - P[1], w.pos[2] - P[2]);
    if (d < best) { best = d; T = w; }
  }
  if (!T || best > 30) return null;
  const others = ws.filter((w) => w.g === T.g && Math.abs(w.axis[0] - T.axis[0]) + Math.abs(w.axis[1] - T.axis[1]) + Math.abs(w.axis[2] - T.axis[2]) < 0.05);
  const combos = [];
  mine.forEach((c, ci) => {
    if (c.g === T.g) return;
    for (const R of SB_ROT24) {
      const a = mulRv(R, c.axis);
      if (Math.abs(a[0] - T.axis[0]) + Math.abs(a[1] - T.axis[1]) + Math.abs(a[2] - T.axis[2]) > 0.05) continue;
      const q = mulRv(R, c.pos), o = [T.pos[0] - q[0], T.pos[1] - q[1], T.pos[2] - q[2]];
      let n = 0;                                          // liaisons : points d'accroche de la pièce qui tombent sur ceux de la cible
      for (const s of mine) {
        if (s.g === T.g) continue;
        const v = mulRv(R, s.pos), w = [v[0] + o[0], v[1] + o[1], v[2] + o[2]];
        if (others.some((t) => Math.hypot(t.pos[0] - w[0], t.pos[1] - w[1], t.pos[2] - w[2]) < 1)) n++;
      }
      // départage : debout (le haut de la pièce reste en haut) d'abord ; sur la plaque de base, debout passe avant tout
      const upright = R[4] > 0.5 ? 1 : 0;
      combos.push({ n, ci, score: targetId === "base" ? upright * 100 + n : n + 0.1 * upright, m: o.map(rnd).concat(R) });
    }
  });
  if (!combos.length) return null;
  combos.sort((a, b) => b.score - a.score);
  if (targetId === "base" && combos.some((c) => c.score >= 100)) {   // sur la plaque : seulement debout, une pose par quart de tour
    const seen = new Set();
    combos.splice(0, combos.length, ...combos.filter((c) => c.score >= 100).filter((c) => { const k = c.m.slice(3).join(","); if (seen.has(k)) return false; seen.add(k); return true; }));
  }
  // C : passer au point d'accroche suivant (dans l'ordre du classement) ; R : défiler les poses
  const cis = [...new Set(combos.map((c) => c.ci))];
  const ciPick = cis[SB.ci % cis.length];
  const pool = SB.ci ? combos.filter((c) => c.ci === ciPick) : combos;
  const pick = pool[SB.rot % pool.length];
  SB.snapInfo = { target: targetId, choices: cis.length, spins: pool.length, links: pick.n };
  return pick.m;
}

function sbGridPlacement(hit, g) {
  SB.snapInfo = null;
  const rb = rotatedBox(g.info, SB.rot);
  const X = Math.max(1, Math.round((rb.x1 - rb.x0) / STUD)), Z = Math.max(1, Math.round((rb.z1 - rb.z0) / STUD));
  let px = hit.point.x * STUD, pz = hit.point.z * STUD, k = 0;
  if (!hit.object.userData.base) {                       // pièce sans point d'accroche connu : posée à côté / dessus, sur la grille
    const ob = new THREE.Box3().setFromObject(hit.object);
    const c = ob.getCenter(new THREE.Vector3());
    const p = SB.doc.parts.find((q) => q.id === hit.object.parent.userData.id);
    const gi = p && ASM.geo[p.part];
    k = gi ? Math.round(-(p.m[1] + gi.info.body_top) / PLATE) : 0;
    if (hit.point.y < ob.max.y - 0.3) { const dx = hit.point.x - c.x, dz = hit.point.z - c.z; if (Math.abs(dx) > Math.abs(dz)) px += Math.sign(dx) * 10; else pz += Math.sign(dz) * 10; }
  }
  const cx = Math.round(px / STUD - X / 2) * STUD + X * STUD / 2;
  const cz = Math.round(pz / STUD - Z / 2) * STUD + Z * STUD / 2;
  const R = sbRy(SB.rot);
  const ox = cx - (rb.x0 + rb.x1) / 2, oz = cz - (rb.z0 + rb.z1) / 2;
  const oy = -k * PLATE - rb.yBottom;
  return [ox, oy, oz].map(rnd).concat(R);
}

function sbRay(ev) {
  const r = SB.three.renderer.domElement.getBoundingClientRect();
  const ndc = new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  const ray = new THREE.Raycaster(); ray.setFromCamera(ndc, SB.three.camera);
  const targets = [SB.three.base].concat(Object.values(SB.objs).map((o) => o.children[0]));
  return ray.intersectObjects(targets, false)[0] || null;
}

async function sbUpdateGhost(ev) {
  const hit = sbRay(ev);
  const id = hit && !hit.object.userData.base ? hit.object.parent.userData.id : null;
  if (ev.shiftKey || ev.altKey || SB.mode === "select") {     // suppression / pipette / sélection : surligner la pièce visée
    if (SB.ghost) SB.ghost.visible = false;
    if (SB.hover !== id) { const prev = SB.hover; SB.hover = id; for (const pid of [prev, id]) { const p = SB.doc.parts.find((q) => q.id === pid); if (p) sbSync(p); } }
    return;
  }
  if (SB.hover) { const prev = SB.hover; SB.hover = null; const p = SB.doc.parts.find((q) => q.id === prev); if (p) sbSync(p); }
  await partGeo(SB.part);
  await sbSnapsFor([SB.part].concat(id ? [SB.doc.parts.find((q) => q.id === id).part] : []));
  if (!hit) { if (SB.ghost) SB.ghost.visible = false; SB.place = null; return; }
  const place = sbComputePlacement(hit);
  const same = SB.place && place && SB.place.every((v, i) => Math.abs(v - place[i]) < 0.01);
  SB.place = place;
  if (!same) { SB.fit = null; sbFitAsync(); }
  sbDrawGhost();
}

function sbFitAsync() {                         // le vrai moteur dit si la pièce tient et si elle en traverse une autre
  const seq = ++SB.fitSeq, place = SB.place, part = SB.part;
  if (!place) return;
  clearTimeout(SB.fitTimer);
  SB.fitTimer = setTimeout(async () => {
    try {
      const r = await api("/api/sandbox-fit", { method: "POST", body: JSON.stringify({ parts: SB.doc.parts, cand: { part, color: SB.color, m: place } }) });
      if (seq !== SB.fitSeq) return;
      SB.fit = r; sbDrawGhost();
    } catch (e) { /* le serveur répondra au clic */ }
  }, 90);
}

function sbWorldBox(part, m) {
  const g = ASM.geo[part]; if (!g) return null;
  const lo = g.info.bbox[0].slice(), hi = g.info.bbox[1].slice();
  lo[1] = Math.max(lo[1], g.info.body_top);
  const R = m.slice(3), mn = [1e9, 1e9, 1e9], mx = [-1e9, -1e9, -1e9];
  for (const x of [lo[0], hi[0]]) for (const y of [lo[1], hi[1]]) for (const z of [lo[2], hi[2]]) {
    const v = [R[0] * x + R[1] * y + R[2] * z + m[0], R[3] * x + R[4] * y + R[5] * z + m[1], R[6] * x + R[7] * y + R[8] * z + m[2]];
    for (let i = 0; i < 3; i++) { mn[i] = Math.min(mn[i], v[i]); mx[i] = Math.max(mx[i], v[i]); }
  }
  return [mn, mx];
}
function sbCollides(part, m) {           // chevauchement réel (> 1 LDU sur les 3 axes) avec une pièce posée
  const a = sbWorldBox(part, m); if (!a) return false;
  return SB.doc.parts.some((p) => {
    const b = sbWorldBox(p.part, p.m); if (!b) return false;
    return [0, 1, 2].every((i) => Math.min(a[1][i], b[1][i]) - Math.max(a[0][i], b[0][i]) > 1);
  });
}

function sbDrawGhost() {
  const g = ASM.geo[SB.part];
  if (!g || !SB.place) return;
  if (!SB.ghost || SB.ghost.userData.part !== SB.part) {
    if (SB.ghost) SB.three.root.remove(SB.ghost);
    SB.ghost = new THREE.Group();
    SB.ghost.add(new THREE.Mesh(g.mesh, new THREE.MeshStandardMaterial({ transparent: true, opacity: 0.55, depthWrite: false })),
      new THREE.LineSegments(g.edges, new THREE.LineBasicMaterial({ color: 0x00b8ff })));
    SB.ghost.matrixAutoUpdate = false; SB.ghost.userData.part = SB.part;
    SB.ghost.children[0].raycast = () => {}; SB.ghost.children[1].raycast = () => {};
    SB.three.root.add(SB.ghost);
  }
  const f = SB.fit;
  SB.blocked = !!(f && f.collisions.length);
  const loose = !!(f && !f.collisions.length && !f.ok);
  SB.ghost.children[0].material.color.set(SB.blocked ? "#ff2020" : loose ? "#ff9f1a" : colorHex(SB.color));
  SB.ghost.children[1].material.color.set(SB.blocked ? 0xff2020 : loose ? 0xff9f1a : 0x00b8ff);
  SB.ghost.matrix.copy(sbMatrix(SB.place));
  SB.ghost.visible = true;
  sbPoseInfo();
  const si = SB.snapInfo;
  $("#sbHint").textContent = !f ? "…" : SB.blocked ? "Traverse une autre pièce : impossible ici"
    : loose ? "Ne tient à rien ici" : (f.ground ? "Posée sur la plaque" : `Accrochée à ${f.links} pièce${f.links > 1 ? "s" : ""}`)
    + (si ? ` · R : ${si.spins} orientation${si.spins > 1 ? "s" : ""}` + (si.choices > 1 ? ` · C : ${si.choices} points d'accroche` : "") : " · R : tourner");
}

function sbBindPointer() {
  const el = SB.three.renderer.domElement;
  let down = null;
  el.addEventListener("pointermove", (e) => { if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) < 4) sbUpdateGhost(e); });
  el.addEventListener("pointerdown", (e) => (down = e.button === 0 ? [e.clientX, e.clientY] : null));
  el.addEventListener("pointerup", async (e) => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) { down = null; return; }
    down = null;
    const hit = sbRay(e);
    const id = hit && !hit.object.userData.base ? hit.object.parent.userData.id : null;
    if (e.shiftKey) { if (id) sbDelete(id); return; }
    if (e.altKey) { const p = SB.doc.parts.find((q) => q.id === id); if (p) { SB.part = p.part; SB.color = p.color; sbPalette(); sbColors(); } return; }
    if (SB.mode === "select") { sbSelect(id); return; }
    if (!SB.place) return;
    const place = SB.place.slice();
    const r = await api("/api/sandbox-fit", { method: "POST", body: JSON.stringify({ parts: SB.doc.parts, cand: { part: SB.part, color: SB.color, m: place } }) });
    if (r.collisions.length) { $("#sbSave").textContent = "Impossible : la pièce en traverserait une autre (vrai moteur)"; return; }
    sbSnapshot();
    const p = { id: "u" + Date.now().toString(36) + Math.floor(Math.random() * 1e4), part: SB.part, color: SB.color, m: place, src: "manuel", status: "ok" };
    SB.doc.parts.push(p);
    await sbSync(p); sbChanged(); hbUse(p.part, p.color);
    if (!r.ok) $("#sbSave").textContent = "Posée, mais elle ne tient à rien pour l'instant";
    SB.fit = null; sbFitAsync();
  });
  // clic droit sans glisser sur une pièce : la sélectionner (clic droit glissé : déplacer la vue)
  let rdown = null;
  el.addEventListener("pointerdown", (e) => { if (e.button === 2) rdown = [e.clientX, e.clientY]; });
  el.addEventListener("pointerup", (e) => {
    if (e.button !== 2 || !rdown) return;
    const moved = Math.hypot(e.clientX - rdown[0], e.clientY - rdown[1]) > 4; rdown = null;
    if (moved) return;
    const hit = sbRay(e);
    const id = hit && !hit.object.userData.base ? hit.object.parent.userData.id : null;
    if (!id) { if (SB.mode === "select") sbSetMode("place"); return; }
    if (SB.mode !== "select") sbSetMode("select");
    sbSelect(id);
  });
  el.addEventListener("pointerleave", () => { if (SB.ghost) SB.ghost.visible = false; });
  el.addEventListener("contextmenu", (e) => e.preventDefault());
}

// ------------------------------------------------------------------ édition et sauvegarde

function sbSnapshot() { SB.undo.push(JSON.stringify(SB.doc.parts)); if (SB.undo.length > 200) SB.undo.shift(); SB.redo = []; }
async function sbDelete(id) {
  sbSnapshot();
  SB.doc.parts = SB.doc.parts.filter((p) => p.id !== id);
  if (SB.objs[id]) { SB.three.root.remove(SB.objs[id]); delete SB.objs[id]; }
  SB.hover = null; sbChanged();
}
async function sbUndo() { const prev = SB.undo.pop(); if (!prev) return; SB.redo.push(JSON.stringify(SB.doc.parts)); SB.doc.parts = JSON.parse(prev); await sbSyncAll(); sbChanged(); }
async function sbRedo() { const nxt = SB.redo.pop(); if (!nxt) return; SB.undo.push(JSON.stringify(SB.doc.parts)); SB.doc.parts = JSON.parse(nxt); await sbSyncAll(); sbChanged(); }

// ------------------------------------------------------------------ sélection : déplacer, tourner, recolorer, changer de pièce

function sbSetMode(mode) {
  SB.mode = mode;
  if (mode === "place") sbSelect(null);
  if (SB.ghost) SB.ghost.visible = false;
  $("#sbMode").textContent = mode === "select" ? "Mode : sélection (S)" : "Mode : poser (S)";
  $("#sbMode").setAttribute("aria-pressed", String(mode === "select"));
  $("#sbHint").textContent = mode === "select" ? "Clic : choisir une pièce · les boutons au-dessus d'elle la tournent et la déplacent · une couleur ou une pièce de la palette la remplace" : "";
  sbPoseInfo();
}
async function sbSelect(id) {
  const prev = SB.sel; SB.sel = id;
  for (const pid of [prev, id]) { const p = SB.doc.parts.find((q) => q.id === pid); if (p) await sbSync(p); }
  if (id) sbSelStatus();
}
async function sbSelStatus() {
  const p = SB.doc.parts.find((q) => q.id === SB.sel); if (!p) return;
  const r = await api("/api/sandbox-fit", { method: "POST", body: JSON.stringify({ parts: SB.doc.parts.filter((q) => q.id !== p.id), cand: p }) });
  const cat = S.catalog.parts.find((c) => c.part === p.part);
  $("#sbSave").textContent = `${p.part}${cat ? " · " + cat.name : ""} — ` + (r.collisions.length ? `traverse ${r.collisions.length} pièce(s)` : r.ok ? (r.ground ? "posée sur la plaque" : `accrochée à ${r.links} pièce(s)`) : "ne tient à rien");
}
async function sbEditSel(fn) {
  const p = SB.doc.parts.find((q) => q.id === SB.sel); if (!p) return;
  sbSnapshot(); fn(p); await sbSync(p); sbChanged(); sbSelStatus();
}
function sbRotateAround(p, Q) {        // tourner la pièce autour de son centre (pas de son origine LDraw), puis recaler au ½ tenon
  const o = SB.objs[p.id];
  const bb = o ? new THREE.Box3().setFromObject(o) : null;
  const c = bb ? [(bb.min.x + bb.max.x) / 2 * STUD, -(bb.min.y + bb.max.y) / 2 * STUD, (bb.min.z + bb.max.z) / 2 * STUD] : p.m.slice(0, 3);
  const d = mulRv(Q, [p.m[0] - c[0], p.m[1] - c[1], p.m[2] - c[2]]);
  const snap = (v, q) => Math.round(v / q) * q;
  p.m = [rnd(snap(c[0] + d[0], 10)), rnd(snap(c[1] + d[1], 4)), rnd(snap(c[2] + d[2], 10))].concat(mulRR(Q, p.m.slice(3)));
}
function sbCamAxis(dir) {          // flèches relatives à la caméra : avant/arrière/gauche/droite → axe x ou z du monde
  const cam = SB.three.camera, t = SB.three.controls.target;
  const f = new THREE.Vector3(t.x - cam.position.x, 0, t.z - cam.position.z).normalize();
  const r = new THREE.Vector3(-f.z, 0, f.x);
  const v = { up: f, down: f.clone().negate(), right: r, left: r.clone().negate() }[dir];
  return Math.abs(v.x) > Math.abs(v.z) ? [Math.sign(v.x), 0] : [0, Math.sign(v.z)];
}
const SB_Q = {                      // quarts de tour autour des axes du monde (LDraw : y vers le bas)
  y: [0, 0, 1, 0, 1, 0, -1, 0, 0], x: [1, 0, 0, 0, 0, -1, 0, 1, 0], z: [0, -1, 0, 1, 0, 0, 0, 0, 1],
};
function sbSelKey(e) {
  const k = e.key;
  const step = e.shiftKey ? 10 : STUD;
  if (k.startsWith("Arrow")) {
    const [dx, dz] = sbCamAxis(k.slice(5).toLowerCase());
    sbEditSel((p) => { p.m[0] = rnd(p.m[0] + dx * step); p.m[2] = rnd(p.m[2] + dz * step); }); return true;
  }
  if (k === "PageUp" || k === "PageDown") { sbEditSel((p) => { p.m[1] = rnd(p.m[1] + (k === "PageUp" ? -PLATE : PLATE)); }); return true; }
  const ax = { r: "y", t: "x", y: "z" }[k.toLowerCase()];
  if (ax) { sbEditSel((p) => sbRotateAround(p, e.shiftKey ? mulRR(SB_Q[ax], mulRR(SB_Q[ax], SB_Q[ax])) : SB_Q[ax])); return true; }
  if (k === "Delete" || k === "Backspace") { const id = SB.sel; SB.sel = null; sbDelete(id); return true; }
  if (k === "Escape") { sbSetMode("place"); return true; }
  if (k.toLowerCase() === "d") { sbDuplicate(); return true; }
  return false;
}

// ------------------------------------------------------------------ rotation et déplacement à la souris

function sbTurn(d) {                                 // pose suivante / précédente (R / Maj+R, Maj + molette)
  if (SB.mode === "select" && SB.sel) { sbEditSel((p) => sbRotateAround(p, d > 0 ? SB_Q.y : mulRR(SB_Q.y, mulRR(SB_Q.y, SB_Q.y)))); return; }
  SB.rot = (SB.rot + (d > 0 ? 1 : 23)) % 24; sbDrawGhostAt();
}
function sbNextSnap() { SB.ci++; SB.rot = 0; sbDrawGhostAt(); }
function sbPoseUI() {
  const box = $("#sb3d");
  const pose = h("div", { class: "sb-pose", id: "sbPose" },
    h("button", { class: "sb-ic", title: "Orientation précédente (Maj+R, Maj + molette)", onclick: () => sbTurn(-1) }, "↺"),
    h("span", { id: "sbPoseN" }, ""),
    h("button", { class: "sb-ic", title: "Orientation suivante (R, Maj + molette)", onclick: () => sbTurn(1) }, "↻"),
    h("button", { class: "sb-txt", id: "sbPoseC", title: "S'accrocher par un autre point de la pièce (C)", onclick: sbNextSnap }, "Autre accroche"));
  const mv = (fn) => (e) => { e.stopPropagation(); fn(); };
  const key = (k, shift) => mv(() => sbSelKey({ key: k, shiftKey: !!shift }));
  const ctx = h("div", { class: "sb-ctx", id: "sbCtx", hidden: true },
    h("div", { class: "sb-ctx-row" },
      h("button", { class: "sb-ic", title: "Tourner à gauche (Maj+R)", onclick: key("r", true) }, "↺"),
      h("button", { class: "sb-ic", title: "Tourner à droite (R)", onclick: key("r") }, "↻"),
      h("button", { class: "sb-ic", title: "Basculer vers l'avant (T)", onclick: key("t") }, "⤵"),
      h("button", { class: "sb-ic", title: "Basculer sur le côté (Y)", onclick: key("y") }, "⤷"),
      h("span", { class: "sb-sep" }),
      h("button", { class: "sb-ic", title: "Dupliquer à côté (D)", onclick: mv(sbDuplicate) }, "⧉"),
      h("button", { class: "sb-ic danger", title: "Supprimer (Suppr)", onclick: key("Delete") }, "🗑"),
      h("button", { class: "sb-ic", title: "Désélectionner (Échap)", onclick: mv(() => sbSetMode("place")) }, "✕")),
    h("div", { class: "sb-ctx-row" },
      h("button", { class: "sb-ic", title: "Gauche (flèche, Maj : ½ tenon)", onclick: key("ArrowLeft") }, "←"),
      h("button", { class: "sb-ic", title: "Vers l'avant (flèche)", onclick: key("ArrowUp") }, "↑"),
      h("button", { class: "sb-ic", title: "Vers l'arrière (flèche)", onclick: key("ArrowDown") }, "↓"),
      h("button", { class: "sb-ic", title: "Droite (flèche)", onclick: key("ArrowRight") }, "→"),
      h("span", { class: "sb-sep" }),
      h("button", { class: "sb-ic", title: "Monter d'une plate (Page ↑)", onclick: key("PageUp") }, "⤒"),
      h("button", { class: "sb-ic", title: "Descendre d'une plate (Page ↓)", onclick: key("PageDown") }, "⤓")));
  for (const el of [pose, ctx]) { el.addEventListener("pointerdown", (e) => e.stopPropagation()); el.addEventListener("pointerup", (e) => e.stopPropagation()); }
  const full = h("button", { class: "sb-ic sb-full", id: "sbFullIc", title: "Plein écran (F)", onclick: (e) => { e.stopPropagation(); sbFullscreen(); } }, "⛶");
  full.addEventListener("pointerdown", (e) => e.stopPropagation()); full.addEventListener("pointerup", (e) => e.stopPropagation());
  box.append(pose, ctx, full);
  // Maj + molette : tourner la pièce (sans zoomer)
  box.addEventListener("wheel", (e) => { if (!e.shiftKey) return; e.preventDefault(); e.stopPropagation(); sbTurn(e.deltaY > 0 ? 1 : -1); }, { capture: true, passive: false });
}
function sbPoseInfo() {
  const n = $("#sbPoseN"); if (!n) return;
  const si = SB.snapInfo;
  $("#sbPose").hidden = SB.mode !== "place";
  n.textContent = si ? `orientation ${(SB.rot % si.spins) + 1} / ${si.spins}` : "orientation";
  $("#sbPoseC").hidden = !(si && si.choices > 1);
}
function sbCtxUpdate() {
  const ctx = document.getElementById("sbCtx"); if (!ctx) return;
  const o = SB.mode === "select" && SB.sel && SB.objs[SB.sel];
  if (!o) { ctx.hidden = true; return; }
  const bb = new THREE.Box3().setFromObject(o);
  const top = new THREE.Vector3((bb.min.x + bb.max.x) / 2, bb.max.y, (bb.min.z + bb.max.z) / 2).project(SB.three.camera);
  const r = SB.three.renderer.domElement;
  const x = (top.x + 1) / 2 * r.clientWidth, y = (1 - top.y) / 2 * r.clientHeight;
  ctx.hidden = false;
  ctx.style.left = Math.max(8, Math.min(r.clientWidth - ctx.offsetWidth - 8, x - ctx.offsetWidth / 2)) + "px";
  ctx.style.top = Math.max(8, y - ctx.offsetHeight - 14) + "px";
}
async function sbDuplicate() {                       // copie de la pièce sélectionnée, posée à côté (là où elle tient)
  const p = SB.doc.parts.find((q) => q.id === SB.sel); if (!p) return;
  const [dx, dz] = sbCamAxis("right");
  for (const k of [1, 2, 3, -1, -2]) {
    const m = p.m.slice(); m[0] = rnd(m[0] + dx * STUD * k * 2); m[2] = rnd(m[2] + dz * STUD * k * 2);
    const r = await api("/api/sandbox-fit", { method: "POST", body: JSON.stringify({ parts: SB.doc.parts, cand: { part: p.part, color: p.color, m } }) });
    if (!r.collisions.length) {
      sbSnapshot();
      const q = { id: "u" + Date.now().toString(36) + Math.floor(Math.random() * 1e4), part: p.part, color: p.color, m, src: "manuel", status: "ok" };
      SB.doc.parts.push(q); await sbSync(q); sbChanged(); sbSelect(q.id); return;
    }
  }
  $("#sbSave").textContent = "Pas de place libre à côté pour la copie";
}

// ------------------------------------------------------------------ barre « Mes pièces » (pièce × couleur), touches 1 à 0

const HB_MAX = 10;
SB.hotbar = (() => { try { return JSON.parse(localStorage.getItem("bf.hotbar") || "[]"); } catch (e) { return []; } })();
function hbSave() { localStorage.setItem("bf.hotbar", JSON.stringify(SB.hotbar)); }
function hbKey(e) { return e.part + ":" + e.color; }
function hbUse(part, color) {                       // une pièce posée entre dans la barre (sans chasser les épinglées)
  const k = part + ":" + color;
  if (SB.hotbar.some((e) => hbKey(e) === k)) return hbRender();
  const pinned = SB.hotbar.filter((e) => e.pin), free = SB.hotbar.filter((e) => !e.pin);
  free.unshift({ part, color });
  SB.hotbar = pinned.concat(free).slice(0, Math.max(HB_MAX, pinned.length));
  hbSave(); hbRender();
}
function hbPick(i) {
  const e = SB.hotbar[i]; if (!e) return;
  if (SB.mode === "select" && SB.sel) { sbEditSel((p) => { p.part = e.part; p.color = e.color; }); return; }
  SB.part = e.part; SB.color = e.color; sbPalette(); sbColors(); hbRender();
  partGeo(e.part).then(() => sbDrawGhostAt());
}
function hbFromCreation() {                         // les pièces les plus utilisées de la création en cours
  const cnt = {};
  for (const p of SB.doc.parts) { const k = p.part + ":" + p.color; cnt[k] = (cnt[k] || 0) + 1; }
  const top = Object.entries(cnt).sort((a, b) => b[1] - a[1]).map(([k]) => { const [part, color] = k.split(":"); return { part, color: +color }; });
  const pinned = SB.hotbar.filter((e) => e.pin);
  SB.hotbar = pinned.concat(top.filter((t) => !pinned.some((e) => hbKey(e) === hbKey(t)))).slice(0, Math.max(HB_MAX, pinned.length));
  hbSave(); hbRender();
}
function hbRender() {
  const bar = $("#sbHotbar"); if (!bar) return;
  const cnt = {};
  for (const p of (SB.doc ? SB.doc.parts : [])) { const k = p.part + ":" + p.color; cnt[k] = (cnt[k] || 0) + 1; }
  const slots = SB.hotbar.slice(0, HB_MAX).map((e, i) => {
    const img = h("img", { alt: "", width: 46, height: 46 });
    thumb(e.part, e.color).then((u) => (img.src = u)).catch(() => {});
    const cat = S.catalog.parts.find((c) => c.part === e.part);
    const col = (S.catalog.colors.find((c) => c.code === e.color) || {}).name || e.color;
    const on = e.part === SB.part && e.color === SB.color;
    const b = h("button", { class: "hb-slot" + (on ? " on" : "") + (e.pin ? " pin" : ""), title: `${i < 9 ? i + 1 : 0} · ${e.part}${cat ? " " + cat.name : ""} · ${col}\nClic : prendre · clic droit : ${e.pin ? "désépingler" : "épingler"} · Maj+clic : retirer`,
      onclick: (ev) => { if (ev.shiftKey) { SB.hotbar.splice(i, 1); hbSave(); hbRender(); } else hbPick(i); } },
      h("span", { class: "hb-n" }, String(i < 9 ? i + 1 : 0)), img, cnt[hbKey(e)] ? h("span", { class: "hb-c" }, "×" + cnt[hbKey(e)]) : null);
    b.addEventListener("contextmenu", (ev) => { ev.preventDefault(); e.pin = !e.pin; hbSave(); hbRender(); });
    return b;
  });
  for (let i = slots.length; i < HB_MAX; i++) slots.push(h("span", { class: "hb-slot empty" }, h("span", { class: "hb-n" }, String(i < 9 ? i + 1 : 0))));
  bar.replaceChildren(...slots, h("button", { class: "hb-tool", title: "Remplir avec les pièces les plus utilisées de cette création", onclick: hbFromCreation }, "↺ de la création"),
    h("button", { class: "hb-tool", title: "Épingler la pièce et la couleur en cours", onclick: () => { hbUse(SB.part, SB.color); const e = SB.hotbar.find((x) => x.part === SB.part && x.color === SB.color); if (e) e.pin = true; hbSave(); hbRender(); } }, "📌 épingler"));
}

// ------------------------------------------------------------------ plein écran

function sbFullscreen() {
  const el = $(".sb");
  if (document.fullscreenElement) { document.exitFullscreen(); return; }
  if (el.classList.contains("sb-max")) { sbMax(false); return; }
  // vrai plein écran ; si le navigateur le refuse, la vue couvre toute la fenêtre (même effet, sans le mode plein écran du système)
  (el.requestFullscreen ? el.requestFullscreen() : Promise.reject(new Error("indisponible"))).catch(() => sbMax(true));
}
function sbMax(on) {
  $(".sb").classList.toggle("sb-max", on);
  $("#sbFull").textContent = on ? "Quitter le plein écran (F)" : "Plein écran (F)";
  $("#sbFullIc").textContent = on ? "✕" : "⛶";
  $("#sbFullIc").title = on ? "Quitter le plein écran (F ou Échap)" : "Plein écran (F)";
}
function sbToggleSide() { $(".sb").classList.toggle("no-side"); }

// ------------------------------------------------------------------ importer

async function sbImportDialog() {
  const src = await api("/api/sandbox-sources");
  const dlg = h("dialog", { class: "sb-import" });
  const status = h("p", { class: "muted" }, "");
  const go = async (body) => {
    status.textContent = "Import…";
    try {
      const r = await api("/api/sandbox-import", { method: "POST", body: JSON.stringify(body) });
      const list = await api("/api/sandbox");
      let name = r.name, i = 2; while (list.some((c) => c.name === name)) name = `${r.name}-${i++}`;
      await api(`/api/sandbox/${name}`, { method: "PUT", body: JSON.stringify({ parts: r.parts, imported: body.source }) });
      dlg.close(); dlg.remove(); await sbLoad(name);
      $("#sbSave").textContent = `Importé : ${r.parts.length} pièces — « Vérifier » pour contrôler avec le moteur`;
    } catch (e) { status.textContent = "Échec : " + e.message; }
  };
  const file = h("input", { type: "file", accept: ".ldr,.mpd,.dat,.txt" });
  file.addEventListener("change", async () => { const f = file.files[0]; if (f) go({ source: "ldr", text: await f.text(), name: f.name.replace(/\.[^.]+$/, "") }); });
  const off = h("select", {}, h("option", { value: "" }, "— choisir —"), ...src.official.map((o) => h("option", { value: o.id }, o.label)));
  off.addEventListener("change", () => off.value && go({ source: "official", id: off.value }));
  const mod = h("select", {}, h("option", { value: "" }, "— choisir —"), ...src.models.map((o) => h("option", { value: o.id }, o.label)));
  mod.addEventListener("change", () => mod.value && go({ source: "model", id: mod.value }));
  dlg.append(h("h3", {}, "Importer dans une nouvelle création"),
    h("label", { class: "field" }, h("span", {}, "Fichier LDraw (.ldr, .mpd — Studio, LDCad, BrickLink)"), file),
    h("label", { class: "field" }, h("span", {}, "BrickHeadz officielle (101)"), off),
    h("label", { class: "field" }, h("span", {}, "Modèle du cahier de recherche"), mod),
    status, h("button", { class: "btn small", onclick: () => { dlg.close(); dlg.remove(); } }, "Fermer"));
  (document.fullscreenElement || document.body).append(dlg); dlg.showModal();
}
function sbChanged() {
  $("#sbSave").textContent = "Modifié…";
  SB.floating.clear();
  clearTimeout(SB.saveTimer);
  SB.saveTimer = setTimeout(async () => {
    try { await api(`/api/sandbox/${SB.name}`, { method: "PUT", body: JSON.stringify(SB.doc) }); $("#sbSave").textContent = "Enregistré"; }
    catch (e) { $("#sbSave").textContent = "Échec : " + e.message; }
  }, 500);
  sbStats();
}
function sbStats() {
  const n = SB.doc ? SB.doc.parts.length : 0;
  const refs = new Set((SB.doc ? SB.doc.parts : []).map((p) => p.part + ":" + p.color)).size;
  $("#sbStats").textContent = `${n} pièce${n > 1 ? "s" : ""} · ${refs} référence${refs > 1 ? "s" : ""} (pièce × couleur)`;
}
async function sbCheck() {
  const r = await api(`/api/sandbox/${SB.name}/check`, { method: "POST", body: JSON.stringify(SB.doc) });
  SB.floating = new Set(r.floating.concat(r.overlap || []));
  await sbSyncAll();
  const msg = [];
  if (r.floating.length) msg.push(`${r.floating.length} pièce(s) ne tiennent à rien`);
  if ((r.overlap || []).length) msg.push(`${r.overlap.length} pièce(s) en chevauchent une autre`);
  $("#sbSave").textContent = msg.length ? msg.join(" · ") + " (en rouge) — moteur réel : points d'accroche et matière" : "Tout est bon (moteur réel) : rien ne vole, aucune pièce n'en traverse une autre";
}

// ------------------------------------------------------------------ palette

const SB_KINDS = ["", "brick", "plate", "tile", "slope", "curved", "round", "wedge", "snot", "other"];
function sbPalette() {
  $("#sbKinds").replaceChildren(...SB_KINDS.map((k) => h("button", { class: "chip", "aria-pressed": String(SB.kind === k), onclick: () => { SB.kind = k; sbPalette(); } }, k ? KIND_FR[k] : "toutes")));
  const q = SB.search.toLowerCase();
  const list = S.catalog.parts.filter((c) => (!SB.kind || c.kind === SB.kind) && (!q || (c.part + " " + c.name).toLowerCase().includes(q)));
  $("#sbParts").replaceChildren(...list.map((c) => {
    const img = h("img", { alt: "", width: 64, height: 64 });
    thumb(c.part, SB.color).then((u) => (img.src = u)).catch(() => {});
    return h("button", { class: "sbpart", "aria-pressed": String(c.part === SB.part), title: `${c.part} — ${c.name}`,
      onclick: () => {
        if (SB.mode === "select" && SB.sel) { sbEditSel((p) => { p.part = c.part; }); return; }
        SB.part = c.part; sbPalette(); partGeo(c.part).then(() => sbDrawGhost()); } }, img, h("small", {}, c.name.replace(/^~?Moved to.*/, c.part)));
  }));
  const cur = S.catalog.parts.find((c) => c.part === SB.part);
  $("#sbCurrent").textContent = cur ? `${cur.part} · ${cur.name}` : SB.part;
  hbRender();
}
function sbColors() {
  $("#sbColors").replaceChildren(...S.catalog.colors.map((c) =>
    h("button", { class: "swatch", style: `background:${c.hex}`, title: c.name, "aria-pressed": String(c.code === SB.color),
      onclick: () => {
        if (SB.mode === "select" && SB.sel) { sbEditSel((p) => { p.color = c.code; }); return; }
        SB.color = c.code; sbColors(); sbPalette(); sbDrawGhost(); } })));
}

// ------------------------------------------------------------------ créations

async function sbLoad(name) {
  SB.name = name; localStorage.setItem("bf.sandbox", name);
  SB.doc = await api(`/api/sandbox/${name}`);
  SB.doc.parts = SB.doc.parts || [];
  SB.undo = []; SB.redo = []; SB.sel = null; SB.floating.clear();
  sbSnapsFor(SB.doc.parts.map((p) => p.part));
  for (const o of Object.values(SB.objs)) SB.three.root.remove(o);
  SB.objs = {};
  await sbSyncAll();
  sbFrame();
  await sbList();
}
function sbFrame() {                 // cadrer la caméra sur la création (vue 3/4 avant)
  const ps = SB.doc.parts;
  if (!ps.length) { SB.three.camera.position.set(18, 16, 22); SB.three.controls.target.set(0, 1, 0); SB.three.controls.update(); return; }
  const xs = ps.map((p) => p.m[0] / STUD), ys = ps.map((p) => -p.m[1] / STUD), zs = ps.map((p) => p.m[2] / STUD);
  const c = [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2, (Math.min(...zs) + Math.max(...zs)) / 2];
  const r = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), Math.max(...zs) - Math.min(...zs), 4);
  SB.three.controls.target.set(c[0], c[1], c[2]);
  SB.three.camera.position.set(c[0] + r * 0.9, c[1] + r * 0.7, c[2] - r * 1.6);
  SB.three.controls.update();
}

async function sbList() {
  const list = await api("/api/sandbox");
  if (SB.name && !list.some((c) => c.name === SB.name)) list.unshift({ name: SB.name, parts: SB.doc.parts.length });
  $("#sbSelect").replaceChildren(...list.map((c) => h("option", { value: c.name, selected: c.name === SB.name }, `${c.name} (${c.parts})`)));
}
async function sbNew() {
  const base = "creation";
  const list = await api("/api/sandbox");
  let i = 1; while (list.some((c) => c.name === `${base}-${i}`)) i++;
  await api(`/api/sandbox/${base}-${i}`, { method: "PUT", body: JSON.stringify({ parts: [] }) });
  await sbLoad(`${base}-${i}`);
}
async function sbRename() {
  const input = $("#sbNewName");
  const to = input.value.trim().replace(/\s+/g, "-");
  if (!to) return;
  try { await api(`/api/sandbox/${SB.name}/rename`, { method: "POST", body: JSON.stringify({ to }) }); input.value = ""; await sbLoad(to); }
  catch (e) { $("#sbSave").textContent = e.message; }
}

// ------------------------------------------------------------------ page

async function pageSandbox() {
  S.tab = "sandbox";
  $("#pageHead").replaceChildren(h("div", { class: "ph-meta" }, h("span", {}, "Atelier")), h("h1", {}, "Bac à sable"),
    h("p", { class: "lede" }, "Construis toi-même, pièce par pièce. Clic : poser (la pièce s'aimante sur le tenon ou le creux visé, même sur le côté) · pour tourner : ↺ ↻ dans la vue ou Maj + molette · clic droit sur une pièce : la sélectionner (boutons au-dessus d'elle pour la tourner, la déplacer, la copier) · Maj+clic : supprimer · Alt+clic : pipette · 1 à 0 : pièces de la barre · F : plein écran · P : replier la palette · Ctrl+Z / Ctrl+Y : annuler / rétablir · clic droit glissé : déplacer la vue."));
  showPanels(["page-sandbox"]);
  if (!SB.three) {
    sbScene();
    sbPoseUI();
    $("#sbSearch").addEventListener("input", (e) => { SB.search = e.target.value; sbPalette(); });
    $("#sbSelect").addEventListener("change", (e) => sbLoad(e.target.value));
    $("#sbNewBtn").addEventListener("click", sbNew);
    $("#sbRenameBtn").addEventListener("click", sbRename);
    $("#sbUndo").addEventListener("click", sbUndo);
    $("#sbCheck").addEventListener("click", sbCheck);
    $("#sbExport").addEventListener("click", () => { location.href = `/api/sandbox-ldr/${SB.name}`; });
    $("#sbRotate").addEventListener("click", () => { SB.rot = (SB.rot + 1) % 24; sbDrawGhostAt(); });
    $("#sbRedo").addEventListener("click", sbRedo);
    $("#sbMode").addEventListener("click", () => sbSetMode(SB.mode === "select" ? "place" : "select"));
    $("#sbImport").addEventListener("click", sbImportDialog);
    $("#sbFull").addEventListener("click", sbFullscreen);
    $("#sbSide").addEventListener("click", sbToggleSide);
    document.addEventListener("fullscreenchange", () => {
      const on = !!document.fullscreenElement;
      $("#sbFull").textContent = on ? "Quitter le plein écran (F)" : "Plein écran (F)";
      $("#sbFullIc").textContent = on ? "✕" : "⛶"; $("#sbFullIc").title = on ? "Quitter le plein écran (F ou Échap)" : "Plein écran (F)";
    });
    window.addEventListener("keydown", (e) => {
      if (S.tab !== "sandbox" || ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { (e.shiftKey ? sbRedo : sbUndo)(); e.preventDefault(); return; }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") { sbRedo(); e.preventDefault(); return; }
      if (e.ctrlKey || e.metaKey) return;
      if (e.key.toLowerCase() === "s") { sbSetMode(SB.mode === "select" ? "place" : "select"); e.preventDefault(); return; }
      if (e.key.toLowerCase() === "f") { sbFullscreen(); e.preventDefault(); return; }
      if (e.key === "Escape" && $(".sb").classList.contains("sb-max") && !(SB.mode === "select" && SB.sel)) { sbMax(false); e.preventDefault(); return; }
      if (e.key.toLowerCase() === "p") { sbToggleSide(); e.preventDefault(); return; }
      if (/^[0-9]$/.test(e.key)) { hbPick(e.key === "0" ? 9 : +e.key - 1); e.preventDefault(); return; }
      if (SB.mode === "select") { if (SB.sel && sbSelKey(e)) e.preventDefault(); return; }
      if (e.key.toLowerCase() === "r") { SB.rot = (SB.rot + (e.shiftKey ? 23 : 1)) % 24; sbDrawGhostAt(); }
      else if (e.key.toLowerCase() === "c") { SB.ci++; sbDrawGhostAt(); }
      else if (e.key === "Escape") { if (SB.ghost) SB.ghost.visible = false; }
    });
    const list = await api("/api/sandbox");
    const saved = localStorage.getItem("bf.sandbox");
    await (list.some((c) => c.name === saved) ? sbLoad(saved) : list.length ? sbLoad(list[0].name) : sbNew());
  }
  sbPalette(); sbColors(); sbStats(); hbRender();
}
let sbLastEvent = null;
document.addEventListener("pointermove", (e) => (sbLastEvent = e));
function sbDrawGhostAt() { if (sbLastEvent && SB.three) sbUpdateGhost(sbLastEvent); }
