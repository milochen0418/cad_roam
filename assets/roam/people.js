// The others in the world: the socket that carries where everyone is (cad_roam/presence.py), and
// their figures: someone walking is a figure in their colour, someone flying is a small drone,
// each with their name over it (seen from behind, yours is drawn the same way: view.js).
// Positions arrive about ten times a second and are eased in. The socket also brings an AI's
// requests for a picture (onShoot, eyes.js) and takes the answers back.
//
// Someone's torch (L) shines from their figure where they look: its lamp glows on their head (or
// under their drone), a soft beam goes out from it, and its light falls on the model, stopped by
// walls (the nearest few torches: each is a light every surface works out, with its own shadows).
//
// The sun's time is the model's, the same for everyone there: whoever moves it moves it for all
// (moveSun), and their moves come back here (onSun).

import * as THREE from "three";
import { CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";
import { FLAT_DEPTH } from "./look.js";

const SEND_EVERY = 100; // ms, at most
const KEEP_ALIVE = 2000; // ms: a pose even when standing still
// The sun's time while it is dragged: sent at most this often (ms), its last place always.
const SUN_EVERY = 100;

// A torch, yours (engine.js) or someone else's: a spot light from the eyes. About as bright as the
// sun 3 m away: insides are seen with eyes used to the dark (light.js), up to ten times brighter,
// and a brighter torch left only white where it shone.
export const TORCH = { color: 0xfff6e5, intensity: 10, distance: 60, angle: Math.PI / 6, penumbra: 0.45, decay: 1.2 };
// How many of the others' torches light the model (the nearest ones; the rest only glow), and how
// sharp their shadows are.
const TORCH_LIGHTS = 3;
const TORCH_SHADOW = 1024;
// A torch's shadows are drawn again when it moves or turns, else this often (s), for what moves in
// its light: drawing them draws the whole model once more.
const SHADOWS_EVERY = 0.5;
// A torch's beam in the air: how long it is (shorter when a wall is nearer), how wide, how bright.
const BEAM = { length: 7, angle: 0.28, strength: 0.015 };
// Where a torch is on its figure: at the eyes of someone walking, at a drone's camera.
const LAMP_AT = { walk: 1.6, fly: -0.06 };

function initials(name) {
  return (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => Array.from(w)[0]).join("").toUpperCase() || "?";
}

// A glow round a lamp: white in the middle, gone at the edge.
let glowTexture = null;
function glow() {
  if (!glowTexture) {
    const c = document.createElement("canvas");
    c.width = c.height = 64;
    const g = c.getContext("2d");
    const r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    r.addColorStop(0, "rgba(255,255,255,1)");
    r.addColorStop(0.2, "rgba(255,255,255,0.55)");
    r.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = r;
    g.fillRect(0, 0, 64, 64);
    glowTexture = new THREE.CanvasTexture(c);
    glowTexture.colorSpace = THREE.SRGBColorSpace;
  }
  return glowTexture;
}

// A beam in the air (a cone from the lamp along -Z): brightest at the lamp, gone at its end and
// towards its sides, so it looks like light in the air, not a cone. Drawn in the renderer's
// logarithmic depth, as everything else, so walls in front of it hide it.
function beam() {
  const geometry = new THREE.ConeGeometry(BEAM.length * Math.tan(BEAM.angle), BEAM.length, 24, 1, true);
  geometry.translate(0, -BEAM.length / 2, 0);
  geometry.rotateX(Math.PI / 2);
  const material = new THREE.ShaderMaterial({
    uniforms: { color: { value: new THREE.Color(TORCH.color) }, strength: { value: BEAM.strength } },
    vertexShader: /* glsl */ `
      #include <common>
      #include <logdepthbuf_pars_vertex>
      varying float vAlong;
      varying float vFacing;
      void main() {
        vAlong = 1.0 - uv.y;
        vec4 mv = modelViewMatrix * vec4( position, 1.0 );
        vFacing = abs( dot( normalize( normalMatrix * normal ), normalize( - mv.xyz ) ) );
        gl_Position = projectionMatrix * mv;
        #include <logdepthbuf_vertex>
      }`,
    fragmentShader: /* glsl */ `
      #include <common>
      #include <logdepthbuf_pars_fragment>
      uniform vec3 color;
      uniform float strength;
      varying float vAlong;
      varying float vFacing;
      void main() {
        #include <logdepthbuf_fragment>
        float a = pow( 1.0 - vAlong, 2.0 ) * smoothstep( 0.05, 0.7, vFacing );
        gl_FragColor = vec4( color * strength * a, 1.0 );
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.renderOrder = 3;
  return mesh;
}

// A torch on a figure, turned up and down with its eyes: the lamp, its glow (brightest seen from
// where it shines) and its beam; its light comes from `at` towards `aim`.
function lamp() {
  const pivot = new THREE.Group();
  const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.035, 12, 8), new THREE.MeshBasicMaterial({ color: TORCH.color, toneMapped: false }));
  bulb.position.z = -0.2;
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: glow(), color: TORCH.color, blending: THREE.AdditiveBlending, depthWrite: false }));
  halo.position.z = -0.24;
  const ray = beam();
  ray.position.z = -0.22;
  const at = new THREE.Object3D();
  at.position.z = -0.25;
  const aim = new THREE.Object3D();
  aim.position.z = -1.25;
  pivot.add(bulb, halo, ray, at, aim);
  pivot.visible = false;
  return { pivot, halo, beam: ray, at, aim };
}

export function walker(color) {
  const g = new THREE.Group();
  const cloth = new THREE.MeshStandardMaterial({ color, roughness: 0.6 });
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.25, 0.85, 6, 14), cloth);
  body.position.y = 0.25 + 0.425 + 0.05;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.17, 20, 14), new THREE.MeshStandardMaterial({ color: 0xf3efe9, roughness: 0.5 }));
  head.position.y = 1.58;
  const visor = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.08, 0.08), new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 0.2, metalness: 0.4 }));
  visor.position.set(0, 1.6, -0.14);
  for (const m of [body, head, visor]) {
    m.castShadow = true;
    m.customDepthMaterial = FLAT_DEPTH;
    g.add(m);
  }
  g.userData.head = head;
  return g;
}

export function drone(color) {
  const g = new THREE.Group();
  const dark = new THREE.MeshStandardMaterial({ color: 0x1f2937, roughness: 0.4, metalness: 0.5 });
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.08, 0.34), dark);
  g.add(body);
  const rotors = [];
  for (const [x, z] of [[-0.24, -0.24], [0.24, -0.24], [-0.24, 0.24], [0.24, 0.24]]) {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.035, 0.025, 0.36), dark);
    arm.position.set(x / 2, 0, z / 2);
    arm.rotation.y = Math.atan2(x, z);
    g.add(arm);
    const rotor = new THREE.Mesh(
      new THREE.CircleGeometry(0.12, 24),
      new THREE.MeshBasicMaterial({ color: 0xe5e7eb, transparent: true, opacity: 0.35, side: THREE.DoubleSide }),
    );
    rotor.rotation.x = -Math.PI / 2;
    rotor.position.set(x, 0.05, z);
    g.add(rotor);
    rotors.push(rotor);
    const led = new THREE.Mesh(new THREE.SphereGeometry(0.025, 8, 6), new THREE.MeshBasicMaterial({ color }));
    led.position.set(x, -0.02, z);
    g.add(led);
  }
  const cam = new THREE.Mesh(new THREE.SphereGeometry(0.045, 12, 8), new THREE.MeshStandardMaterial({ color: 0x0b0f14, roughness: 0.1, metalness: 0.8 }));
  cam.position.set(0, -0.06, -0.17);
  g.add(cam);
  g.traverse((o) => {
    if (!o.isMesh) return;
    o.castShadow = true;
    o.customDepthMaterial = FLAT_DEPTH;
  });
  g.userData.rotors = rotors;
  return g;
}

class Figure {
  constructor(person, scene, look) {
    this.id = person.id;
    this.scene = scene;
    this.group = new THREE.Group();
    this.walker = walker(person.color);
    this.drone = drone(person.color);
    this.group.add(this.walker, this.drone);
    // Lit as the place they are in (inside a church too).
    if (look) this.group.traverse((o) => { if (o.isMesh && o.material.isMeshStandardMaterial) look.receive(o.material); });
    const tag = document.createElement("div");
    tag.className = "rm-person";
    tag.style.setProperty("--c", person.color);
    this.tagEl = tag;
    this.tag = new CSS2DObject(tag);
    this.tag.center.set(0.5, 1);
    this.group.add(this.tag);
    // Their torch, where they look (lit or not: update).
    this.lamp = lamp();
    this.group.add(this.lamp.pivot);
    this.torch = false;
    this.ahead = BEAM.length; // how far their beam goes before a wall
    scene.add(this.group);
    this.pos = new THREE.Vector3().fromArray(person.p || [0, 0, 0]);
    this.target = this.pos.clone();
    this.yaw = this.targetYaw = person.yaw || 0;
    this.pitch = this.targetPitch = person.pitch || 0;
    this.update(person);
  }

  update(person) {
    this.person = person;
    this.mode = person.mode === "fly" ? "fly" : "walk";
    this.walker.visible = this.mode === "walk";
    this.drone.visible = this.mode === "fly";
    this.tagEl.textContent = person.name || "?";
    this.tag.position.set(0, this.mode === "walk" ? 2.05 : 0.45, 0);
    if (person.p) this.target.fromArray(person.p);
    if (typeof person.yaw === "number") this.targetYaw = person.yaw;
    if (typeof person.pitch === "number") this.targetPitch = person.pitch;
    this.torch = person.torch === true;
    this.lamp.pivot.visible = this.torch;
    this.lamp.pivot.position.set(0, LAMP_AT[this.mode], 0);
  }

  frame(dt, t, eye) {
    const k = 1 - Math.exp(-dt * 10);
    if (this.pos.distanceToSquared(this.target) > 400) this.pos.copy(this.target); // a jump: no gliding across the world
    else this.pos.lerp(this.target, k);
    let d = this.targetYaw - this.yaw;
    d = Math.atan2(Math.sin(d), Math.cos(d));
    this.yaw += d * k;
    this.pitch += (this.targetPitch - this.pitch) * k;
    this.group.position.copy(this.pos);
    this.group.rotation.y = this.yaw;
    if (this.mode === "fly") {
      for (const r of this.drone.userData.rotors) r.rotation.z += dt * 40;
      this.drone.position.y = Math.sin(t * 2.3 + this.id.length) * 0.03;
    }
    if (!this.torch) return;
    const l = this.lamp;
    l.pivot.rotation.x = this.pitch;
    this.group.updateMatrixWorld(true);
    // The glow is brightest seen from where the torch shines, the beam stops at the first wall.
    l.at.getWorldPosition(_at);
    this.direction(_dir);
    const facing = Math.max(0, _dir.dot(_to.subVectors(eye, _at).normalize()));
    l.halo.material.opacity = 0.25 + 0.75 * facing ** 6;
    l.halo.scale.setScalar(0.35 + 0.45 * facing ** 6);
    l.beam.scale.setScalar(Math.max(0.03, this.ahead / BEAM.length));
  }

  // Where their torch points (a unit vector).
  direction(out) {
    const c = Math.cos(this.pitch);
    return out.set(-Math.sin(this.yaw) * c, Math.sin(this.pitch), -Math.cos(this.yaw) * c);
  }

  // A light shining from their torch.
  aim(light) {
    this.lamp.at.getWorldPosition(light.position);
    this.lamp.aim.getWorldPosition(light.target.position);
  }

  dispose() {
    this.scene.remove(this.group);
    if (this.tagEl.parentNode) this.tagEl.remove();
    this.group.traverse((o) => {
      // (Sprites share one geometry.)
      if (o.geometry && !o.isSprite) o.geometry.dispose();
      if (o.material) o.material.dispose();
    });
  }
}

const _at = new THREE.Vector3();
const _dir = new THREE.Vector3();
const _to = new THREE.Vector3();

export class People {
  // time: () => the sun's time this tab shows; reach(from, dir, far): how far nothing is in the way.
  constructor({ scene, look, wsUrl, peer, quality, time, reach, onShoot, onRejoin, onWorld, onChange, onWelcome, onSun }) {
    this.scene = scene;
    this.look = look;
    this.wsUrl = wsUrl;
    this.peer = peer;
    this.quality = quality;
    this.time = time;
    this.reach = reach;
    this.onShoot = onShoot;
    this.onRejoin = onRejoin;
    this.onWorld = onWorld;
    this.onChange = onChange;
    this.onWelcome = onWelcome;
    this.onSun = onSun;
    this.figures = new Map();
    this.list = [];
    this.connected = false;
    this._sent = 0;
    this._last = "";
    this._retry = 0;
    this._closed = false;
    this._aimed = 0;
    // The model's sun: the last move of it this tab has (the server numbers them), its own moves
    // on their way (sent, not back yet), its next one (not sent yet), and someone else's newest
    // that came meanwhile.
    this._sunSeq = 0;
    this._sunOut = 0;
    this._sunNext = null;
    this._sunSent = 0;
    this._sunHeld = null;
    // The lights of the others' torches, always there (a light more or less would make every
    // surface's shader again), off until a torch has one.
    this.lights = [];
    for (let i = 0; i < TORCH_LIGHTS; i++) {
      const light = new THREE.SpotLight(TORCH.color, 0, TORCH.distance, TORCH.angle, TORCH.penumbra, TORCH.decay);
      light.castShadow = !!(look && look.shadows);
      light.shadow.mapSize.set(TORCH_SHADOW, TORCH_SHADOW);
      light.shadow.camera.near = 0.2;
      light.shadow.bias = -0.00005;
      light.shadow.normalBias = 0.04;
      // Its shadows drawn once now: until they are, three.js gives the surfaces' shaders a plain
      // picture for them, which WebGL refuses, and no surface is drawn at all.
      light.shadow.autoUpdate = false;
      light.shadow.needsUpdate = true;
      // The torch it shines for, and where that was when its shadows were last drawn.
      light.userData = { figure: null, drawn: null, at: new THREE.Vector3(), to: new THREE.Vector3(), since: 0 };
      scene.add(light, light.target);
      this.lights.push(light);
    }
    // Whether this tab is on a screen: an AI's pictures are asked of such a tab first.
    this._seen = () => {
      if (this.connected && this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify({ t: "seen", visible: !document.hidden }));
    };
    document.addEventListener("visibilitychange", this._seen);
    // A moment later: React's development double mount disposes the first view at once.
    this._timer = setTimeout(() => this._connect(), 30);
  }

  _connect() {
    if (this._closed || !this.peer) return;
    let ws;
    try {
      ws = new WebSocket(this.wsUrl);
    } catch (e) {
      this._again();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      let token = "";
      try { token = window.sessionStorage.getItem("token") || ""; } catch (e) { /* storage blocked */ }
      // The time is the sun's, for when nobody at the model has brought one yet.
      ws.send(JSON.stringify({ t: "hello", peer: this.peer, token, visible: !document.hidden, quality: this.quality, time: this.time() }));
    };
    ws.onmessage = (ev) => {
      let m;
      try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (m.t === "welcome") {
        this.connected = true;
        this._retry = 0;
        this._last = "";
        // The model's sun as it is now (moves of yours that didn't get there are lost).
        this._sunOut = 0;
        this._sunHeld = null;
        this._sunSeq = m.sun ? m.sun.seq : 0;
        if (m.sun) this.onSun(m.sun, false);
        if (this.onWelcome) this.onWelcome(m.rev);
      } else if (m.t === "rejoin") {
        this.connected = false;
        this._rejoining = true;
        this.onRejoin();
      } else if (m.t === "people") {
        this._people(m.people || []);
      } else if (m.t === "pose") {
        const f = this.figures.get(m.id);
        if (f) f.update({ ...f.person, ...m });
        const p = this.list.find((x) => x.id === m.id);
        if (p) Object.assign(p, { p: m.p, yaw: m.yaw, pitch: m.pitch, mode: m.mode, torch: m.torch });
      } else if (m.t === "sun") {
        this._sunIn(m);
      } else if (m.t === "world") {
        this.onWorld(m.rev);
      } else if (m.t === "shoot" && this.onShoot) {
        // The answer goes back on this socket (the server knows the request by it).
        this.onShoot(m).then((answer) => {
          if (ws.readyState === 1) ws.send(JSON.stringify({ ...answer, t: "shot", id: m.id }));
        });
      }
    };
    ws.onclose = () => {
      this.connected = false;
      if (this.ws === ws) this.ws = null;
      if (!this._rejoining) this._again();
    };
  }

  _again() {
    if (this._closed) return;
    const wait = Math.min(10000, 500 * 2 ** this._retry++);
    clearTimeout(this._timer);
    this._timer = setTimeout(() => this._connect(), wait);
  }

  // The page entered the world again (after "rejoin"): say hello again.
  rejoined() {
    this._rejoining = false;
    if (this.ws) this.ws.close();
    clearTimeout(this._timer);
    this._timer = setTimeout(() => this._connect(), 200);
  }

  _people(list) {
    this.list = list;
    const here = new Set();
    for (const person of list) {
      if (person.id === this.peer) continue;
      here.add(person.id);
      const f = this.figures.get(person.id);
      if (f) f.update(person);
      else this.figures.set(person.id, new Figure(person, this.scene, this.look));
    }
    for (const [id, f] of this.figures) {
      if (!here.has(id)) {
        f.dispose();
        this.figures.delete(id);
      }
    }
    this.onChange(list);
  }

  // Where this tab's person is (sent when it changed, at most every SEND_EVERY ms).
  send(pose, now) {
    if (!this.connected || !this.ws || this.ws.readyState !== 1) return;
    const text = JSON.stringify({ t: "pose", ...pose });
    if (now - this._sent < SEND_EVERY) return;
    if (text === this._last && now - this._sent < KEEP_ALIVE) return;
    this.ws.send(text);
    this._sent = now;
    this._last = text;
  }

  // You moved the sun: for everyone at the model (while it is dragged, at most every SUN_EVERY ms
  // and where it was let go).
  moveSun(hours) {
    this._sunNext = hours;
    if (this._sunTimer) return;
    this._sunTimer = setTimeout(() => this._sendSun(), Math.max(0, this._sunSent + SUN_EVERY - performance.now()));
  }

  _sendSun() {
    this._sunTimer = null;
    const hours = this._sunNext;
    this._sunNext = null;
    if (hours === null || !this.connected || !this.ws || this.ws.readyState !== 1) return;
    this.ws.send(JSON.stringify({ t: "sun", time: hours }));
    this._sunOut++;
    this._sunSent = performance.now();
  }

  // A move of the model's sun, as the server numbered it (everyone gets each one, the one who
  // moved it too). Someone else's waits while moves of yours are on their way: the server takes
  // yours after it, so everyone ends at your last one; else it is taken, the newest first.
  _sunIn(m) {
    if (m.peer === this.peer) {
      this._sunOut = Math.max(0, this._sunOut - 1);
      this._sunSeq = Math.max(this._sunSeq, m.seq);
    } else if (m.seq > this._sunSeq && (!this._sunHeld || m.seq > this._sunHeld.seq)) {
      this._sunHeld = m;
    }
    const held = this._sunHeld;
    if (!held || this._sunOut || this._sunNext !== null) return;
    this._sunHeld = null;
    if (held.seq <= this._sunSeq) return;
    this._sunSeq = held.seq;
    this.onSun(held, true);
  }

  frame(dt, t, eye) {
    for (const f of this.figures.values()) f.frame(dt, t, eye);
    this._torches(dt, eye);
  }

  // The nearest torches that are on get the lights (one keeps its light while it is among them),
  // their shadows drawn again when they move; ten times a second, how far each beam goes before a
  // wall.
  _torches(dt, eye) {
    const on = [...this.figures.values()].filter((f) => f.torch);
    this._aimed += dt;
    if (this._aimed >= 0.1 && this.reach) {
      this._aimed = 0;
      for (const f of on) {
        f.lamp.at.getWorldPosition(_at);
        f.ahead = this.reach(_at, f.direction(_dir), BEAM.length);
      }
    }
    on.sort((a, b) => a.pos.distanceToSquared(eye) - b.pos.distanceToSquared(eye));
    const lit = new Set(on.slice(0, this.lights.length));
    for (const light of this.lights) if (!lit.has(light.userData.figure)) light.userData.figure = null;
    for (const f of lit) {
      if (this.lights.some((l) => l.userData.figure === f)) continue;
      this.lights.find((l) => !l.userData.figure).userData.figure = f;
    }
    for (const light of this.lights) {
      const u = light.userData, f = u.figure;
      light.intensity = f ? TORCH.intensity : 0;
      if (!f) continue;
      f.aim(light);
      u.since += dt;
      if (u.drawn === f && u.since < SHADOWS_EVERY && u.at.distanceToSquared(light.position) < 1e-6 && u.to.distanceToSquared(light.target.position) < 1e-6) continue;
      light.shadow.needsUpdate = true;
      u.drawn = f;
      u.at.copy(light.position);
      u.to.copy(light.target.position);
      u.since = 0;
    }
  }

  // For an AI's picture (eyes.js), the model in its own light: the others' torches out, until the
  // function returned is called.
  dim() {
    const was = this.lights.map((l) => l.intensity);
    const shown = [...this.figures.values()].map((f) => [f, f.lamp.pivot.visible]);
    for (const l of this.lights) l.intensity = 0;
    for (const [f] of shown) f.lamp.pivot.visible = false;
    return () => {
      this.lights.forEach((l, i) => { l.intensity = was[i]; });
      for (const [f, visible] of shown) f.lamp.pivot.visible = visible;
    };
  }

  // Whose torches are on, and whether each lights the model (for tests).
  torches() {
    const lit = new Set(this.lights.map((l) => l.userData.figure).filter(Boolean));
    return [...this.figures.values()].filter((f) => f.torch).map((f) => ({ id: f.id, lit: lit.has(f) }));
  }

  where(id) {
    const f = this.figures.get(id);
    return f ? { p: f.target.toArray(), yaw: f.targetYaw, mode: f.mode } : null;
  }

  dispose() {
    this._closed = true;
    clearTimeout(this._timer);
    clearTimeout(this._sunTimer);
    document.removeEventListener("visibilitychange", this._seen);
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
    }
    for (const f of this.figures.values()) f.dispose();
    this.figures.clear();
    for (const light of this.lights) {
      this.scene.remove(light, light.target);
      light.dispose();
    }
  }
}

export { initials };
