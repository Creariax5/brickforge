// Brick Forge Lab — note « Image → 3D → LEGO » : photo d'entrée, maillage généré (Hunyuan3D…),
// figurine LEGO construite couche par couche, et l'officielle si on en a une. Trois vues 3D, une caméra commune.
"use strict";

const I3D = (() => {
  const geo = {};
  let colors = null, three = null, list = null, cur = null, kind = "couches";
  const PANES = [["mesh", "Modèle 3D généré"], ["lego", "Figurine LEGO construite"], ["ref", "Officielle"]];

  const f32 = (b64) => { const bin = atob(b64), buf = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i); return new Float32Array(buf.buffer); };

  async function loadGeo(parts) {
    const need = [...new Set(parts)].filter((p) => !(p in geo));
    for (let i = 0; i < need.length; i += 150) {
      const chunk = need.slice(i, i + 150);
      const r = await api("/api/parts-batch", { method: "POST", body: JSON.stringify(chunk) });
      for (const p of chunk) geo[p] = r[p] ? { tris: f32(r[p].tris), edges: f32(r[p].edges) } : null;
    }
  }

  function legoMesh(parts) {
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
    const outer = new THREE.Group(); outer.add(grp);
    return outer;
  }

  function loadGLB(url) {
    // les GLB de Hunyuan3D ont leurs UV dans le sens « image » : on retourne la texture (même réglage que from_mesh.FLIPV = 0)
    return new Promise((ok, ko) => new THREE.GLTFLoader().load(url, (g) => {
      g.scene.traverse((o) => {
        const uv = o.geometry && o.geometry.attributes.uv;          // ImageBitmap : flipY est ignoré, on retourne les UV
        if (uv) { for (let i = 0; i < uv.count; i++) uv.setY(i, 1 - uv.getY(i)); uv.needsUpdate = true; }
      });
      ok(g.scene);
    }, undefined, ko));
  }

  function setup(stage) {
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setScissorTest(true);
    renderer.outputEncoding = THREE.sRGBEncoding;
    stage.prepend(renderer.domElement);
    const camera = new THREE.PerspectiveCamera(30, 1, 0.01, 2000);
    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    const scenes = PANES.map(() => {
      const sc = new THREE.Scene();
      sc.add(new THREE.HemisphereLight(0xffffff, 0x7d756a, 0.9));
      const d1 = new THREE.DirectionalLight(0xffffff, 0.6); d1.position.set(15, 30, -20); sc.add(d1);
      const d2 = new THREE.DirectionalLight(0xffffff, 0.3); d2.position.set(-20, 10, 25); sc.add(d2);
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
        if (Math.abs(renderer.domElement.width / renderer.getPixelRatio() - w) > 1 || Math.abs(renderer.domElement.height / renderer.getPixelRatio() - hh) > 1) renderer.setSize(w, hh, false);
        const vw = w / 3;
        camera.aspect = vw / hh; camera.updateProjectionMatrix();
        controls.update();
        scenes.forEach((sc, i) => { renderer.setViewport(i * vw, 0, vw, hh); renderer.setScissor(i * vw, 0, vw, hh); renderer.render(sc, camera); });
      }
      requestAnimationFrame(loop);
    };
    loop();
  }

  async function show(name) {
    if (!three) return;
    const it = list.find((x) => x.name === name);
    const st = three.stage.querySelector(".bhg-status");
    st.textContent = "Chargement…";
    three.photo.src = it.img || "";
    if (kind === "fill" && !it.fill) kind = "couches";
    const has = kind === "fill" ? !!it.fill : it.built;
    const [glb, lg] = await Promise.all([loadGLB(it.glb), has ? api(`/api/i3d/${name}/lego?kind=${kind}`) : Promise.resolve({ lego: [], ref: null })]);
    three.stage.parentElement.querySelectorAll(".i3d-kind button").forEach((b) => { b.setAttribute("aria-pressed", String(b.dataset.k === kind)); b.disabled = b.dataset.k === "fill" && !it.fill; });
    await loadGeo([...lg.lego, ...(lg.ref || [])].map((p) => p.part));
    if (!three) return;
    three.roots.forEach((r, i) => three.scenes[i].remove(r));
    const lego = legoMesh(lg.lego);
    const ref = lg.ref ? legoMesh(lg.ref) : new THREE.Group();
    // le maillage généré : même orientation que pour la construction (quart de tour `yaw`), même hauteur que la figurine
    const m = new THREE.Group(); m.add(glb); glb.rotation.y = (it.yaw || 0) * Math.PI / 2;   // même quart de tour que pour la construction
    m.updateMatrixWorld(true);
    const lb = new THREE.Box3().setFromObject(lego), gb = new THREE.Box3().setFromObject(m);
    const ls = lb.getSize(new THREE.Vector3()), gs = gb.getSize(new THREE.Vector3());
    const k = ls.y > 0 && gs.y > 0 ? ls.y / gs.y : 1;
    m.scale.setScalar(k); m.updateMatrixWorld(true);
    const gb2 = new THREE.Box3().setFromObject(m), lc = lb.getCenter(new THREE.Vector3()), gc = gb2.getCenter(new THREE.Vector3());
    m.position.set(lc.x - gc.x, lb.min.y - gb2.min.y, lc.z - gc.z);
    three.roots = [m, lego, ref];
    three.roots.forEach((r, i) => three.scenes[i].add(r));
    const bb = lb.isEmpty() ? new THREE.Box3().setFromObject(m) : lb;
    const c = bb.getCenter(new THREE.Vector3()), s = bb.getSize(new THREE.Vector3());
    const dist = Math.max(s.y, s.x) * 2.6;
    three.controls.target.copy(c);
    three.camera.position.set(c.x - dist * 0.45, c.y + dist * 0.25, c.z - dist * 0.85);
    three.camera.near = dist / 50; three.camera.far = dist * 20; three.camera.updateProjectionMatrix();
    cur = name;
    const labs = three.stage.querySelectorAll(".bhg-lab b");
    labs[0].textContent = "Hunyuan3D 2.1";
    const info = kind === "fill" ? it.fill : it;
    three.stage.querySelectorAll(".bhg-lab span")[1].textContent = kind === "fill" ? "Remplissage optimisé (forme seule)" : "Figurine LEGO · couches";
    labs[1].textContent = has ? `${lg.lego.length} pièces · ${info.floating ? info.floating + " volent" : "rien ne vole"}${info.collisions ? " · " + info.collisions + " collisions" : ""}` : "pas encore construite";
    labs[2].textContent = lg.ref ? `${lg.ref.length} pièces` : "pas d'officielle pour ce concept";
    const mm = it.metrics, sf = it.fill && it.fill.silhouettes;
    st.textContent = kind === "fill" && sf
      ? `Silhouettes vs modèle 3D : face ${Math.round(sf.face * 100)} % · profil ${Math.round(sf.profil * 100)} % · dessus ${Math.round(sf.dessus * 100)} % · volume ${Math.round(sf.volume * 100)} %`
      : mm ? `Comparée à l'officielle : volume ${mm.iou3d} · face juste ${Math.round(mm.front_acc * 100)} %` : "";
    const sel = three.stage.parentElement.querySelector("select");
    if (sel) sel.value = name;
  }

  async function mount(host) {
    if (!window.THREE || !THREE.GLTFLoader) await new Promise((ok, ko) => { const s = document.createElement("script"); s.src = "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"; s.onload = ok; s.onerror = ko; document.head.append(s); });
    if (!colors) colors = await api("/api/ldcolors");
    list = await api("/api/i3d");
    if (!list.length) { host.replaceChildren(h("p", { class: "muted" }, "Aucun modèle généré pour l'instant.")); return; }
    const photo = h("img", { class: "i3d-photo", alt: "Image d'entrée" });
    const stage = h("div", { class: "bhg-stage" },
      h("div", { class: "bhg-labs" }, PANES.map(([, t]) => h("div", { class: "bhg-lab" }, h("span", {}, t), h("b", {}, "")))),
      h("div", { class: "bhg-status" }, ""));
    const sel = h("select", { onchange: (e) => show(e.target.value) }, list.map((x) => h("option", { value: x.name }, x.name)));
    const step = (d) => { const i = list.findIndex((x) => x.name === cur); show(list[(i + d + list.length) % list.length].name); };
    host.replaceChildren(h("div", { class: "bhg" },
      h("div", { class: "bhg-bar" }, h("button", { class: "tool", onclick: () => step(-1) }, "←"), sel, h("button", { class: "tool", onclick: () => step(1) }, "→"),
        h("span", { class: "i3d-kind" }, [["couches", "Couches (couleurs)"], ["fill", "Remplissage optimisé"]].map(([k, t]) =>
          h("button", { class: "tool", "data-k": k, "aria-pressed": String(k === kind), onclick: () => { kind = k; show(cur); } }, t))),
        h("small", { class: "muted" }, "Glisser pour tourner · molette pour zoomer · les trois tournent ensemble")),
      h("div", { class: "i3d-row" }, h("figure", { class: "i3d-in" }, photo, h("figcaption", {}, "Image d'entrée")), stage)));
    setup(stage);
    three.photo = photo;
    show(list[0].name);
  }

  return { mount };
})();
