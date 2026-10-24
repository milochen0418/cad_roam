// The others in the world: the socket that carries where everyone is (cad_roam/presence.py), and
// their figures: someone walking is a figure in their colour, someone flying is a small drone,
// each with their name over it. Positions arrive about ten times a second and are eased in.

import * as THREE from "three";
import { CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";

const SEND_EVERY = 100; // ms, at most
const KEEP_ALIVE = 2000; // ms: a pose even when standing still

function initials(name) {
  return (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => Array.from(w)[0]).join("").toUpperCase() || "?";
}

function walker(color) {
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
    g.add(m);
  }
  g.userData.head = head;
  return g;
}

function drone(color) {
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
  g.traverse((o) => { if (o.isMesh) o.castShadow = true; });
  g.userData.rotors = rotors;
  return g;
}

class Figure {
  constructor(person, scene) {
    this.id = person.id;
    this.scene = scene;
    this.group = new THREE.Group();
    this.walker = walker(person.color);
    this.drone = drone(person.color);
    this.group.add(this.walker, this.drone);
    const tag = document.createElement("div");
    tag.className = "rm-person";
    tag.style.setProperty("--c", person.color);
    this.tagEl = tag;
    this.tag = new CSS2DObject(tag);
    this.tag.center.set(0.5, 1);
    this.group.add(this.tag);
    scene.add(this.group);
    this.pos = new THREE.Vector3().fromArray(person.p || [0, 0, 0]);
    this.target = this.pos.clone();
    this.yaw = this.targetYaw = person.yaw || 0;
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
  }

  frame(dt, t) {
    const k = 1 - Math.exp(-dt * 10);
    if (this.pos.distanceToSquared(this.target) > 400) this.pos.copy(this.target); // a jump: no gliding across the world
    else this.pos.lerp(this.target, k);
    let d = this.targetYaw - this.yaw;
    d = Math.atan2(Math.sin(d), Math.cos(d));
    this.yaw += d * k;
    this.group.position.copy(this.pos);
    this.group.rotation.y = this.yaw;
    if (this.mode === "fly") {
      for (const r of this.drone.userData.rotors) r.rotation.z += dt * 40;
      this.drone.position.y = Math.sin(t * 2.3 + this.id.length) * 0.03;
    }
  }

  dispose() {
    this.scene.remove(this.group);
    if (this.tagEl.parentNode) this.tagEl.remove();
    this.group.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) o.material.dispose();
    });
  }
}

export class People {
  constructor({ scene, wsUrl, peer, onRejoin, onWorld, onChange, onWelcome }) {
    this.scene = scene;
    this.wsUrl = wsUrl;
    this.peer = peer;
    this.onRejoin = onRejoin;
    this.onWorld = onWorld;
    this.onChange = onChange;
    this.onWelcome = onWelcome;
    this.figures = new Map();
    this.list = [];
    this.connected = false;
    this._sent = 0;
    this._last = "";
    this._retry = 0;
    this._closed = false;
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
      ws.send(JSON.stringify({ t: "hello", peer: this.peer, token }));
    };
    ws.onmessage = (ev) => {
      let m;
      try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (m.t === "welcome") {
        this.connected = true;
        this._retry = 0;
        this._last = "";
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
        if (p) Object.assign(p, { p: m.p, yaw: m.yaw, pitch: m.pitch, mode: m.mode });
      } else if (m.t === "world") {
        this.onWorld(m.rev);
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
      else this.figures.set(person.id, new Figure(person, this.scene));
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

  frame(dt, t) {
    for (const f of this.figures.values()) f.frame(dt, t);
  }

  where(id) {
    const f = this.figures.get(id);
    return f ? { p: f.target.toArray(), yaw: f.targetYaw, mode: f.mode } : null;
  }

  dispose() {
    this._closed = true;
    clearTimeout(this._timer);
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
    }
    for (const f of this.figures.values()) f.dispose();
    this.figures.clear();
  }
}

export { initials };
