// Brick Forge Lab — galerie BrickHeadz en 3D (note « 10 · Galerie ») :
// trois modèles côte à côte (officiel, couches cible 3D, couches cible fiche) dans un seul canvas,
// une caméra partagée : ils tournent ensemble.
"use strict";

const BHG = (() => {
  const geo = {};
  let colors = null, three = null, list = null, cur = null;
  const KINDS = [["officiel", "Officiel"], ["3d", "Couches · cible 3D"], ["fiche", "Couches · cible fiche"]];

  function f32(b64) {
    const bin = atob(b64), buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    return new Float32Array(buf.buffer);
  }

  async function loadGeo(parts) {
    const need = [...new Set(parts)].filter((p) => !(p in geo));
    for (let i = 0; i < need.length; i += 150) {
      const chunk = need.slice(i, i + 150);
      const r = await api("/api/parts-batch", { method: "POST", body: JSON.stringify(chunk) });
      for (const p of chunk) geo[p] = r[p] ? { tris: f32(r[p].tris), edges: f32(r[p].edges) } : null;
    }
  }

  function meshOf(parts) {
    let ns = 0, ne = 0;
    for (const p of parts) { const g = geo[p.part]; if (g) { ns += g.tris.length; ne += g.edges.length; } }
    const pos = new Float32Array(ns), col = new Float32Array(ns), epos = new Float32Array(ne);
    let o = 0, oe = 0;
    const c = new THREE.Color();
    for (const p of parts) {
      const g = geo[p.part]; if (!g) continue;
      c.set((colors[p.color] || {}).hex || "#9a9a9a");
      const [x, y, z, a, b, cc, d, e, f, gg, hh, i] = p.m;
      const put = (src, dst, off, cdst) => {
        for (let k = 0; k < src.length; k += 3) {
          const vx = src[k], vy = src[k + 1], vz = src[k + 2];
          dst[off + k] = a * vx + b * vy + cc * vz + x; dst[off + k + 1] = d * vx + e * vy + f * vz + y; dst[off + k + 2] = gg * vx + hh * vy + i * vz + z;
          if (cdst) { cdst[off + k] = c.r; cdst[off + k + 1] = c.g; cdst[off + k + 2] = c.b; }
        }
      };
      put(g.tris, pos, o, col); o += g.tris.length;
      put(g.edges, epos, oe, null); oe += g.edges.length;
    }
    const grp = new THREE.Group();
    const bg = new THREE.BufferGeometry();
    bg.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    bg.setAttribute("color", new THREE.BufferAttribute(col, 3));
    bg.computeVertexNormals();
    grp.add(new THREE.Mesh(bg, three.mat));
    const eg = new THREE.BufferGeometry();
    eg.setAttribute("position", new THREE.BufferAttribute(epos, 3));
    grp.add(new THREE.LineSegments(eg, three.edge));
    grp.scale.set(1 / 20, -1 / 20, 1 / 20);
    return grp;
  }

  function setup(stage) {
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setScissorTest(true);
    stage.prepend(renderer.domElement);
    const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 2000);
    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    const scenes = KINDS.map(() => {
      const sc = new THREE.Scene();
      sc.add(new THREE.HemisphereLight(0xffffff, 0x7d756a, 0.85));
      const d1 = new THREE.DirectionalLight(0xffffff, 0.6); d1.position.set(15, 30, -20); sc.add(d1);
      const d2 = new THREE.DirectionalLight(0xffffff, 0.25); d2.position.set(-20, 10, 25); sc.add(d2);
      return sc;
    });
    const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.4, metalness: 0, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
    const edge = new THREE.LineBasicMaterial({ color: 0x1b1b1b, transparent: true, opacity: 0.3 });
    three = { renderer, camera, controls, scenes, mat, edge, stage, roots: [] };
    const loop = () => {
      if (!renderer.domElement.isConnected) { three = null; renderer.dispose(); return; }
      const w = stage.clientWidth, hh = stage.clientHeight;
      if (w && hh) {
        const cw = renderer.domElement.width / renderer.getPixelRatio();
        if (Math.abs(cw - w) > 1 || Math.abs(renderer.domElement.height / renderer.getPixelRatio() - hh) > 1) renderer.setSize(w, hh, false);
        const vw = w / 3;
        camera.aspect = vw / hh; camera.updateProjectionMatrix();
        controls.update();
        scenes.forEach((sc, i) => { renderer.setViewport(i * vw, 0, vw, hh); renderer.setScissor(i * vw, 0, vw, hh); renderer.render(sc, camera); });
      }
      requestAnimationFrame(loop);
    };
    loop();
  }

  async function show(key) {
    if (!three) return;
    const [num, fig] = key.split("#");
    const lbl = three.stage.querySelector(".bhg-status");
    lbl.textContent = "Chargement…";
    const d = await api(`/api/bh/model/${num}/${fig}`);
    if (!three) return;
    await loadGeo(KINDS.flatMap(([k]) => d[k].map((p) => p.part)));
    if (!three) return;
    three.roots.forEach((r, i) => { three.scenes[i].remove(r); r.traverse((o) => o.geometry && o.geometry.dispose()); });
    three.roots = KINDS.map(([k], i) => { const g = meshOf(d[k]); three.scenes[i].add(g); return g; });
    // cadrage commun (sur l'officiel), vue de trois quarts face
    const bb = new THREE.Box3();
    three.roots.forEach((r) => bb.expandByObject(r));
    const c = bb.getCenter(new THREE.Vector3()), s = bb.getSize(new THREE.Vector3());
    const dist = Math.max(s.y, s.x) * 2.6;
    three.controls.target.copy(c);
    three.camera.position.set(c.x - dist * 0.45, c.y + dist * 0.25, c.z - dist * 0.85);
    three.camera.near = dist / 50; three.camera.far = dist * 20; three.camera.updateProjectionMatrix();
    cur = key;
    const it = list.find((x) => x.key === key) || {};
    three.stage.querySelectorAll(".bhg-lab b").forEach((b, i) => {
      const n = d[KINDS[i][0]].length;
      b.textContent = n ? `${n} pièces` : "pas encore construit";
    });
    lbl.textContent = `${d.set}${it.nfigs > 1 ? ` (${it.fig + 1}/${it.nfigs})` : ""} · ${num}`;
    const sel = three.stage.parentElement.querySelector("select");
    if (sel) sel.value = key;
  }

  async function mount(host, article) {
    if (!colors) colors = await api("/api/ldcolors");
    list = await api("/api/bh/gallery");
    const stage = h("div", { class: "bhg-stage" },
      h("div", { class: "bhg-labs" }, KINDS.map(([, t]) => h("div", { class: "bhg-lab" }, h("span", {}, t), h("b", {}, "")))),
      h("div", { class: "bhg-status" }, ""));
    const sel = h("select", { onchange: (e) => show(e.target.value) },
      list.map((x) => h("option", { value: x.key }, `${x.set}${x.nfigs > 1 ? ` (${x.fig + 1}/${x.nfigs})` : ""} · ${x.num}`)));
    const prev = () => { const i = list.findIndex((x) => x.key === cur); show(list[(i - 1 + list.length) % list.length].key); };
    const next = () => { const i = list.findIndex((x) => x.key === cur); show(list[(i + 1) % list.length].key); };
    host.replaceChildren(h("div", { class: "bhg" },
      h("div", { class: "bhg-bar" }, h("button", { class: "tool", onclick: prev }, "←"), sel, h("button", { class: "tool", onclick: next }, "→"),
        h("small", { class: "muted" }, "Glisser pour tourner · molette pour zoomer · les trois tournent ensemble")),
      stage));
    setup(stage);
    article.querySelectorAll("img").forEach((img) => {
      const m = img.getAttribute("src").match(/10-galerie\/(.+)_(\d+)\.png/);
      if (!m) return;
      img.style.cursor = "pointer";
      img.title = "Voir en 3D";
      img.addEventListener("click", () => { show(`${m[1]}#${m[2]}`); host.scrollIntoView({ behavior: "smooth", block: "start" }); });
    });
    show(list.find((x) => x.key === "40377-1#0") ? "40377-1#0" : list[0].key);
  }

  return { mount };
})();
