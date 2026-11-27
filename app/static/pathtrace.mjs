// Brick Forge Lab — « Cycles temps réel » : traceur de chemins GPU dans le navigateur (three-gpu-pathtracer).
// L'image se précise à chaque passe tant qu'on ne bouge pas ; elle repart quand on tourne la caméra.
// Les pièces biseautées et leurs matériaux viennent de Blender (glTF exporté par brickforge/blender_render.py).
//
//   const { open } = await import("/static/pathtrace.mjs");  open({ three, parts, name })

const V = "0.187.0";
const ESM = "https://esm.sh/";
let mods = null;
async function load() {
  if (!mods) {
    mods = Promise.all([
      import(`${ESM}three@${V}`),
      import(`${ESM}three@${V}/examples/jsm/loaders/GLTFLoader.js`),
      import(`${ESM}three@${V}/examples/jsm/controls/OrbitControls.js`),
      import(`${ESM}three-gpu-pathtracer@0.0.28?deps=three@${V}`),
    ]).then(([T, G, O, P]) => ({ T, GLTFLoader: G.GLTFLoader, OrbitControls: O.OrbitControls, PT: P }));
  }
  return mods;
}

const MAX_SAMPLES = 2000;

export async function open(ctx) {
  const box = ctx.three.box;
  box.querySelector(".hd-overlay")?.remove();
  const ov = document.createElement("div");
  ov.className = "hd-overlay pt-overlay";
  ov.innerHTML = `<div class="hd-card"><b>Cycles temps réel</b><div class="hd-bar"><i style="width:15%"></i></div>
    <small class="hd-msg">Préparation des pièces biseautées (Blender)…</small><button class="btn small hd-cancel">Fermer</button></div>`;
  box.append(ov);
  let closed = false, cleanup = () => {};
  const close = () => { closed = true; cleanup(); ov.remove(); };
  ov.querySelector(".hd-cancel").onclick = close;
  const msg = ov.querySelector(".hd-msg"), bar = ov.querySelector(".hd-bar i");
  try {
    const [glb, M] = await Promise.all([
      fetch("/api/scene-glb", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ parts: ctx.parts, name: ctx.name }) })
        .then(async (r) => { if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText); return r.json(); }),
      load(),
    ]);
    if (closed) return;
    msg.textContent = `Chargement du modèle (${(glb.bytes / 1e6).toFixed(1)} Mo)…`; bar.style.width = "45%";
    const { T, GLTFLoader, OrbitControls, PT } = M;
    const gltf = await new GLTFLoader().loadAsync(glb.url);
    if (closed) return;

    // ---------------------------------------------------------------- scène
    const scene = new T.Scene();
    const model = gltf.scene;
    model.traverse((o) => { if (o.isMesh) { o.material.side = T.DoubleSide; } });
    scene.add(model);
    const bb = new T.Box3().setFromObject(model), ctr = bb.getCenter(new T.Vector3()), size = bb.getSize(new T.Vector3());
    const r = Math.max(size.x, size.y, size.z);
    // sol studio blanc (reçoit ombres et lumière rebondie)
    const floor = new T.Mesh(new T.PlaneGeometry(r * 40, r * 40), new T.MeshStandardMaterial({ color: 0xf4f4f6, roughness: 0.85 }));
    floor.rotation.x = -Math.PI / 2; floor.position.set(ctr.x, bb.min.y - 0.002, ctr.z);
    scene.add(floor);
    // ciel de studio : dégradé doux, sert de fond et d'éclairage d'ambiance
    const sky = new PT.GradientEquirectTexture();
    sky.topColor.set(0xffffff); sky.bottomColor.set(0xd9d9de); sky.exponent = 1.5; sky.update();
    scene.background = sky; scene.environment = sky; scene.environmentIntensity = 0.45; scene.backgroundIntensity = 1;

    // caméra : celle de la vue 3D
    const c0 = ctx.three.camera, t0 = ctx.three.controls.target;
    const camera = new T.PerspectiveCamera(c0.fov, c0.aspect, r / 500, r * 100);
    camera.position.set(...c0.position.toArray());

    // softbox (lumières de surface), placées par rapport à la caméra comme dans le rendu Blender
    const view = camera.position.clone().sub(ctr).normalize(), up = new T.Vector3(0, 1, 0), side = new T.Vector3().crossVectors(view, up).normalize();
    const softbox = (intensity, s, d, col = 0xffffff) => {
      const l = new T.RectAreaLight(col, intensity, s * r, s * r);
      const dir = view.clone().multiplyScalar(d[0]).add(side.clone().multiplyScalar(d[1])).add(up.clone().multiplyScalar(d[2])).normalize();
      l.position.copy(ctr).addScaledVector(dir, r * 2.2);
      l.lookAt(ctr);
      scene.add(l);
    };
    softbox(9, 1.2, [0.6, 0.7, 1.0]);            // principale
    softbox(2.5, 1.6, [0.8, -1.0, 0.25], 0xf2f5ff); // remplissage
    softbox(7, 0.8, [-1.0, 0.3, 0.9]);           // contre-jour
    softbox(3, 2.0, [0, 0, 1]);                  // dessus

    // ---------------------------------------------------------------- rendu
    const renderer = new T.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    renderer.toneMapping = T.AgXToneMapping;
    renderer.toneMappingExposure = 0.85;
    const canvas = renderer.domElement; canvas.className = "pt-canvas";
    const controls = new OrbitControls(camera, canvas);
    controls.target.set(...t0.toArray()); controls.enableDamping = false; controls.update();   // sans inertie : l’affinage reprend dès qu’on lâche
    controls.mouseButtons = { LEFT: T.MOUSE.ROTATE, MIDDLE: T.MOUSE.DOLLY, RIGHT: T.MOUSE.PAN };

    const pt = new PT.WebGLPathTracer(renderer);
    pt.bounces = 6; pt.transmissiveBounces = 8; pt.filterGlossyFactor = 0.5;
    pt.minSamples = 1; pt.renderDelay = 0; pt.fadeDuration = 250;
    pt.dynamicLowRes = true; pt.lowResScale = 0.35; pt.tiles.set(2, 2);
    msg.textContent = "Construction de la hiérarchie de rayons (BVH)…"; bar.style.width = "70%";
    await new Promise((res) => setTimeout(res, 30));
    pt.setScene(scene, camera);
    if (closed) { renderer.dispose(); return; }

    ov.innerHTML = "";
    ov.classList.add("done");
    const hud = document.createElement("div"); hud.className = "hd-actions pt-hud";
    const info = document.createElement("small");
    const save = document.createElement("button"); save.className = "btn small"; save.textContent = "Enregistrer (PNG)";
    const back = document.createElement("button"); back.className = "btn small"; back.textContent = "Retour à la 3D";
    hud.append(info, save, back);
    ov.append(canvas, hud);
    back.onclick = close;
    save.onclick = () => { const a = document.createElement("a"); a.href = canvas.toDataURL("image/png"); a.download = (ctx.name || "rendu") + "-cycles.png"; a.click(); };

    const resize = () => {
      const w = ov.clientWidth, h = ov.clientHeight; if (!w || !h) return;
      renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); pt.updateCamera();
    };
    const ro = new ResizeObserver(resize); ro.observe(ov); resize();
    controls.addEventListener("change", () => pt.updateCamera());

    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      controls.update();
      if (pt.samples < MAX_SAMPLES) pt.renderSample();
      const s = Math.floor(pt.samples);
      info.textContent = s >= MAX_SAMPLES ? `Cycles temps réel · ${s} passes · terminé` : `Cycles temps réel · ${s} passe${s > 1 ? "s" : ""}`;
    };
    loop();
    cleanup = () => {
      cancelAnimationFrame(raf); ro.disconnect(); controls.dispose();
      pt.dispose(); renderer.dispose(); renderer.forceContextLoss();
    };
  } catch (e) {
    console.error(e);
    msg.textContent = "Erreur : " + e.message;
  }
}
