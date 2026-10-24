// CAD Roam's 3D view: the sky and the ground, the model in its place (things.js) in its colours
// and with its glass (look.js), you walking or flying (player.js), the others there (people.js)
// and what is drawn over it all (hud.js).
//
// The place comes from GET /_roam/world/<owner>/<item> (cad_roam/models.py) and is fetched again
// whenever the server says it changed (the model rebuilt in Codoc in CAD, a size someone chose);
// a rebuilt model swaps in its new mesh once it has loaded, so you can stay inside it.
// Everything is metres, Y up.
//
// The page (world.jsx) passes commands in ({type: "goto" | "follow" | "mode" | "reload" |
// "release" | "rejoined", ...}) and hears back through onEvent ({type: "ready" | "select" |
// "rejoin" | "world" | "gone" | "mode" | "error", ...}). window.__roam is this engine, for tests.

import * as THREE from "three";
import { acceleratedRaycast } from "three-mesh-bvh";
import { Sky } from "three/addons/objects/Sky.js";
import { CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";
import { Hud } from "./hud.js";
import { Input } from "./input.js";
import { Look } from "./look.js";
import { People } from "./people.js";
import { FLY, Player, WALK } from "./player.js";
import { BYTES_PER_TRIANGLE, Thing, needsRebuild } from "./things.js";

THREE.Mesh.prototype.raycast = acceleratedRaycast;

// A model with more triangles than the server's limit (its "big", cad_roam/models.py) loads only
// once the person said so. Asked once in a page: model key -> true (load it, and its later builds)
// or false (leave its outline, with a button to load it after all).
const BIG = new Map();

// The sun crosses the sky along its path on a day in spring or autumn (an equinox) at 41° N,
// Barcelona's: up in the east at 6:00, highest (49°) in the south at noon, down in the west at
// 18:00 (solar time; +X is the east, -Z the north). Its time is dragged in the HUD, or T jumps to
// the morning, the day and the evening. 10:30 is the sun CAD Roam always had: behind people
// arriving (the south) and a little to the east, so fronts are lit. A browser keeps the time it was
// left at.
const LATITUDE = THREE.MathUtils.degToRad(41.4);
const SUN_TIMES = { first: 6.5, last: 17.5 };
const TIMES = [7.5, 10.5, 16.5];
const DAYTIME = 10.5;
const SUN_KEY = "cad_roam_sun_time";
const LOW_SUN = new THREE.Color(0xffd2a6);
const HIGH_SUN = new THREE.Color(0xfff2df);

// Where the sun is at a time of the day (hours): its compass bearing and height, in degrees.
export function sunAt(hours) {
  const h = THREE.MathUtils.degToRad(15 * (hours - 12));
  const elevation = Math.asin(Math.cos(LATITUDE) * Math.cos(h));
  const bearing = Math.atan2(Math.sin(h), Math.cos(h) * Math.sin(LATITUDE)) + Math.PI;
  return { bearing: THREE.MathUtils.radToDeg(bearing), elevation: THREE.MathUtils.radToDeg(elevation) };
}

function savedTime() {
  try {
    const t = parseFloat(localStorage.getItem(SUN_KEY));
    return Number.isFinite(t) ? t : DAYTIME;
  } catch (e) {
    return DAYTIME;
  }
}

const LOADS_AT_ONCE = 2;

function grassTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const g = c.getContext("2d");
  g.fillStyle = "#7f9f5f";
  g.fillRect(0, 0, 256, 256);
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < 2600; i++) {
    const v = 110 + Math.floor(rnd() * 60);
    g.fillStyle = `rgba(${v - 30},${v + 20},${v - 50},${0.25 + rnd() * 0.3})`;
    g.fillRect(rnd() * 256, rnd() * 256, 1 + rnd() * 3, 1 + rnd() * 3);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(1200, 1200);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

export class Engine {
  constructor(container, opts) {
    this.container = container;
    this.opts = opts; // {backend, model: "<owner>/<item>", me, spawn, labels, quality, onEvent}
    this.backend = opts.backend || window.location.origin;
    this.model = opts.model;
    this.path = this.model.split("/").map(encodeURIComponent).join("/");
    this.labels = opts.labels || {};
    this.things = new Map();
    this.replacing = new Map(); // key -> the old thing, shown until its new mesh has loaded
    this.rev = 0;
    this.ready = false;
    this.selected = "";
    this.light = false;
    this.quality = opts.quality || "high";
    this.peopleList = [];
    this._spawned = false;
    this._tween = null;
    this._last = performance.now();
    this._t = 0;
    this._slow = 0;
    this._fps = 0;
    this._frames = 0;

    this._setupRenderer();
    this._setupScene();
    this.player = new Player();
    this.input = new Input(this.surface, (a, d) => this._action(a, d));
    this.hud = new Hud(this.surface, {
      labels: this.labels,
      touch: this.input.touch,
      onMode: (m) => this.setMode(m),
      onFollow: (id) => this.follow(id),
      onStick: (x, y, id) => this.input.setStick(x, y, id),
      onRise: (v) => { this.input.touchRise = v; },
      onAction: (a, d) => this._action(a, d),
      sunTimes: SUN_TIMES,
      onSunTime: (t) => this.setTime(t),
    });
    this.hud.setSunTime(this.time);
    this.hud.setMode(this.player.mode, false, false);
    this.hud.showHelp(true);
    this.hud.showKeys(true);
    this.people = new People({
      scene: this.scene,
      wsUrl: this.url(`/_roam/ws/${this.path}`).replace(/^http/, "ws"),
      peer: (opts.me || {}).peer,
      onRejoin: () => this._emit({ type: "rejoin" }),
      onWorld: (rev) => { if (rev !== this.rev) this.reload(); },
      onWelcome: (rev) => { if (rev && this.ready && rev !== this.rev) this.reload(); },
      onChange: (list) => {
        this.peopleList = list;
        this.hud.setPeople(list, (this.opts.me || {}).peer);
      },
    });
    this._resize = new ResizeObserver(() => this.resize());
    this._resize.observe(container);
    this.resize();
    this.reload();
    this._loop = this._loop.bind(this);
    this._raf = requestAnimationFrame(this._loop);
    window.__roam = this;
  }

  url(path) {
    return new URL(path, this.backend).toString();
  }

  _emit(e) {
    try {
      if (this.opts.onEvent) this.opts.onEvent(e);
    } catch (err) {
      console.warn("Roam:", err);
    }
  }

  // ------------------------------------------------------------------ setup

  _setupRenderer() {
    this.surface = document.createElement("div");
    this.surface.className = "rm-surface";
    this.surface.tabIndex = 0;
    this.container.appendChild(this.surface);
    const r = new THREE.WebGLRenderer({ antialias: this.quality !== "low", logarithmicDepthBuffer: true, powerPreference: "high-performance" });
    r.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.quality === "low" ? 1 : 1.75));
    r.outputColorSpace = THREE.SRGBColorSpace;
    r.toneMapping = THREE.ACESFilmicToneMapping;
    r.toneMappingExposure = 0.72;
    r.shadowMap.enabled = this.quality !== "low";
    r.shadowMap.type = THREE.PCFShadowMap;
    this.renderer = r;
    this.surface.appendChild(r.domElement);
    r.domElement.className = "rm-canvas";
    this.labelsRenderer = new CSS2DRenderer();
    this.labelsRenderer.domElement.className = "rm-labels";
    this.surface.appendChild(this.labelsRenderer.domElement);
  }

  _setupScene() {
    const scene = new THREE.Scene();
    this.scene = scene;
    this.camera = new THREE.PerspectiveCamera(72, 1, 0.05, 30000);
    this.camera.rotation.order = "YXZ";
    this.listener = new THREE.AudioListener();
    this.camera.add(this.listener);
    scene.add(this.camera);

    const sky = new Sky();
    this.sky = sky;
    sky.scale.setScalar(25000);
    const u = sky.material.uniforms;
    u.turbidity.value = 3.2;
    u.rayleigh.value = 1.4;
    u.mieCoefficient.value = 0.004;
    u.mieDirectionalG.value = 0.8;
    scene.add(sky);
    scene.fog = new THREE.Fog(0xc7d6e6, 900, 9000);

    // Sky light from above, a warm grey from below (not the grass' green: insides would turn
    // green), and a little everywhere, so rooms the sun doesn't reach are still readable.
    this.skyLight = new THREE.HemisphereLight(0xdbe8ff, 0x8d8579, 1.15);
    this.fillLight = new THREE.AmbientLight(0xffffff, 0.35);
    scene.add(this.skyLight, this.fillLight);
    const sun = new THREE.DirectionalLight(0xfff2df, 2.6);
    sun.castShadow = this.quality !== "low";
    sun.shadow.mapSize.set(this.quality === "high" ? 4096 : 2048, this.quality === "high" ? 4096 : 2048);
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 0.06;
    this.sun = sun;
    this.sunDir = new THREE.Vector3();
    this.setTime(savedTime());
    this._shadowRange(120);
    scene.add(sun, sun.target);
    // Models' colours and glass, and the sunlight through glass (look.js).
    this.look = new Look(this.renderer, scene, sun);

    // In 400 m squares: drawn in software, one 40 km triangle loses so much depth that the grass
    // came through floors 8 cm above it.
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(40000, 40000, 100, 100),
      this.look.receive(new THREE.MeshStandardMaterial({ map: grassTexture(), roughness: 1, metalness: 0 })),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.03;
    ground.receiveShadow = true;
    scene.add(ground);
    this.ground = ground;

    // A torch for dark insides (L).
    const torch = new THREE.SpotLight(0xfff6e5, 0, 60, Math.PI / 6, 0.45, 1.2);
    torch.position.set(0, 0, 0.1);
    torch.target.position.set(0, 0, -1);
    this.camera.add(torch, torch.target);
    this.torch = torch;
  }

  // The sun at a time of the day (hours): low (under 20°), it is warmer and the sky gives less light.
  setTime(hours) {
    const t = THREE.MathUtils.clamp(Math.round((Number(hours) || DAYTIME) * 60) / 60, SUN_TIMES.first, SUN_TIMES.last);
    const { bearing, elevation } = sunAt(t);
    const k = THREE.MathUtils.smoothstep(elevation, 2, 20);
    this.time = t;
    this.setSun(bearing, elevation);
    this.sun.color.lerpColors(LOW_SUN, HIGH_SUN, k);
    this.sun.intensity = 1.9 + 0.7 * k;
    this.skyLight.intensity = 1.15 * (0.7 + 0.3 * k);
    this.fillLight.intensity = 0.35 * (0.7 + 0.3 * k);
    if (this.hud) this.hud.setSunTime(t);
    try {
      localStorage.setItem(SUN_KEY, String(t));
    } catch (e) {
      // A browser that keeps nothing starts at 10:30 again.
    }
  }

  // Where the sun is: its compass bearing (90 = east) and its height above the horizon, in degrees.
  setSun(bearing, elevation) {
    const b = THREE.MathUtils.degToRad(bearing), e = THREE.MathUtils.degToRad(elevation);
    this.sunDir.set(Math.cos(e) * Math.sin(b), Math.sin(e), -Math.cos(e) * Math.cos(b));
    this.sky.material.uniforms.sunPosition.value.copy(this.sunDir);
  }

  _shadowRange(r) {
    const cam = this.sun.shadow.camera;
    cam.left = -r;
    cam.right = r;
    cam.top = r;
    cam.bottom = -r;
    cam.near = 1;
    cam.far = 4 * r + 1200;
    cam.updateProjectionMatrix();
    this._shadowR = r;
  }

  resize() {
    const w = Math.max(1, this.container.clientWidth), h = Math.max(1, this.container.clientHeight);
    this.renderer.setSize(w, h);
    this.labelsRenderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  // ------------------------------------------------------------------ the world

  async reload() {
    if (this._loadingWorld) {
      this._again = true;
      return;
    }
    this._loadingWorld = true;
    try {
      const res = await fetch(this.url(`/_roam/world/${this.path}`), { cache: "no-store" });
      if (res.status === 404) {
        // The model was deleted (in Codoc in CAD or on the storage page).
        for (const t of this.things.values()) t.dispose();
        this.things.clear();
        this.hud.closeBig();
        this._emit({ type: "gone" });
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const world = await res.json();
      if (this.disposed) return;
      this._apply(world);
    } catch (e) {
      console.warn("Roam: world", e);
      this._emit({ type: "error", text: String(e) });
      this.hud.say(this.hud.t("world_failed", "The world could not be loaded"));
    } finally {
      this._loadingWorld = false;
      if (this._again && !this.disposed) {
        this._again = false;
        this.reload();
      }
    }
  }

  _ctx() {
    return {
      scene: this.scene,
      look: this.look,
      quality: this.quality,
      url: (p) => this.url(p),
      onProgress: () => { this._loadingChanged = true; },
      onLoaded: (t) => this._loaded(t),
    };
  }

  _apply(world) {
    const first = !this.ready;
    const hadNone = this.things.size === 0;
    this.rev = world.rev || 0;
    this.worldData = world;
    const seen = new Set();
    for (const data of world.things || []) {
      seen.add(data.key);
      const old = this.things.get(data.key);
      if (!old) {
        this.things.set(data.key, new Thing(data, this._ctx()));
        continue;
      }
      if (!needsRebuild(old.data, data)) {
        old.data = data;
        continue;
      }
      const thing = new Thing(data, this._ctx());
      this.things.set(data.key, thing);
      const placeSame = ["x", "z", "unit", "w", "d", "h", "base"].every((k) => old.data[k] === data[k]);
      if (data.type === "model" && old.data.type === "model" && old.status === "ready" && placeSame) {
        // A rebuilt model: keep showing the old one until the new mesh is in.
        if (thing.placeholder) thing.placeholder.visible = false;
        const prev = this.replacing.get(data.key);
        if (prev) prev.dispose();
        this.replacing.set(data.key, old);
      } else {
        old.dispose();
      }
    }
    for (const [key, thing] of this.things) {
      if (!seen.has(key)) {
        thing.dispose();
        this.things.delete(key);
        this.hud.closeBig(key);
        const prev = this.replacing.get(key);
        if (prev) prev.dispose(), this.replacing.delete(key);
      }
    }
    this._worldBounds();
    this._loadingChanged = true;
    if (first) {
      this.ready = true;
      const key = (this.opts.spawn && this.things.has(this.opts.spawn)) ? this.opts.spawn : world.spawn;
      if (key && this.things.has(key)) this.goto(key, true);
      else this.player.place(0, 0, 12, 0);
      this._spawned = true;
      this._emit({ type: "ready", rev: this.rev, things: this.things.size });
    } else {
      // A model that wasn't built when you came has just been built: stand in front of it.
      if (hadNone && world.spawn && this.things.has(world.spawn)) this.goto(world.spawn, true);
      this._emit({ type: "world", rev: this.rev });
    }
    this._schedule();
  }

  _worldBounds() {
    const box = new THREE.Box3();
    for (const t of this.things.values()) box.union(t.bounds);
    this.bounds = box;
    const size = box.isEmpty() ? 100 : Math.max(box.max.x - box.min.x, box.max.z - box.min.z);
    this.hud.setMapRange(Math.max(40, Math.min(420, size * 0.45)));
    this.scene.fog.near = Math.max(600, size * 2.5);
    this.scene.fog.far = Math.max(6000, size * 14);
  }

  // Loads models nearest first, a couple at a time; big ones once the person said so.
  _schedule() {
    const loading = [...this.things.values()].filter((t) => t.status === "loading").length;
    let free = LOADS_AT_ONCE - loading;
    if (free <= 0) return;
    const p = this.player.position;
    const waiting = [...this.things.values()]
      .filter((t) => t.status === "waiting")
      .sort((a, b) => a.bounds.distanceToPoint(p) - b.bounds.distanceToPoint(p));
    for (const t of waiting) {
      if (t.data.big && BIG.get(t.key) !== true) {
        this._askBig(t);
        continue;
      }
      if (free-- <= 0) break;
      t.load();
    }
  }

  // A model over the server's triangle limit: what loading it costs, and load it or not (hud.js).
  _askBig(thing) {
    if (BIG.get(thing.key) === false) {
      this._skip(thing);
      return;
    }
    const t = thing.data;
    this.input.unlock();
    this.hud.askBig(
      { key: t.key, mesh: t.mesh, title: t.title, tris: t.tris, limit: t.big.limit, bytes: t.big.bytes, memory: t.tris * BYTES_PER_TRIANGLE },
      (load) => {
        BIG.set(thing.key, load);
        this._schedule();
      },
    );
  }

  // Not loaded: its outline stays (or its last build, when this is a newer one), and the HUD
  // offers to load it after all.
  _skip(thing) {
    thing.status = "skipped";
    if (!this.replacing.has(thing.key)) thing.setNote(this.hud.t("not_loaded", "not loaded"));
    this._loadingChanged = true;
  }

  _loaded(thing) {
    const old = this.replacing.get(thing.key);
    if (old && this.things.get(thing.key) === thing) {
      old.dispose();
      this.replacing.delete(thing.key);
    }
    if (thing.status === "failed") thing.setNote(this.hud.t("model_failed", "could not be loaded"));
    this._loadingChanged = true;
    this._schedule();
  }

  _colliders() {
    const out = [];
    for (const t of this.things.values()) for (const c of t.colliders) out.push(c);
    for (const t of this.replacing.values()) for (const c of t.colliders) out.push(c);
    return out;
  }

  _pickables() {
    const out = [];
    for (const t of this.things.values()) for (const m of t.pickables) out.push(m);
    return out;
  }

  // ------------------------------------------------------------------ going places

  goto(key, instant = false) {
    const thing = this.things.get(key);
    if (!thing) return false;
    const v = thing.viewpoint(this.player.mode);
    this._travel(v.x, v.y, v.z, v.yaw, v.pitch, instant);
    return true;
  }

  follow(peer) {
    const w = this.people.where(peer);
    if (!w) return false;
    if (w.mode === "fly" && this.player.mode !== FLY) this.setMode(FLY);
    const back = 3.5;
    const x = w.p[0] + Math.sin(w.yaw) * back;
    const z = w.p[2] + Math.cos(w.yaw) * back;
    const y = this.player.mode === FLY ? w.p[1] + 0.8 : Math.max(0, w.p[1]);
    this._travel(x, y, z, w.yaw, this.player.mode === FLY ? -0.15 : 0, false);
    return true;
  }

  _travel(x, y, z, yaw, pitch, instant) {
    const p = this.player;
    if (instant) {
      p.place(x, y, z, yaw, pitch);
      this.hud.flash();
      this._schedule();
      return;
    }
    let dy = yaw - p.yaw;
    dy = Math.atan2(Math.sin(dy), Math.cos(dy));
    const from = p.position.clone();
    const to = new THREE.Vector3(x, y, z);
    const dist = from.distanceTo(to);
    this._tween = {
      from, to, yaw0: p.yaw, yaw1: p.yaw + dy, pitch0: p.pitch, pitch1: pitch,
      t: 0, d: Math.min(2.2, 0.6 + dist / 160),
      lift: Math.min(150, dist * 0.25),
    };
  }

  _stepTween(dt) {
    const w = this._tween;
    w.t = Math.min(1, w.t + dt / w.d);
    const e = w.t < 0.5 ? 4 * w.t ** 3 : 1 - (-2 * w.t + 2) ** 3 / 2;
    const p = this.player;
    p.position.lerpVectors(w.from, w.to, e);
    p.position.y += Math.sin(Math.PI * e) * w.lift * (p.mode === FLY ? 1 : 0.35);
    p.yaw = w.yaw0 + (w.yaw1 - w.yaw0) * e;
    p.pitch = w.pitch0 + (w.pitch1 - w.pitch0) * e;
    p.velocity.set(0, 0, 0);
    if (w.t >= 1) {
      p.place(w.to.x, w.to.y, w.to.z, w.yaw1, w.pitch1);
      this._tween = null;
      this._schedule();
    }
  }

  setMode(mode) {
    if (mode !== WALK && mode !== FLY) return;
    if (mode !== this.player.mode) {
      this.player.setMode(mode);
      this._emit({ type: "mode", mode });
    }
    this.hud.setMode(this.player.mode, this.player.ghost, this.light);
  }

  // ------------------------------------------------------------------ actions

  _action(a, d) {
    if (a === "mode") this.setMode(this.player.mode === WALK ? FLY : WALK);
    else if (a === "sun") this.setTime(TIMES.find((t) => t > this.time + 1e-3) ?? TIMES[0]);
    else if (a === "ghost") {
      this.player.ghost = !this.player.ghost;
      this.hud.setMode(this.player.mode, this.player.ghost, this.light);
    } else if (a === "light") {
      this.light = !this.light;
      this.torch.intensity = this.light ? 60 : 0;
      this.hud.setMode(this.player.mode, this.player.ghost, this.light);
    } else if (a === "interact") this._pickAt(null);
    else if (a === "pick") this._pickAt(d);
    else if (a === "click") {
      this.input.lock();
      if (this.listener.context.state === "suspended") this.listener.context.resume();
    } else if (a === "help") {
      this._helpOpen = !this._helpOpen;
      this.hud.showKeys(this._helpOpen);
    } else if (a === "respawn") {
      const key = this.worldData && this.worldData.spawn;
      if (key) this.goto(key);
    } else if (a === "load_big") {
      // A big model left unloaded: loaded after all (the HUD's button).
      BIG.set(d, true);
      const thing = this.things.get(d);
      if (thing && thing.status === "skipped") {
        thing.status = "waiting";
        thing.setNote("");
        this._schedule();
      }
    } else if (a === "locked") {
      // The key list stays up until you first look around; H shows it again.
      this.hud.setLocked(true);
      this.hud.showHelp(false);
      if (!this._helpOpen) this.hud.showKeys(false);
    } else if (a === "unlocked") {
      this.hud.setLocked(false);
      this.hud.showHelp(true);
    }
  }

  _ray(screen) {
    const ray = new THREE.Raycaster();
    ray.firstHitOnly = true;
    ray.far = 2000;
    if (screen) {
      const r = this.renderer.domElement.getBoundingClientRect();
      ray.setFromCamera(new THREE.Vector2(((screen.x - r.left) / r.width) * 2 - 1, -((screen.y - r.top) / r.height) * 2 + 1), this.camera);
    } else {
      ray.setFromCamera(new THREE.Vector2(0, 0), this.camera);
    }
    const hits = ray.intersectObjects(this._pickables(), false);
    const hit = hits.find((h) => h.object.userData.key);
    return hit ? { thing: this.things.get(hit.object.userData.key), distance: hit.distance } : null;
  }

  _pickAt(screen) {
    const hit = this._ray(screen);
    if (!hit || !hit.thing) return;
    const thing = hit.thing;
    this.selected = thing.key;
    this.input.unlock();
    this._emit({ type: "select", key: thing.key });
  }

  command(cmd) {
    if (!cmd || !cmd.type) return;
    if (cmd.type === "goto") this.goto(cmd.key);
    else if (cmd.type === "follow") this.follow(cmd.peer);
    else if (cmd.type === "mode") this.setMode(cmd.mode);
    else if (cmd.type === "reload") this.reload();
    else if (cmd.type === "release") this.input.unlock();
    else if (cmd.type === "rejoined") this.people.rejoined();
  }

  setLabels(labels) {
    this.labels = labels || {};
    this.hud.setLabels(this.labels);
    this.hud.setMode(this.player.mode, this.player.ghost, this.light);
    this._loadingChanged = true;
  }

  // ------------------------------------------------------------------ the frame

  _loop() {
    if (this.disposed) return;
    this._raf = requestAnimationFrame(this._loop);
    const now = performance.now();
    const dt = Math.min(0.05, (now - this._last) / 1000);
    this._last = now;
    this._t += dt;
    const input = this.input.read(dt);
    const p = this.player;
    if (input.lookX || input.lookY) p.look(input.lookX, input.lookY);
    if (this._tween) this._stepTween(dt);
    else if (this.ready) {
      // Walking: Shift runs; flying: Shift goes down (input.rise), so it doesn't speed up too.
      const move = p.mode === WALK ? { ...input, jump: input.jump } : { ...input, run: false };
      p.step(dt, move, this._colliders());
    }
    p.eye(this.camera);

    // Shadows follow you, snapped to whole texels so they don't shimmer.
    const r = this._shadowR;
    const texel = (2 * r) / this.sun.shadow.mapSize.x;
    const cx = Math.round(p.position.x / texel) * texel, cz = Math.round(p.position.z / texel) * texel;
    this.sun.target.position.set(cx, 0, cz);
    const sunDir = this.sunDir;
    this.sun.position.set(cx + sunDir.x * 1500, sunDir.y * 1500, cz + sunDir.z * 1500);
    const wanted = p.mode === FLY ? Math.min(600, Math.max(120, p.position.y * 2.2)) : 120;
    if (Math.abs(wanted - r) / r > 0.25) this._shadowRange(wanted);

    this.people.frame(dt, this._t);
    this.people.send(
      { p: [p.position.x, p.position.y, p.position.z].map((v) => Math.round(v * 1000) / 1000), yaw: Math.round(p.yaw * 1e4) / 1e4, pitch: Math.round(p.pitch * 1e4) / 1e4, mode: p.mode, moving: p.moving },
      performance.now(),
    );

    // Slower work, ten times a second.
    this._slow += dt;
    if (this._slow > 0.1) {
      this._slow = 0;
      this._tick();
    }
    this.look.frame();
    this.renderer.render(this.scene, this.camera);
    this.labelsRenderer.render(this.scene, this.camera);
    this._frames++;
  }

  _tick() {
    const p = this.player;
    p.measureAltitude(this._pickables());
    this.hud.telemetry(p);
    const hit = this.input.locked || this.input.touch ? this._ray(null) : null;
    const hint = hit && hit.thing ? this.hud.t("hint_details", "E or click: details") : "";
    this.hud.aim(hit && hit.thing && hit.distance < Math.max(60, hit.thing.size * 1.5) ? hit.thing : null, hint);
    // Names: shown near enough, hidden when you are inside or right against the thing.
    const eye = this.camera.position;
    for (const t of this.things.values()) {
      const d = t.bounds.distanceToPoint(eye);
      t.label.visible = d > 0.8 && d < Math.max(70, t.size * 6);
    }
    if (this._loadingChanged) {
      this._loadingChanged = false;
      const rows = [...this.things.values()]
        .filter((t) => t.status === "loading" || t.status === "skipped")
        .map((t) => ({ key: t.key, title: t.data.title, progress: t.progress, skipped: t.status === "skipped", newer: this.replacing.has(t.key) }));
      this.hud.setLoading(rows);
    }
    this.hud.drawMap(p, this.things.values(), this.peopleList, (this.opts.me || {}).peer);
    this._fpsTime = (this._fpsTime || 0) + 0.1;
    if (this._fpsTime >= 1) {
      this._fps = this._frames / this._fpsTime;
      this._frames = 0;
      this._fpsTime = 0;
    }
  }

  // For tests and the page: where you are and what is loaded.
  state() {
    const p = this.player;
    const things = {}, looks = {};
    for (const [k, t] of this.things) {
      things[k] = t.status;
      looks[k] = { parts: t.parts, glass: t.glass, glow: t.glow };
    }
    return {
      ready: this.ready,
      rev: this.rev,
      mode: p.mode,
      ghost: p.ghost,
      position: p.position.toArray(),
      yaw: p.yaw,
      pitch: p.pitch,
      onGround: p.onGround,
      altitude: p.altitude,
      locked: this.input.locked,
      things,
      looks,
      time: this.time,
      people: this.peopleList.map((x) => ({ id: x.id, name: x.name, mode: x.mode, p: x.p })),
      figures: [...this.people.figures.keys()],
      connected: this.people.connected,
      fps: Math.round(this._fps),
    };
  }

  dispose() {
    this.disposed = true;
    cancelAnimationFrame(this._raf);
    this._resize.disconnect();
    this.input.dispose();
    this.people.dispose();
    for (const t of this.things.values()) t.dispose();
    for (const t of this.replacing.values()) t.dispose();
    this.things.clear();
    this.replacing.clear();
    this.hud.dispose();
    this.look.dispose();
    this.scene.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) {
        if (o.material.map) o.material.map.dispose();
        o.material.dispose();
      }
    });
    this.renderer.dispose();
    this.renderer.forceContextLoss();
    this.surface.remove();
    if (window.__roam === this) window.__roam = null;
  }
}
