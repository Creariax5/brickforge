// Brick Forge Lab — note 13 « Un réseau qui apprend à remplir » : suivi en direct de l'apprentissage
// lancé sur le Mac Studio (brickforge.fill_learn) : étape, courbes, plafond, constructions en 3D.
"use strict";

const TRF = (() => {
  const geo = {};
  const GOAL = 0.95, HEUR = null;                // objectif : volume commun avec la vraie LEGO
  const SER = [["donald_beam", "Donald · réseau + faisceau", "var(--trf-a)"], ["donald", "Donald · réseau seul", "var(--trf-b)"],
    ["test_mean", "Moyenne des 11 formes de test", "var(--trf-c)"]];
  let ui = null, three = null, timer = null, curModel = null, autoModel = true;

  const f32 = (b64) => { const bin = atob(b64), buf = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i); return new Float32Array(buf.buffer); };
  const pct = (v) => v == null ? "—" : Math.round(v * 1000) / 10 + " %";
  const ago = (t, now) => { const s = Math.max(0, Math.round(now - t)); return s < 60 ? `il y a ${s} s` : s < 3600 ? `il y a ${Math.round(s / 60)} min` : `il y a ${(s / 3600).toFixed(1)} h`; };
  const SVGNS = "http://www.w3.org/2000/svg";
  const sv = (tag, a = {}, ...kids) => { const e = document.createElementNS(SVGNS, tag); for (const k in a) e.setAttribute(k, a[k]); kids.flat().forEach((c) => c != null && e.append(c)); return e; };

  // ---------- courbe : volume commun par itération (une seule échelle, 0–100 %)
  function lineChart(evals, ceil) {
    const W = 560, H = 220, L = 44, R = 150, T = 12, B = 28;
    const xs = evals.map((e) => e.iter), nx = Math.max(1, ...xs, 3), allv = evals.flatMap((e) => [e.donald, e.donald_beam, e.test_mean]).filter((v) => v != null);
    const lo = Math.min(0.6, Math.floor(Math.min(...allv, 0.6) * 10) / 10), X = (i) => L + (i / nx) * (W - L - R), Y = (v) => T + (1 - (v - lo) / (1 - lo)) * (H - T - B);
    const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, class: "trf-chart", role: "img", "aria-label": "Volume commun par itération" });
    for (let v = lo; v <= 1.0001; v += 0.1) {
      svg.append(sv("line", { x1: L, x2: W - R, y1: Y(v), y2: Y(v), class: "trf-grid" }), sv("text", { x: L - 6, y: Y(v) + 4, class: "trf-ax", "text-anchor": "end" }, Math.round(v * 100) + " %"));
    }
    for (let i = 0; i <= nx; i++) svg.append(sv("text", { x: X(i), y: H - 8, class: "trf-ax", "text-anchor": "middle" }, i === 0 ? "heur." : "it. " + i));
    svg.append(sv("line", { x1: L, x2: W - R, y1: Y(GOAL), y2: Y(GOAL), class: "trf-goal" }), sv("text", { x: W - R + 6, y: Y(GOAL) + 4, class: "trf-lab" }, "objectif 95 %"));
    if (ceil != null) svg.append(sv("line", { x1: L, x2: W - R, y1: Y(ceil), y2: Y(ceil), class: "trf-ceil" }), sv("text", { x: W - R + 6, y: Y(ceil) + 4, class: "trf-lab" }, "plafond " + pct(ceil)));
    const tip = sv("text", { class: "trf-tip", x: 0, y: 0, visibility: "hidden" });
    SER.forEach(([k, name, col]) => {
      const pts = evals.map((e) => [e.iter, k === "donald_beam" && e.iter === 0 ? null : e[k]]).filter((p) => p[1] != null);
      if (!pts.length) return;
      svg.append(sv("polyline", { points: pts.map(([i, v]) => `${X(i)},${Y(v)}`).join(" "), fill: "none", stroke: col, "stroke-width": 2, "stroke-linejoin": "round" }));
      pts.forEach(([i, v]) => {
        const c = sv("circle", { cx: X(i), cy: Y(v), r: 4.5, fill: col, stroke: "var(--panel)", "stroke-width": 2 });
        const hit = sv("circle", { cx: X(i), cy: Y(v), r: 12, fill: "transparent" });
        hit.addEventListener("mouseenter", () => { tip.textContent = `${name} : ${pct(v)}`; tip.setAttribute("x", Math.min(X(i) + 8, W - 230)); tip.setAttribute("y", Y(v) - 10); tip.setAttribute("visibility", "visible"); });
        hit.addEventListener("mouseleave", () => tip.setAttribute("visibility", "hidden"));
        svg.append(c, hit);
      });
    });
    svg.append(tip);
    const legend = h("div", { class: "trf-legend" }, SER.map(([, name, col]) => h("span", {}, h("i", { style: `background:${col}` }), name)));
    return h("div", {}, legend, svg);
  }

  // ---------- courbe de perte de l'itération en cours
  function lossChart(L) {
    if (!L || !L.hist.length) return h("p", { class: "muted" }, "Pas encore d'apprentissage.");
    const W = 560, H = 150, l = 44, r = 20, t = 10, b = 24, hs = L.hist, mx = Math.max(...hs.map((x) => x.loss), 0.01), sx = Math.max(...hs.map((x) => x.step), 1);
    const X = (s) => l + (s / sx) * (W - l - r), Y = (v) => t + (1 - v / mx) * (H - t - b);
    const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, class: "trf-chart", role: "img", "aria-label": "Perte d'apprentissage" });
    [0, mx / 2, mx].forEach((v) => svg.append(sv("line", { x1: l, x2: W - r, y1: Y(v), y2: Y(v), class: "trf-grid" }), sv("text", { x: l - 6, y: Y(v) + 4, class: "trf-ax", "text-anchor": "end" }, v.toFixed(2))));
    svg.append(sv("text", { x: W - r, y: H - 6, class: "trf-ax", "text-anchor": "end" }, `pas ${sx}`));
    svg.append(sv("polyline", { points: hs.map((x) => `${X(x.step)},${Y(x.loss)}`).join(" "), fill: "none", stroke: "var(--trf-b)", "stroke-width": 2 }));
    const acc = [...hs].reverse().find((x) => x.acc_test != null);
    return h("div", {}, svg, h("p", { class: "muted trf-small" },
      `Itération ${L.iter} · perte ${hs[hs.length - 1].loss} · bon classement (paire posée / bloquée) : entraînement ${pct(acc && acc.acc_train)}, test ${pct(acc && acc.acc_test)}`
      + (L.pairs_train ? ` · ${L.pairs_train.toLocaleString("fr-FR")} paires` : "")),
      acc && acc.v_mae_test != null ? h("p", { class: "muted trf-small" },
        `Tête de valeur (prédit le volume commun final depuis un état à moitié construit) : erreur moyenne ${pct(acc.v_mae_test)} · `
        + `départage deux états ${pct(acc.v_rank_test)} du temps (50 % = hasard)`
        + (L.value_ok === true ? " · utilisée dans le faisceau" : L.value_ok === false ? " · pas encore assez fiable, le faisceau garde la note faite main" : "")) : null);
  }

  function silBars(sil) {
    if (!sil) return null;
    return h("div", { class: "trf-sils" }, [["face", "Face"], ["profil", "Profil"], ["dessus", "Dessus"], ["volume", "Volume"]].map(([k, t]) =>
      h("div", { class: "flv-sil" + (sil[k] >= GOAL ? " ok" : "") }, h("span", {}, t), h("div", { class: "flv-track trf-track" }, h("i", { style: `width:${sil[k] * 100}%` })), h("b", {}, Math.round(sil[k] * 100) + " %"))));
  }

  // ---------- vue 3D d'une construction
  async function loadGeo(parts) {
    const need = [...new Set(parts)].filter((p) => !(p in geo));
    for (let i = 0; i < need.length; i += 150) {
      const chunk = need.slice(i, i + 150);
      const r = await api("/api/parts-batch", { method: "POST", body: JSON.stringify(chunk) });
      for (const p of chunk) geo[p] = r[p] ? { tris: f32(r[p].tris), edges: f32(r[p].edges) } : null;
    }
  }

  function setup(stage) {
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    stage.prepend(renderer.domElement);
    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xffffff, 0x7d756a, 0.9));
    const d1 = new THREE.DirectionalLight(0xffffff, 0.6); d1.position.set(15, 30, -20); scene.add(d1);
    const d2 = new THREE.DirectionalLight(0xffffff, 0.3); d2.position.set(-20, 10, 25); scene.add(d2);
    const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 2000);
    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    three = { renderer, scene, camera, controls, root: null,
      mat: new THREE.MeshStandardMaterial({ color: 0xb4b8bd, roughness: 0.45, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }),
      side: new THREE.MeshStandardMaterial({ color: 0x5b8fc9, roughness: 0.45, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }),
      edge: new THREE.LineBasicMaterial({ color: 0x1b1b1b, transparent: true, opacity: 0.3 }) };
    const loop = () => {
      if (!renderer.domElement.isConnected) { three = null; renderer.dispose(); return; }
      const w = stage.clientWidth, hh = stage.clientHeight;
      if (w && hh && (Math.abs(renderer.domElement.width / renderer.getPixelRatio() - w) > 1 || Math.abs(renderer.domElement.height / renderer.getPixelRatio() - hh) > 1)) {
        renderer.setSize(w, hh, false); camera.aspect = w / hh; camera.updateProjectionMatrix();
      }
      controls.update(); renderer.render(scene, camera); requestAnimationFrame(loop);
    };
    loop();
  }

  function build(placed) {
    const grp = new THREE.Group();
    const add = (list, mat) => {
      let n = 0, ne = 0;
      for (const p of list) { const g = geo[p.part]; if (g) { n += g.tris.length; ne += g.edges.length; } }
      const pos = new Float32Array(n), ep = new Float32Array(ne);
      let o = 0, oe = 0;
      for (const p of list) {
        const g = geo[p.part]; if (!g) continue;
        const [x, y, z, a, b, c, d, e, f, gg, hh, i] = p.m;
        const put = (src, dst, off) => { for (let k = 0; k < src.length; k += 3) { const vx = src[k], vy = src[k + 1], vz = src[k + 2]; dst[off + k] = a * vx + b * vy + c * vz + x; dst[off + k + 1] = d * vx + e * vy + f * vz + y; dst[off + k + 2] = gg * vx + hh * vy + i * vz + z; } };
        put(g.tris, pos, o); o += g.tris.length; put(g.edges, ep, oe); oe += g.edges.length;
      }
      const bg = new THREE.BufferGeometry(); bg.setAttribute("position", new THREE.BufferAttribute(pos, 3)); bg.computeVertexNormals();
      grp.add(new THREE.Mesh(bg, mat));
      const eg = new THREE.BufferGeometry(); eg.setAttribute("position", new THREE.BufferAttribute(ep, 3));
      grp.add(new THREE.LineSegments(eg, three.edge));
    };
    // pièces fixées sur le côté = rotation qui ne garde pas l'axe vertical
    const isSide = (p) => Math.abs(Math.abs(p.m[7]) - 1) > 1e-3;
    add(placed.filter((p) => !isSide(p)), three.mat);
    add(placed.filter(isSide), three.side);
    grp.scale.set(1 / 20, -1 / 20, 1 / 20);
    const outer = new THREE.Group(); outer.add(grp); return outer;
  }

  async function showModel(file) {
    if (!three || !file) return;
    curModel = file;
    const d = await api(`/api/train-fill/model/${encodeURIComponent(file)}`);
    await loadGeo(d.placed.map((p) => p.part));
    if (!three || curModel !== file) return;
    if (three.root) three.scene.remove(three.root);
    three.root = build(d.placed); three.scene.add(three.root);
    const bb = new THREE.Box3().setFromObject(three.root), c = bb.getCenter(new THREE.Vector3()), s = bb.getSize(new THREE.Vector3());
    const dist = Math.max(s.x, s.y) * 2.6;
    if (!three.placed) { three.controls.target.copy(c); three.camera.position.set(c.x - dist * 0.45, c.y + dist * 0.25, c.z - dist * 0.85); three.placed = true; }
    three.camera.near = dist / 50; three.camera.far = dist * 20; three.camera.updateProjectionMatrix();
    ui.modelInfo.replaceChildren(h("b", {}, `${d.name} · ${label(d.tag)}`), h("small", { class: "muted" }, `${d.n} pièces dont ${d.side || 0} sur le côté (en bleu) · volume commun avec la vraie LEGO ${pct(d.score)}`), silBars(d.sil));
  }

  const label = (tag) => tag === "plafond" ? "meilleure du plafond" : tag.replace(/^eval(\d+)_w(\d+)$/, (_, i, w) => (i === "0" ? "heuristique" : "réseau " + i) + (w === "1" ? " seul" : " + faisceau " + w));

  // ---------- rendu de l'état
  function render(s) {
    const now = s.now || Date.now() / 1000;
    const prog = s.progress ? `${s.progress[0]} / ${s.progress[1]}` : "";
    ui.head.replaceChildren(
      h("span", { class: "status" + (s.stage === "terminé" ? "" : " run") }, s.stage || "—"),
      prog ? h("span", { class: "trf-prog" }, h("i", { style: `width:${(100 * s.progress[0]) / Math.max(1, s.progress[1])}%` })) : null,
      prog ? h("small", {}, prog + " tâches") : null,
      h("small", { class: "muted" }, s.updated ? `Mac Studio · mis à jour ${ago(s.updated, now)}` + (s.started ? ` · lancé ${ago(s.started, now)}` : "") : ""));
    const ev = s.evals || [], ceil = s.ceiling || [];
    const cbest = ceil.length ? Math.max(...ceil.map((c) => c.score)) : null;
    const netBest = Math.max(-1, ...ev.filter((e) => e.iter > 0).map((e) => Math.max(e.donald || 0, e.donald_beam || 0)));
    ui.kpis.replaceChildren(
      kpi("Donald · glouton heuristique", pct(ev.length ? ev[0].donald : HEUR), "volume commun avec la vraie LEGO"),
      kpi("Donald · plafond (faisceau 24)", pct(cbest), ceil.length ? `${ceil.length} / 8 essais` : "en cours"),
      kpi("Donald · meilleur avec le réseau", netBest > 0 ? pct(netBest) : "—", ev.length > 1 ? `après ${ev.length - 1} itération(s)` : "après la 1re itération"),
      kpi("Objectif", "95 %", "volume commun avec la vraie LEGO"));
    ui.chart.replaceChildren(ev.length ? lineChart(ev, cbest) : h("p", { class: "muted" }, "La première mesure arrive à la fin de l'étape « plafond + experts »."));
    ui.loss.replaceChildren(lossChart((s.loss || [])[s.loss ? s.loss.length - 1 : 0]));
    ui.ceil.replaceChildren(ceil.length ? h("table", { class: "trf-table" },
      h("thead", {}, h("tr", {}, ["λ", "graine", "Face", "Profil", "Dessus", "Volume", "Pièces", "Durée"].map((t) => h("th", {}, t)))),
      h("tbody", {}, [...ceil].sort((a, b) => b.score - a.score).map((c) => h("tr", {}, h("td", {}, c.lam), h("td", {}, c.seed),
        ["face", "profil", "dessus", "volume"].map((k) => h("td", { class: c.sil[k] >= GOAL ? "trf-ok" : "" }, pct(c.sil[k]))), h("td", {}, c.n), h("td", {}, Math.round(c.seconds / 60) + " min")))))
      : h("p", { class: "muted" }, "8 recherches très larges sur Donald en cours (≈ 30–60 min chacune)."));
    const t = s.targets || {}, trn = s.train || [];
    const vals = trn.map((n) => t[n] && t[n].score).filter((v) => v != null);
    ui.experts.textContent = vals.length ? `Meilleures constructions trouvées sur ${vals.length} / ${trn.length} formes d'entraînement : moyenne ${pct(vals.reduce((a, b) => a + b, 0) / vals.length)}, ${vals.filter((v) => v >= GOAL).length} au-dessus de 95 %.` : "";
    const ms = s.models || [];
    const opts = ms.map((m) => [m.file, `${m.name} · ${label(m.tag)} · ${pct(m.score)}`]);
    const sig = opts.map((o) => o[0]).join("|");
    if (ui.sel.dataset.sig !== sig) {
      ui.sel.replaceChildren(...opts.map(([v, t]) => h("option", { value: v }, t)));
      ui.sel.dataset.sig = sig;
      const don = ms.filter((m) => m.name === s.donald).sort((a, b) => b.score - a.score)[0];
      if (autoModel && don && don.file !== curModel) showModel(don.file);
      if (curModel) ui.sel.value = curModel;
    }
    ui.log.replaceChildren(...(s.log || []).slice(-12).reverse().map(([tt, m]) => h("div", {}, h("small", { class: "muted" }, new Date(tt * 1000).toLocaleTimeString("fr-FR")), " ", m)));
  }

  const kpi = (l, v, sub) => h("div", { class: "trf-kpi" }, h("small", {}, l), h("b", {}, v), h("small", { class: "muted" }, sub));

  async function tick() {
    if (!ui || !ui.root.isConnected) { clearInterval(timer); timer = null; return; }
    try { render(await api("/api/train-fill/status")); } catch (e) { ui.head.textContent = "Pas de nouvelles du Mac : " + e.message; }
  }

  async function mount(host) {
    const stage = h("div", { class: "trf-stage" });
    ui = { root: h("div", { class: "trf" }), head: h("div", { class: "trf-head" }), kpis: h("div", { class: "trf-kpis" }), chart: h("div", {}), loss: h("div", {}),
      ceil: h("div", {}), experts: h("p", { class: "trf-small" }), log: h("div", { class: "trf-log" }), modelInfo: h("div", { class: "trf-minfo" }),
      sel: h("select", { onchange: (e) => { autoModel = false; showModel(e.target.value); } }) };
    ui.root.append(ui.head, ui.kpis,
      h("div", { class: "trf-grid2" },
        h("section", {}, h("h4", {}, "Volume commun avec la vraie LEGO, par itération"), ui.chart),
        h("section", {}, h("h4", {}, "Apprentissage en cours"), ui.loss, ui.experts)),
      h("h4", {}, "Constructions"),
      h("div", { class: "flv-bar" }, ui.sel, h("small", { class: "muted" }, "Glisser pour tourner · molette pour zoomer")),
      h("div", { class: "flv-row" }, stage, ui.modelInfo),
      h("div", { class: "trf-grid2" },
        h("section", {}, h("h4", {}, "Plafond : recherche très large sur Donald"), ui.ceil),
        h("section", {}, h("h4", {}, "Journal du Mac"), ui.log)));
    host.replaceChildren(ui.root);
    setup(stage);
    await tick();
    timer = setInterval(tick, 5000);
  }

  return { mount };
})();
