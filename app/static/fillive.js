// Brick Forge Lab — l'optimiseur de remplissage en direct (note 12) :
// la cible (cases de surface, en transparence), les pièces posées une à une, la couche en cours, les silhouettes.
"use strict";

const FLV = (() => {
  const geo = {};
  let three = null, job = null, queue = [], playing = true, speed = 12, acc = 0, last = null, ui = null, hud = null;

  const f32 = (b64) => { const bin = atob(b64), buf = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i); return new Float32Array(buf.buffer); };

  async function loadGeo(parts) {
    const need = [...new Set(parts)].filter((p) => !(p in geo));
    if (!need.length) return;
    const r = await api("/api/parts-batch", { method: "POST", body: JSON.stringify(need) });
    for (const p of need) geo[p] = r[p] ? { tris: f32(r[p].tris), edges: f32(r[p].edges) } : null;
  }

  function pieceMesh(part, m, mat) {
    const g = geo[part]; if (!g) return null;
    const [x, y, z, a, b, c, d, e, f, gg, hh, i] = m;
    const tr = (src) => { const o = new Float32Array(src.length); for (let k = 0; k < src.length; k += 3) { const vx = src[k], vy = src[k + 1], vz = src[k + 2]; o[k] = a * vx + b * vy + c * vz + x; o[k + 1] = d * vx + e * vy + f * vz + y; o[k + 2] = gg * vx + hh * vy + i * vz + z; } return o; };
    const grp = new THREE.Group();
    const bg = new THREE.BufferGeometry(); bg.setAttribute("position", new THREE.BufferAttribute(tr(g.tris), 3)); bg.computeVertexNormals();
    const mesh = new THREE.Mesh(bg, mat); grp.add(mesh);
    const eg = new THREE.BufferGeometry(); eg.setAttribute("position", new THREE.BufferAttribute(tr(g.edges), 3));
    grp.add(new THREE.LineSegments(eg, three.edge));
    grp.userData.mesh = mesh;
    return grp;
  }

  function setup(stage) {
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    stage.prepend(renderer.domElement);
    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xffffff, 0x7d756a, 0.9));
    const d1 = new THREE.DirectionalLight(0xffffff, 0.6); d1.position.set(15, 30, -20); scene.add(d1);
    const d2 = new THREE.DirectionalLight(0xffffff, 0.3); d2.position.set(-20, 10, 25); scene.add(d2);
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 2000);
    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    const root = new THREE.Group(); root.scale.set(1 / 20, -1 / 20, 1 / 20); scene.add(root);
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ color: 0xc8501e, transparent: true, opacity: 0.12, side: THREE.DoubleSide, depthWrite: false }));
    plane.rotation.x = Math.PI / 2; plane.visible = false; scene.add(plane);
    three = { renderer, scene, camera, controls, root, plane, stage,
      mat: new THREE.MeshStandardMaterial({ color: 0xb4b8bd, roughness: 0.45, metalness: 0, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }),
      hot: new THREE.MeshStandardMaterial({ color: 0xc8501e, emissive: 0xc8501e, emissiveIntensity: 0.35, roughness: 0.45, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }),
      edge: new THREE.LineBasicMaterial({ color: 0x1b1b1b, transparent: true, opacity: 0.3 }),
      pieces: [], target: null };
    let prev = performance.now();
    const loop = (now) => {
      if (!renderer.domElement.isConnected) { three = null; job = null; renderer.dispose(); return; }
      const dt = Math.min(0.2, (now - prev) / 1000); prev = now;
      const w = stage.clientWidth, hh = stage.clientHeight;
      if (w && hh && (Math.abs(renderer.domElement.width / renderer.getPixelRatio() - w) > 1 || Math.abs(renderer.domElement.height / renderer.getPixelRatio() - hh) > 1)) {
        renderer.setSize(w, hh, false); camera.aspect = w / hh; camera.updateProjectionMatrix();
      }
      if (playing) { acc += dt * speed; while (acc >= 1 && queue.length) { acc -= 1; step(); } if (!queue.length) acc = 0; }
      controls.update(); renderer.render(scene, camera);
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  function frame(cells, cx, cy, c0) {
    let lo = [1e9, 1e9, 1e9], hi = [-1e9, -1e9, -1e9];
    for (const [i, j, k] of cells) { const p = [(i - c0 + 0.5) * cx, (j + 0.5) * cy, (k - c0 + 0.5) * cx]; for (let a = 0; a < 3; a++) { lo[a] = Math.min(lo[a], p[a]); hi[a] = Math.max(hi[a], p[a]); } }
    const c = new THREE.Vector3((lo[0] + hi[0]) / 40, (lo[1] + hi[1]) / 40, (lo[2] + hi[2]) / 40);
    const dist = Math.max(hi[1] - lo[1], hi[0] - lo[0]) / 20 * 2.4;
    three.controls.target.copy(c);
    three.camera.position.set(c.x - dist * 0.55, c.y + dist * 0.3, c.z - dist * 0.8);
    three.camera.near = dist / 50; three.camera.far = dist * 30; three.camera.updateProjectionMatrix();
    three.plane.scale.set((hi[0] - lo[0]) / 20 + 3, (hi[2] - lo[2]) / 20 + 3, 1);
    three.plane.position.set(c.x, 0, c.z);
  }

  function showTarget(t) {
    if (three.target) { three.root.remove(three.target); three.target.geometry.dispose(); }
    const box = new THREE.BoxGeometry(t.cx * 0.92, t.cy * 0.92, t.cx * 0.92);
    const mat = new THREE.MeshBasicMaterial({ color: 0x3a7bd5, transparent: true, opacity: 0.09, depthWrite: false });
    const inst = new THREE.InstancedMesh(box, mat, t.cells.length);
    const M = new THREE.Matrix4();
    t.cells.forEach(([i, j, k], n) => { M.makeTranslation((i - t.c0 + 0.5) * t.cx, -(j + 0.5) * t.cy, (k - t.c0 + 0.5) * t.cx); inst.setMatrixAt(n, M); });
    three.target = inst; three.root.add(inst);
    frame(t.cells, t.cx, t.cy, t.c0);
  }

  function clearPieces() {
    for (const p of three.pieces) { three.root.remove(p); p.traverse((o) => o.geometry && o.geometry.dispose()); }
    three.pieces = []; last = null;
  }

  function step() {
    const e = queue.shift();
    if (e.t === "place") {
      if (last) last.userData.mesh.material = three.mat;
      const g = pieceMesh(e.part, e.m, three.hot);
      if (g) { three.root.add(g); three.pieces.push(g); last = g; }
      hud.piece.textContent = `${e.part} · gain ${e.gain}`;
      hud.count.textContent = three.pieces.length;
      three.plane.visible = true; three.plane.position.y = (e.level * 4) / 20 + 0.01;
      hud.where.textContent = e.side ? `pose latérale (tour ${e.pass - 9})` : `passe ${e.pass + 1} · plate ${e.level / 2 + 1}`;
    } else if (e.t === "level") {
      three.plane.position.y = (e.level * 4) / 20 + 0.01; three.plane.visible = true;
      hud.where.textContent = `passe ${e.pass + 1} · plate ${e.level / 2 + 1} · ${e.cands} candidates notées`;
      sil(e.sil);
    } else if (e.t === "done") {
      if (last) last.userData.mesh.material = three.mat;
      three.plane.visible = false;
      sil(e.sil);
      hud.where.textContent = `terminé : ${e.pieces} pièces en ${e.seconds} s · ${e.floating ? e.floating + " volent" : "rien ne vole"} · ${e.collisions ? e.collisions + " collisions" : "aucune collision"}`;
      ui.run.disabled = false;
    } else if (e.t === "error") {
      hud.where.textContent = "Erreur : " + e.msg; ui.run.disabled = false;
    }
  }

  function sil(s) {
    if (!s) return;
    for (const k of ["face", "profil", "dessus", "volume"]) {
      const v = Math.round(s[k] * 100);
      hud.sil[k].querySelector("i").style.width = v + "%";
      hud.sil[k].querySelector("b").textContent = v + " %";
      hud.sil[k].classList.toggle("ok", v >= 90);
    }
  }

  async function poll(id) {
    let since = 0;
    while (job === id && three) {
      let r;
      try { r = await api(`/api/fill/job/${id}?since=${since}`); }
      catch (e) { if (job === id) { hud.where.textContent = "Calcul perdu (serveur redémarré ?) : relance."; ui.run.disabled = false; } return; }
      if (job !== id) return;
      since = r.next;
      const parts = r.events.filter((e) => e.t === "place").map((e) => e.part);
      await loadGeo(parts);
      queue.push(...r.events);
      if (r.done) return;
      await new Promise((ok) => setTimeout(ok, 400));
    }
  }

  async function start() {
    job = null;                                                  // on abandonne l'affichage du calcul précédent
    ui.run.disabled = true;
    queue = []; clearPieces();
    hud.where.textContent = "Préparation de la cible…";
    const body = { src: ui.src.value, lam: +ui.lam.value, ratio: +ui.ratio.value, relax: +ui.relax.value, passes: +ui.passes.value, snot: ui.snot.checked };
    let r;
    try { r = await api("/api/fill/run", { method: "POST", body: JSON.stringify(body) }); }
    catch (e) { hud.where.textContent = "Erreur : " + e.message; ui.run.disabled = false; return; }
    job = r.job;
    ui.run.disabled = false;                                     // « Relancer » reste possible pendant le calcul
    showTarget(await api(`/api/fill/job/${r.job}/target`));
    hud.where.textContent = "Calcul en cours…";
    poll(r.job);
  }

  async function mount(host) {
    const srcs = await api("/api/fill/sources");
    const num = (label, val, min, max, stp, title) => h("label", { class: "flv-num", title }, h("span", {}, label), h("input", { type: "number", value: val, min, max, step: stp }));
    const lam = num("λ (débord)", 2, 0.2, 10, 0.2, "Pénalité par case posée hors de la forme"),
      ratio = num("part dedans", 0.6, 0.2, 1, 0.05, "Part minimale du volume d'une pièce qui doit être dans la forme"),
      relax = num("relâche", 0.5, 0.1, 1, 0.1, "λ est multiplié par ce facteur à chaque passe (boucher les trous)"),
      passes = num("passes", 3, 1, 6, 1, "Nombre de passes de bas en haut");
    const src = h("select", {}, srcs.map((s) => h("option", { value: s.id }, s.label)));
    const run = h("button", { class: "tool primary", onclick: start }, "Lancer");
    const pp = h("button", { class: "tool", onclick: () => { playing = !playing; pp.textContent = playing ? "Pause" : "Lecture"; } }, "Pause");
    const all = h("button", { class: "tool", onclick: () => { while (queue.length) step(); } }, "Tout afficher");
    const spd = h("input", { type: "range", min: 1, max: 120, value: speed, oninput: (e) => { speed = +e.target.value; spdl.textContent = speed + " pièces/s"; } });
    const spdl = h("small", { class: "muted" }, speed + " pièces/s");
    const snot = h("label", { class: "flv-num", title: "Briques à tenons sur le côté + pièces fixées latéralement" }, h("span", {}, "côtés"), h("input", { type: "checkbox", checked: true }));
    ui = { snot: snot.querySelector("input"), src, run, lam: lam.querySelector("input"), ratio: ratio.querySelector("input"), relax: relax.querySelector("input"), passes: passes.querySelector("input") };
    let deb = null;                                              // changer un réglage relance tout seul (après une courte pause)
    [ui.lam, ui.ratio, ui.relax, ui.passes, ui.snot, ui.src].forEach((el) => el.addEventListener("change", () => { clearTimeout(deb); deb = setTimeout(start, 500); }));
    const bar = (k, t) => h("div", { class: "flv-sil" }, h("span", {}, t), h("div", { class: "flv-track" }, h("i", {})), h("b", {}, "–"));
    hud = { where: h("div", { class: "flv-where" }, "Choisis une cible puis « Lancer »."), piece: h("span", { class: "mono" }, "–"), count: h("b", {}, "0"),
      sil: { face: bar("face", "Face"), profil: bar("profil", "Profil"), dessus: bar("dessus", "Dessus"), volume: bar("volume", "Volume") } };
    const stage = h("div", { class: "flv-stage" });
    host.replaceChildren(h("div", { class: "flv" },
      h("div", { class: "flv-bar" }, src, lam, ratio, relax, passes, snot, run),
      h("div", { class: "flv-bar" }, pp, all, h("label", { class: "flv-speed" }, "Vitesse", spd, spdl),
        h("small", { class: "muted" }, "Bleu transparent : la forme visée · orange : la dernière pièce posée · plan : la plate en cours")),
      h("div", { class: "flv-row" }, stage,
        h("aside", { class: "flv-hud" }, hud.where,
          h("div", { class: "flv-kpi" }, h("small", {}, "Pièces posées"), hud.count),
          h("div", { class: "flv-kpi" }, h("small", {}, "Dernière pièce"), hud.piece),
          h("h4", {}, "Silhouettes (objectif 90 %)"), Object.values(hud.sil)))));
    setup(stage);
    const pref = srcs.find((s) => s.kind === "mesh") || srcs[0];
    if (pref) src.value = pref.id;
  }

  return { mount };
})();
