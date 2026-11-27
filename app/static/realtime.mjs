// Brick Forge Lab — « Rendu » temps réel en WebGPU (three.js r187, nœuds TSL), 60 images/s, presque photoréaliste :
//   - pièces biseautées et matériaux plastique exportés par Blender (même glTF que « Cycles temps réel ») ;
//   - éclairage global à l'écran (SSGI) : lumière qui rebondit entre les pièces + occlusion ambiante ;
//   - reflets à l'écran (SSR) sur le plastique verni ;
//   - ombres douces d'une lumière principale, environnement de studio (RoomEnvironment) ;
//   - anticrénelage temporel (TRAA), tone mapping AgX.
// Repli automatique sur WebGL 2 si le navigateur n'a pas WebGPU.
//
//   const { open } = await import("/static/realtime.mjs");  open({ three, parts, name })

const V = "0.187.0";
const ESM = "https://esm.sh/";
let mods = null;
const load = () => mods || (mods = Promise.all([
  import(`${ESM}three@${V}/webgpu`),
  import(`${ESM}three@${V}/tsl`),
  import(`${ESM}three@${V}/examples/jsm/tsl/display/SSGINode.js`),
  import(`${ESM}three@${V}/examples/jsm/tsl/display/SSRNode.js`),
  import(`${ESM}three@${V}/examples/jsm/tsl/display/TRAANode.js`),
  import(`${ESM}three@${V}/examples/jsm/loaders/GLTFLoader.js`),
  import(`${ESM}three@${V}/examples/jsm/controls/OrbitControls.js`),
  import(`${ESM}three@${V}/examples/jsm/environments/RoomEnvironment.js`),
]).then(([T, L, G, R, A, GL, O, E]) => ({ T, L, ssgi: G.ssgi, ssr: R.ssr, traa: A.traa, GLTFLoader: GL.GLTFLoader, OrbitControls: O.OrbitControls, RoomEnvironment: E.RoomEnvironment })));

export function preload() { return load(); }

export async function open(ctx, onClose) {
  const box = ctx.three.box;
  box.querySelector(".hd-overlay")?.remove();
  const ov = document.createElement("div");
  ov.className = "hd-overlay rt-overlay";
  ov.innerHTML = `<div class="hd-card"><b>Rendu temps réel</b><div class="hd-bar"><i style="width:15%"></i></div>
    <small class="hd-msg">Préparation des pièces biseautées…</small><button class="btn small hd-cancel">Fermer</button></div>`;
  box.append(ov);
  let closed = false, cleanup = () => {};
  const close = () => { if (closed) return; closed = true; cleanup(); ov.remove(); onClose && onClose(); };
  ov.querySelector(".hd-cancel").onclick = close;
  const msg = ov.querySelector(".hd-msg"), bar = ov.querySelector(".hd-bar i");
  try {
    const [glb, M] = await Promise.all([
      fetch("/api/scene-glb", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ parts: ctx.parts, name: ctx.name }) })
        .then(async (r) => { if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText); return r.json(); }),
      load(),
    ]);
    if (closed) return;
    const { T, L, ssgi, ssr, traa, GLTFLoader, OrbitControls, RoomEnvironment } = M;
    msg.textContent = `Chargement du modèle (${(glb.bytes / 1e6).toFixed(1)} Mo)…`; bar.style.width = "45%";
    const gltf = await new GLTFLoader().loadAsync(glb.url);
    if (closed) return;

    // ---------------------------------------------------------------- moteur
    // les 5 tampons du rendu (couleur, diffus, normales, vitesse, métal/rugosité) dépassent la limite WebGPU par défaut (32 o/pixel)
    let mrBytes = 0;
    try { mrBytes = (await navigator.gpu?.requestAdapter())?.limits.maxColorAttachmentBytesPerSample || 0; } catch (e) { mrBytes = 0; }
    const fullMRT = mrBytes >= 48 || !navigator.gpu;            // WebGL 2 : pas cette limite
    const renderer = new T.WebGPURenderer(fullMRT && navigator.gpu ? { antialias: false, requiredLimits: { maxColorAttachmentBytesPerSample: Math.min(mrBytes, 128) } } : { antialias: false });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.25));
    renderer.toneMapping = T.AgXToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = T.PCFSoftShadowMap;
    await renderer.init();
    const backend = renderer.backend.isWebGPUBackend ? "WebGPU" : "WebGL 2";

    // ---------------------------------------------------------------- scène
    const scene = new T.Scene();
    const model = gltf.scene;
    model.traverse((o) => { if (o.isMesh) { o.castShadow = o.receiveShadow = true; o.material.side = T.DoubleSide; } });
    scene.add(model);
    const bb = new T.Box3().setFromObject(model), ctr = bb.getCenter(new T.Vector3()), size = bb.getSize(new T.Vector3());
    const r = Math.max(size.x, size.y, size.z);

    // fond de studio (dégradé radial) et sol qui ne montre que l'ombre
    // valeurs > 1 : le tone mapping AgX assombrit le blanc, on compense pour un fond studio vraiment clair
    scene.backgroundNode = L.screenUV.distance(L.vec2(0.5, 0.38)).mul(1.6).clamp(0, 1).mix(L.vec3(1.9, 1.9, 1.9), L.vec3(1.05, 1.05, 1.1));
    const floor = new T.Mesh(new T.PlaneGeometry(r * 30, r * 30), new T.ShadowNodeMaterial({ opacity: 0.32 }));
    floor.rotation.x = -Math.PI / 2; floor.position.set(ctr.x, bb.min.y - 0.002, ctr.z); floor.receiveShadow = true;
    scene.add(floor);

    const pm = new T.PMREMGenerator(renderer);
    scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environmentIntensity = 0.75;
    pm.dispose();

    const c0 = ctx.three.camera, t0 = ctx.three.controls.target;
    const camera = new T.PerspectiveCamera(c0.fov, c0.aspect, r / 200, r * 60);
    camera.position.set(...c0.position.toArray());

    // lumière principale (ombres douces), placée en haut à gauche de la caméra
    const view = camera.position.clone().sub(ctr).setY(0).normalize(), side = new T.Vector3().crossVectors(new T.Vector3(0, 1, 0), view).normalize();
    const key = new T.DirectionalLight(0xffffff, 2.6);
    key.position.copy(ctr).addScaledVector(view, r * 0.9).addScaledVector(side, -r * 1.2).add(new T.Vector3(0, r * 1.8, 0));
    key.target.position.copy(ctr);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.radius = 6; key.shadow.bias = -0.0005; key.shadow.normalBias = 0.02;
    Object.assign(key.shadow.camera, { left: -r * 1.4, right: r * 1.4, top: r * 1.4, bottom: -r * 1.4, near: r * 0.1, far: r * 6 });
    scene.add(key, key.target);
    const rim = new T.DirectionalLight(0xf4f6ff, 0.9);
    rim.position.copy(ctr).addScaledVector(view, -r * 2).add(new T.Vector3(0, r * 1.2, 0));
    scene.add(rim);

    // ---------------------------------------------------------------- post-traitement : SSGI + SSR + TRAA
    const pipe = new T.RenderPipeline(renderer);
    const scenePass = L.pass(scene, camera);
    const targets = { output: L.output, diffuseColor: L.diffuseColor, normal: L.packNormalToRGB(L.normalView), velocity: L.velocity };
    if (fullMRT) targets.metalrough = L.vec2(L.metalness, L.roughness);
    scenePass.setMRT(L.mrt(targets));
    const color = scenePass.getTextureNode("output");
    const diffuse = scenePass.getTextureNode("diffuseColor");
    const depth = scenePass.getTextureNode("depth");
    const normalTex = scenePass.getTextureNode("normal");
    const vel = scenePass.getTextureNode("velocity");
    const mr = fullMRT ? scenePass.getTextureNode("metalrough") : null;
    for (const k of fullMRT ? ["diffuseColor", "normal", "metalrough"] : ["diffuseColor", "normal"]) scenePass.getTexture(k).type = T.UnsignedByteType;
    const normal = L.sample((uv) => L.unpackRGBToNormal(normalTex.sample(uv)));

    const gi = ssgi(color, depth, normal, camera);
    gi.sliceCount.value = 2; gi.stepCount.value = 8;
    const ao = gi.getAONode(), giRGB = gi.getGINode();
    const lit = L.vec4(L.add(color.rgb.mul(ao), diffuse.rgb.mul(giRGB.rgb)), color.a);

    const refl = ssr(color, depth, normal, { metalnessNode: mr ? mr.r : L.float(0), roughnessNode: mr ? mr.g : L.float(0.22), camera });
    refl.maxDistance.value = r * 0.5; refl.thickness.value = 0.3; refl.intensity.value = 0.6;
    const composed = lit.add(refl.rgb);
    pipe.outputNode = traa(composed, depth, vel, camera);

    // ---------------------------------------------------------------- affichage
    ov.innerHTML = "";
    ov.classList.add("done");
    const canvas = renderer.domElement; canvas.className = "pt-canvas";
    const hud = document.createElement("div"); hud.className = "hd-actions pt-hud";
    const info = document.createElement("small");
    const save = document.createElement("button"); save.className = "btn small"; save.textContent = "Photo";
    const back = document.createElement("button"); back.className = "btn small"; back.textContent = "Retour à la 3D";
    hud.append(info, save, back);
    ov.append(canvas, hud);
    back.onclick = close;
    save.onclick = async () => {
      await pipe.renderAsync();
      const a = document.createElement("a"); a.href = canvas.toDataURL("image/png"); a.download = (ctx.name || "rendu") + ".png"; a.click();
    };

    const controls = new OrbitControls(camera, canvas);
    controls.target.set(...t0.toArray()); controls.enableDamping = true; controls.update();
    controls.mouseButtons = { LEFT: T.MOUSE.ROTATE, MIDDLE: T.MOUSE.DOLLY, RIGHT: T.MOUSE.PAN };

    const resize = () => { const w = ov.clientWidth, h = ov.clientHeight; if (!w || !h) return; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); };
    const ro = new ResizeObserver(resize); ro.observe(ov); resize();

    let frames = 0, t = performance.now(), fps = 0;
    renderer.setAnimationLoop(() => {
      controls.update();
      pipe.render();
      frames++;
      const now = performance.now();
      if (now - t > 1000) { fps = Math.round(frames * 1000 / (now - t)); frames = 0; t = now; info.textContent = `${backend} · ${fps} img/s · SSGI + SSR + TRAA`; }
    });
    cleanup = () => { renderer.setAnimationLoop(null); ro.disconnect(); controls.dispose(); pipe.dispose && pipe.dispose(); renderer.dispose(); };
  } catch (e) {
    console.error(e);
    msg.textContent = "Erreur : " + e.message;
  }
}
