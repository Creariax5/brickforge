// Brick Forge Lab — mode « Rendu » temps réel des vues 3D : plastique comme sur les visuels officiels.
//   - matériaux physiques (vernis, reflets d'un studio virtuel), tone mapping ACES, ombres douces au sol ;
//   - normales lissées au-delà de 35° (pièces rondes sans facettes) ;
//   - occlusion ambiante (SSAO) : les creux et les jointures entre pièces s'assombrissent ;
//   - étalonnage final (contraste, saturation) et anticrénelage FXAA.
// Les vues 3D passent leur objet three { renderer, scene, camera, controls, root, box, grid? } :
//   await Photo.set(three, true|false)   bascule (charge les scripts de post-traitement à la première fois)
//   Photo.tick(three)                    à chaque image : convertit ce qui a été ajouté depuis
//   Photo.render(three)                  dessine l'image (avec ou sans post-traitement)
//   Photo.snapshot(three, nom)           enregistre l'image en PNG
"use strict";

const Photo = (() => {
  const CDN = "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/";
  const POST = ["shaders/CopyShader.js", "postprocessing/EffectComposer.js", "postprocessing/ShaderPass.js", "math/SimplexNoise.js",
    "shaders/SSAOShader.js", "postprocessing/SSAOPass.js", "shaders/FXAAShader.js"];
  let postReady = null;
  const loadPost = () => postReady || (postReady = POST.reduce((pr, f) => pr.then(() => new Promise((ok, ko) => {
    const s = document.createElement("script"); s.src = CDN + f; s.onload = ok; s.onerror = () => ko(new Error("script " + f)); document.head.append(s);
  })), Promise.resolve()));

  const phys = new WeakMap();        // matériau plat → matériau physique
  let envTex = null;

  function env(renderer) {
    if (!envTex) {
      const pm = new THREE.PMREMGenerator(renderer);
      envTex = pm.fromScene(new THREE.RoomEnvironment(), 0.04).texture;
      pm.dispose();
    }
    return envTex;
  }

  const lin = (c) => (c ? c.clone().convertSRGBToLinear() : c);

  function physical(src) {
    if (phys.has(src)) return phys.get(src);
    const trans = !!src.transparent && src.opacity < 0.99;
    const m = new THREE.MeshPhysicalMaterial({
      color: src.vertexColors ? 0xffffff : lin(src.color),
      vertexColors: !!src.vertexColors,
      roughness: trans ? 0.05 : 0.16, metalness: 0,
      clearcoat: trans ? 1 : 0.6, clearcoatRoughness: 0.06,
      reflectivity: 0.45, envMapIntensity: 0.55,
      transparent: trans, opacity: trans ? 0.55 : 1, depthWrite: !trans,
      side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
      emissive: src.emissive ? lin(src.emissive) : 0x000000, emissiveIntensity: src.emissiveIntensity ?? 1,
    });
    m.userData.photo = true;
    phys.set(src, m);
    return m;
  }

  // couleurs par sommet : stockées en sRGB → linéaires pour le rendu physique
  function linColors(geo, on) {
    const a = geo.getAttribute && geo.getAttribute("color");
    if (!a || !!geo.userData.lin === on) return;
    const arr = a.array;
    if (on) {
      geo.userData.srgb = arr.slice();
      for (let i = 0; i < arr.length; i++) { const c = arr[i]; arr[i] = c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }
    } else if (geo.userData.srgb) arr.set(geo.userData.srgb);
    geo.userData.lin = on;
    a.needsUpdate = true;
  }

  // normales lissées entre faces voisines dont l'angle est < 35° (géométrie non indexée, triangles)
  function creaseNormals(geo, on) {
    const na = geo.getAttribute("normal"), pa = geo.getAttribute("position");
    if (!na || !pa || geo.index || !!geo.userData.creased === on) return;
    if (!on) { if (geo.userData.flatN) na.array.set(geo.userData.flatN); geo.userData.creased = false; na.needsUpdate = true; return; }
    if (!geo.userData.smoothN) {
      const P = pa.array, n = P.length / 9, F = new Float32Array(n * 3);
      for (let t = 0; t < n; t++) {
        const o = t * 9;
        const ux = P[o + 3] - P[o], uy = P[o + 4] - P[o + 1], uz = P[o + 5] - P[o + 2];
        const vx = P[o + 6] - P[o], vy = P[o + 7] - P[o + 1], vz = P[o + 8] - P[o + 2];
        let x = uy * vz - uz * vy, y = uz * vx - ux * vz, z = ux * vy - uy * vx;
        const l = Math.hypot(x, y, z) || 1; F[t * 3] = x / l; F[t * 3 + 1] = y / l; F[t * 3 + 2] = z / l;
      }
      const groups = new Map();
      for (let v = 0; v < n * 3; v++) {
        const k = Math.round(P[v * 3] * 20) + "," + Math.round(P[v * 3 + 1] * 20) + "," + Math.round(P[v * 3 + 2] * 20);
        const g = groups.get(k); if (g) g.push(v); else groups.set(k, [v]);
      }
      const N = new Float32Array(n * 9), cos = Math.cos(35 * Math.PI / 180);
      for (const g of groups.values()) {
        for (const v of g) {
          const f = (v / 3) | 0; let x = 0, y = 0, z = 0;
          for (const w of g) {
            const h = (w / 3) | 0;
            const d = F[f * 3] * F[h * 3] + F[f * 3 + 1] * F[h * 3 + 1] + F[f * 3 + 2] * F[h * 3 + 2];
            if (d >= cos) { x += F[h * 3]; y += F[h * 3 + 1]; z += F[h * 3 + 2]; }
          }
          const l = Math.hypot(x, y, z) || 1; N[v * 3] = x / l; N[v * 3 + 1] = y / l; N[v * 3 + 2] = z / l;
        }
      }
      geo.userData.flatN = na.array.slice();
      geo.userData.smoothN = N;
    }
    na.array.set(geo.userData.smoothN);
    geo.userData.creased = true;
    na.needsUpdate = true;
  }

  function tick(t) {
    if (!t.photo) return;
    t.root.traverse((o) => {
      if (o.isLineSegments) { if (o.visible) { o.userData.wasVisible = true; o.visible = false; } return; }
      if (!o.isMesh) return;
      if (!o.material.userData.photo) { o.userData.flat = o.material; o.material = physical(o.material); }
      linColors(o.geometry, true);
      creaseNormals(o.geometry, true);
      o.castShadow = true; o.receiveShadow = true;
    });
  }

  function fitStage(t) {
    const bb = new THREE.Box3();
    t.root.traverse((o) => { if (o.isMesh) bb.expandByObject(o); });   // sol sous le modèle entier, même aux premières étapes
    if (bb.isEmpty()) return;
    const c = bb.getCenter(new THREE.Vector3()), s = bb.getSize(new THREE.Vector3()), r = Math.max(s.x, s.y, s.z);
    const P = t.photo;
    P.ground.position.set(c.x, bb.min.y - 0.001, c.z);
    P.ground.scale.setScalar(r * 6);
    const L = P.key;
    L.position.copy(c).add(new THREE.Vector3(-0.9, 1.0, -0.5).multiplyScalar(r * 1.6));
    L.target.position.copy(c);
    const sc = L.shadow.camera;
    sc.left = sc.bottom = -r * 1.5; sc.right = sc.top = r * 1.5; sc.near = r * 0.1; sc.far = r * 6;
    sc.updateProjectionMatrix();
    L.shadow.radius = 4;
    if (P.ssao) P.ssao.kernelRadius = Math.max(0.3, Math.min(1.2, r * 0.05));
  }

  // fond studio (dégradé radial) en texture, pour que le post-traitement le garde
  function studioBackground() {
    const c = document.createElement("canvas"); c.width = c.height = 512;
    const g = c.getContext("2d"), gr = g.createRadialGradient(256, 180, 10, 256, 220, 420);
    gr.addColorStop(0, "#ffffff"); gr.addColorStop(0.55, "#f0f0f3"); gr.addColorStop(1, "#d6d6dc");
    g.fillStyle = gr; g.fillRect(0, 0, 512, 512);
    const tex = new THREE.CanvasTexture(c); tex.encoding = THREE.sRGBEncoding;
    return tex;
  }

  const GradeShader = {
    uniforms: { tDiffuse: { value: null }, saturation: { value: 1.18 }, contrast: { value: 1.08 } },
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: `uniform sampler2D tDiffuse; uniform float saturation, contrast; varying vec2 vUv;
      vec3 toSRGB(vec3 c){ return mix(c * 12.92, 1.055 * pow(max(c, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c)); }
      void main(){ vec4 c = texture2D(tDiffuse, vUv); vec3 s = toSRGB(c.rgb);
        float l = dot(s, vec3(0.2126, 0.7152, 0.0722)); s = mix(vec3(l), s, saturation); s = (s - 0.5) * contrast + 0.5;
        gl_FragColor = vec4(clamp(s, 0.0, 1.0), 1.0); }`,
  };

  function makeComposer(t) {
    const { renderer, scene, camera } = t;
    const size = renderer.getDrawingBufferSize(new THREE.Vector2());
    const comp = new THREE.EffectComposer(renderer, new THREE.WebGLRenderTarget(size.x, size.y, { type: THREE.HalfFloatType }));
    const ssao = new THREE.SSAOPass(scene, camera, size.x, size.y);
    ssao.kernelRadius = 0.9; ssao.minDistance = 0.00002; ssao.maxDistance = 0.006;
    ssao.beautyRenderTarget.texture.type = THREE.HalfFloatType;        // pas de bandes dans les ombres
    // le sol attrape-ombres ne participe pas à l'occlusion (artefacts en escalier sur un grand plan)
    const ov = ssao.overrideVisibility.bind(ssao), rv = ssao.restoreVisibility.bind(ssao);
    ssao.overrideVisibility = () => { ov(); t.photo.ground.visible = false; };
    ssao.restoreVisibility = () => { rv(); t.photo.ground.visible = true; };
    comp.addPass(ssao);
    comp.addPass(new THREE.ShaderPass(GradeShader));
    const fxaa = new THREE.ShaderPass(THREE.FXAAShader);
    comp.addPass(fxaa);
    t.photo.ssao = ssao; t.photo.fxaa = fxaa; t.photo.size = [0, 0];
    return comp;
  }

  function render(t) {
    const P = t.photo;
    if (!P || !P.composer) { t.renderer.render(t.scene, t.camera); return; }
    const s = t.renderer.getDrawingBufferSize(new THREE.Vector2());
    if (s.x !== P.size[0] || s.y !== P.size[1]) {
      const pr = t.renderer.getPixelRatio();
      P.composer.setPixelRatio(pr);
      P.composer.setSize(s.x / pr, s.y / pr);
      P.fxaa.material.uniforms.resolution.value.set(1 / s.x, 1 / s.y);
      P.size = [s.x, s.y];
    }
    P.composer.render();
  }

  async function set(t, on) {
    const { renderer, scene } = t;
    if (on === !!t.photo) return;
    if (on) {
      let post = true;
      try { await loadPost(); } catch (e) { post = false; console.warn("post-traitement indisponible", e); }
      const ground = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.ShadowMaterial({ opacity: 0.38 }));
      ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true;
      const key = new THREE.DirectionalLight(0xffffff, 2.8);
      key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0004; key.shadow.normalBias = 0.02;
      scene.add(ground, key, key.target);
      const dimmed = [];
      scene.traverse((o) => { if (o.isLight && o !== key) { dimmed.push([o, o.intensity]); o.intensity = 0; } });
      t.photo = { ground, key, dimmed, grid: t.grid ? t.grid.visible : null, bg: scene.background };
      if (t.grid) t.grid.visible = false;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 0.8;
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      scene.environment = env(renderer);
      t.box.classList.add("photo-stage");
      if (post) {
        renderer.outputEncoding = THREE.LinearEncoding;          // la conversion sRGB est faite par l'étalonnage
        scene.background = studioBackground();
        t.photo.composer = makeComposer(t);
      } else {
        renderer.outputEncoding = THREE.sRGBEncoding;
      }
      tick(t); fitStage(t);
      t.photo.fit = setInterval(() => t.photo && fitStage(t), 1000);   // suit les étapes de notice et les éditions
    } else {
      const P = t.photo;
      clearInterval(P.fit);
      scene.remove(P.ground, P.key, P.key.target);
      P.dimmed.forEach(([o, i]) => (o.intensity = i));
      if (t.grid && P.grid != null) t.grid.visible = P.grid;
      if (P.composer) { P.composer.passes.forEach((p) => p.dispose && p.dispose()); }
      scene.background = P.bg || null;
      t.photo = null;
      t.root.traverse((o) => {
        if (o.isLineSegments && o.userData.wasVisible) { o.visible = true; delete o.userData.wasVisible; }
        if (o.isMesh) {
          if (o.material.userData.photo && o.userData.flat) o.material = o.userData.flat;
          linColors(o.geometry, false);
          creaseNormals(o.geometry, false);
          o.castShadow = o.receiveShadow = false;
        }
      });
      renderer.outputEncoding = THREE.LinearEncoding;
      renderer.toneMapping = THREE.NoToneMapping;
      renderer.shadowMap.enabled = false;
      scene.environment = null;
      scene.traverse((o) => { if (o.material) [].concat(o.material).forEach((m) => (m.needsUpdate = true)); });
      t.box.classList.remove("photo-stage");
    }
  }

  function snapshot(t, name) {
    render(t);
    const a = document.createElement("a");
    a.href = t.renderer.domElement.toDataURL("image/png");
    a.download = (name || "rendu") + ".png";
    a.click();
  }

  // bouton « Rendu » : moteur WebGPU temps réel (realtime.mjs) si getCtx est fourni, sinon l'ancien mode (WebGL 1, three r128)
  function button(getThree, onChange, getCtx) {
    const t0 = getThree();
    const b = document.createElement("button");
    b.className = "tool photo-btn"; b.type = "button"; b.textContent = "Rendu";
    b.title = "Rendu réaliste temps réel : éclairage global, reflets, ombres douces (WebGPU)";
    b.setAttribute("aria-pressed", String(!!(t0 && t0.photo)));
    b.addEventListener("click", async () => {
      const t = getThree(); if (!t) return;
      const ctx = getCtx && getCtx();
      if (ctx) {
        if (b.getAttribute("aria-pressed") === "true") { t.box.querySelector(".rt-overlay .btn:last-child")?.click(); return; }
        b.setAttribute("aria-pressed", "true");
        try {
          const m = await import("/static/realtime.mjs?v=6");
          await m.open(ctx, () => b.setAttribute("aria-pressed", "false"));
        } catch (e) {               // moteur indisponible : ancien mode
          console.warn("rendu WebGPU indisponible", e);
          await set(t, true);
        }
        return;
      }
      b.disabled = true;
      await set(t, !t.photo);
      b.disabled = false;
      b.setAttribute("aria-pressed", String(!!t.photo));
      onChange && onChange(!!t.photo);
    });
    return b;
  }

  // ---------------------------------------------------------------- rendu photoréaliste (Blender Cycles, côté serveur)
  // getCtx() → { three, parts: [{part, color, m}], name }
  function hdButton(getCtx) {
    const wrap = document.createElement("span");
    wrap.className = "seg";
    const sel = document.createElement("select");
    sel.className = "hd-q"; sel.title = "Qualité du rendu Cycles";
    sel.innerHTML = '<option value="apercu">Aperçu</option><option value="hd">HD</option>';
    const b = document.createElement("button");
    b.className = "tool hd-btn"; b.type = "button"; b.textContent = "Rendu HD";
    b.title = "Rendu photoréaliste avec Blender Cycles : arêtes biseautées, plastique, softbox, ombres";
    b.addEventListener("click", () => { const c = getCtx(); if (c) hdRender(c, sel.value); });
    const live = document.createElement("button");
    live.className = "tool pt-btn"; live.type = "button"; live.textContent = "Cycles temps réel";
    live.title = "Lancer de rayons progressif dans le navigateur : l'image se précise tant qu'on ne bouge pas";
    live.addEventListener("click", async () => {
      const c = getCtx(); if (!c) return;
      const m = await import("/static/pathtrace.mjs?v=3");
      m.open(c);
    });
    wrap.append(live, b, sel);
    return wrap;
  }

  async function hdRender(ctx, quality) {
    const t = ctx.three, cam = t.camera, tgt = t.controls.target;
    const box = t.box;
    box.querySelector(".hd-overlay")?.remove();
    const ov = document.createElement("div");
    ov.className = "hd-overlay";
    ov.innerHTML = '<div class="hd-card"><b>Rendu Cycles</b><div class="hd-bar"><i></i></div><small class="hd-msg">Envoi de la scène…</small><button class="btn small hd-cancel">Fermer</button></div>';
    box.append(ov);
    ov.querySelector(".hd-cancel").onclick = () => ov.remove();
    const msg = ov.querySelector(".hd-msg"), bar = ov.querySelector(".hd-bar i");
    try {
      let st = await api("/api/render", { method: "POST", body: JSON.stringify({
        parts: ctx.parts, name: ctx.name, quality,
        camera: { pos: cam.position.toArray(), target: tgt.toArray(), fov: cam.fov, aspect: cam.aspect } }) });
      const id = st.id;
      while (st.state !== "terminé" && st.state !== "erreur" && ov.isConnected) {
        msg.textContent = st.state === "attente" ? "En file d'attente…" : st.progress > 0
          ? `Lancer de rayons… ${Math.round(st.progress * 100)} %` + (st.remaining != null ? ` · ~${st.remaining} s` : "") : `${st.stage || "Préparation"}… (${st.parts} pièces)`;
        bar.style.width = Math.round((st.progress || 0) * 100) + "%";
        await new Promise((r) => setTimeout(r, 800));
        st = await api(`/api/render/${id}`);
      }
      if (!ov.isConnected) return;
      if (st.state === "erreur") { msg.textContent = "Échec du rendu : " + (st.error || "").slice(-300); return; }
      ov.classList.add("done");
      ov.innerHTML = "";
      const img = new Image(); img.src = st.url; img.alt = "Rendu photoréaliste";
      const bar2 = document.createElement("div"); bar2.className = "hd-actions";
      const save = document.createElement("a"); save.className = "btn small"; save.textContent = "Enregistrer (PNG)";
      save.href = st.url; save.download = (ctx.name || "rendu") + ".png";
      const close = document.createElement("button"); close.className = "btn small"; close.textContent = "Retour à la 3D";
      close.onclick = () => ov.remove();
      const info = document.createElement("small"); info.textContent = st.seconds ? `Cycles · ${st.seconds} s` : "Cycles";
      bar2.append(info, save, close);
      ov.append(img, bar2);
    } catch (e) { msg.textContent = "Erreur : " + e.message; }
  }

  return { set, tick, render, snapshot, button, hdButton };
})();
