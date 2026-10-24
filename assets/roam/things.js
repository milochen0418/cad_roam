// The model in its place: at its real size (from its mesh), on paving, on a pedestal when it is
// small, with its name over it.
//
// Everything is placed and collided in world coordinates (metres, Y up). A thing's data comes
// from the server (cad_roam/models.py): x, z = the centre of its footprint, w x d its footprint,
// h its height, base the pedestal under it.

import * as THREE from "three";
import { MeshBVH } from "three-mesh-bvh";
import { CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";

const STONES = [0xefe9df, 0xe7dcc6, 0xdcc9a7, 0xd9e2d4, 0xdde1e6, 0xeadad3];
const PAVING = 0xd8d2c4;
const PEDESTAL = 0x3b3f46;

function hash(text) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return h >>> 0;
}

function boxCollider(w, h, d, x, y, z) {
  const geo = new THREE.BoxGeometry(w, h, d);
  geo.translate(x, y, z);
  geo.computeBoundingBox();
  const bvh = new MeshBVH(geo);
  return { box: geo.boundingBox.clone(), bvh, geo };
}

function disposeTree(obj) {
  obj.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
    for (const m of mats) {
      if (m.map) m.map.dispose();
      m.dispose();
    }
  });
}

// Where the mesh of a model goes: model coordinates (Z up, -Y to the front) to the world.
function placeModel(positions, t) {
  const [x0, y0, , x1, y1] = t.box;
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, u = t.unit, g = t.ground;
  for (let i = 0; i < positions.length; i += 3) {
    const mx = positions[i], my = positions[i + 1], mz = positions[i + 2];
    positions[i] = (mx - cx) * u + t.x;
    positions[i + 1] = (mz - g) * u + t.base;
    positions[i + 2] = -(my - cy) * u + t.z;
  }
}

// Reads a mesh file (cad_roam/meshes.py) into positions and indices.
export function parseMesh(buffer) {
  const head = new DataView(buffer, 0, 48);
  const magic = String.fromCharCode(head.getUint8(0), head.getUint8(1), head.getUint8(2), head.getUint8(3));
  if (magic !== "RMSH") throw new Error("not a Roam mesh");
  const nverts = head.getUint32(8, true), ntris = head.getUint32(12, true), width = head.getUint32(16, true);
  const positions = new Float32Array(buffer, 48, nverts * 3).slice();
  const offset = 48 + nverts * 12;
  const indices = width === 4 ? new Uint32Array(buffer, offset, ntris * 3) : new Uint16Array(buffer, offset, ntris * 3);
  return { positions, indices };
}

export class Thing {
  constructor(data, ctx) {
    this.data = data;
    this.ctx = ctx; // {scene, url(path), quality, onLoaded(thing), onProgress(thing)}
    this.key = data.key;
    this.group = new THREE.Group();
    this.group.name = data.key;
    this.colliders = [];
    this.pickables = [];
    const fw = Math.max(data.w, data.pedestal || 0) / 2, fd = Math.max(data.d, data.pedestal || 0) / 2;
    this.bounds = new THREE.Box3(
      new THREE.Vector3(data.x - fw, 0, data.z - fd),
      new THREE.Vector3(data.x + fw, data.base + Math.max(data.h, 0.05), data.z + fd),
    );
    this.status = "waiting"; // "waiting" | "loading" | "ready" | "failed"
    this.progress = 0;
    this._abort = null;
    ctx.scene.add(this.group);
    this._plot();
    this._label();
    this._placeholder();
  }

  get size() {
    return Math.max(this.data.w, this.data.d, this.data.h + this.data.base);
  }

  // Where to stand to see it: in front of it, far enough to take it in.
  viewpoint(mode) {
    const t = this.data;
    const big = Math.max(t.w, t.h + t.base);
    const front = t.z + Math.max(t.d, t.pedestal || 0, 0.3) / 2;
    if (mode === "fly") {
      const dist = Math.min(400, big * 0.85 + 4);
      const y = Math.max(3, (t.h + t.base) * 0.55 + Math.min(big * 0.25, 60));
      const pitch = -Math.atan2(y - (t.h + t.base) * 0.4, dist + t.d / 2);
      return { x: t.x, y, z: front + dist, yaw: 0, pitch };
    }
    // Small things: far enough to see all of it; buildings: close enough to walk up to.
    const dist = big < 6 ? Math.max(2.4, big * 0.85) : Math.min(45, big * 0.3 + 1);
    const middle = t.base + t.h * 0.5;
    const eyeTo = Math.min(middle, 1.62 + dist * 0.4);
    const pitch = Math.atan2(eyeTo - 1.62, dist + 0.3);
    return { x: t.x, y: 0, z: front + dist, yaw: 0, pitch: THREE.MathUtils.clamp(pitch, -0.6, 0.6) };
  }

  _plot() {
    const t = this.data;
    const [pw, pd] = t.plot || [t.w + 3, t.d + 3];
    // Paving a little larger than the thing (or its pedestal), inside its plot.
    const tw = Math.max(t.w, t.pedestal || 0), td = Math.max(t.d, t.pedestal || 0);
    const pad = Math.min((pw - tw) / 2, (pd - td) / 2) * 0.7;
    const w = tw + 2 * pad, d = td + 2 * pad;
    const geo = new THREE.BoxGeometry(w, 0.04, d);
    const mat = new THREE.MeshStandardMaterial({ color: PAVING, roughness: 0.95 });
    const slab = new THREE.Mesh(geo, mat);
    slab.position.set(t.x, 0, t.z);
    slab.receiveShadow = true;
    this.group.add(slab);
    if (t.base > 0) {
      const side = t.pedestal || Math.max(t.w, t.d);
      const ped = new THREE.Mesh(
        new THREE.BoxGeometry(side, t.base, side),
        new THREE.MeshStandardMaterial({ color: PEDESTAL, roughness: 0.6, metalness: 0.1 }),
      );
      ped.position.set(t.x, t.base / 2, t.z);
      ped.castShadow = ped.receiveShadow = true;
      ped.userData.key = this.key;
      this.group.add(ped);
      this.pickables.push(ped);
      this.colliders.push(boxCollider(side, t.base, side, t.x, t.base / 2, t.z));
    }
  }

  _label() {
    const t = this.data;
    const el = document.createElement("div");
    el.className = "rm-label";
    const title = document.createElement("div");
    title.className = "rm-label-title";
    title.textContent = t.title;
    const sub = document.createElement("div");
    sub.className = "rm-label-sub";
    el.append(title, sub);
    this.labelEl = el;
    this.labelSub = sub;
    this.label = new CSS2DObject(el);
    const top = t.base + t.h;
    this.label.position.set(t.x, top + Math.max(0.35, Math.min(4, top * 0.04)), t.z);
    this.label.center.set(0.5, 1);
    this.group.add(this.label);
  }

  setNote(text) {
    if (this.labelSub.textContent !== text) this.labelSub.textContent = text;
  }

  // ------------------------------------------------------------------ models

  _placeholder() {
    const t = this.data;
    const geo = new THREE.BoxGeometry(Math.max(t.w, 0.05), Math.max(t.h, 0.05), Math.max(t.d, 0.05));
    const lines = new THREE.LineSegments(
      new THREE.EdgesGeometry(geo),
      new THREE.LineBasicMaterial({ color: 0x64748b, transparent: true, opacity: 0.7 }),
    );
    geo.dispose();
    lines.position.set(t.x, t.base + Math.max(t.h, 0.05) / 2, t.z);
    this.placeholder = lines;
    this.group.add(lines);
    this.status = "waiting";
  }

  async load() {
    if (this.status === "loading" || this.status === "ready") return;
    this.status = "loading";
    this.progress = 0;
    const abort = new AbortController();
    this._abort = abort;
    try {
      const res = await fetch(this.ctx.url(this.data.mesh), { signal: abort.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const total = Number(res.headers.get("X-Roam-Bytes")) || 0;
      let buffer;
      if (res.body && total) {
        const out = new Uint8Array(total);
        const reader = res.body.getReader();
        let got = 0;
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          if (got + value.length > out.length) throw new Error("mesh longer than announced");
          out.set(value, got);
          got += value.length;
          this.progress = got / total;
          this.ctx.onProgress(this);
        }
        buffer = out.buffer;
      } else {
        buffer = await res.arrayBuffer();
      }
      if (abort.signal.aborted || this.disposed) return;
      this._build(parseMesh(buffer));
      this.status = "ready";
      this.progress = 1;
    } catch (e) {
      if (abort.signal.aborted || this.disposed) return;
      this.status = "failed";
      console.warn("Roam: model", this.key, e);
    }
    this.ctx.onLoaded(this);
  }

  _build({ positions, indices }) {
    const t = this.data;
    placeModel(positions, t);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setIndex(new THREE.BufferAttribute(indices, 1));
    geo.computeBoundingBox();
    geo.computeBoundingSphere();
    geo.boundsTree = new MeshBVH(geo);
    const mat = new THREE.MeshStandardMaterial({
      color: STONES[hash(this.key) % STONES.length],
      roughness: 0.84,
      metalness: 0.02,
      flatShading: true,
      side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.castShadow = this.ctx.quality !== "low";
    mesh.receiveShadow = true;
    mesh.userData.key = this.key;
    this.mesh = mesh;
    if (this.placeholder) {
      this.group.remove(this.placeholder);
      disposeTree(this.placeholder);
      this.placeholder = null;
    }
    this.group.add(mesh);
    this.pickables.push(mesh);
    this.colliders.push({ box: geo.boundingBox.clone(), bvh: geo.boundsTree });
    this.bounds.union(geo.boundingBox);
  }

  dispose() {
    this.disposed = true;
    if (this._abort) this._abort.abort();
    this.ctx.scene.remove(this.group);
    if (this.label && this.label.element.parentNode) this.label.element.remove();
    disposeTree(this.group);
    for (const c of this.colliders) if (c.geo) c.geo.dispose();
    this.colliders = [];
    this.pickables = [];
  }
}

// Changes that need the thing built again (the rest is only words).
export function needsRebuild(a, b) {
  for (const k of ["mesh", "unit", "x", "z", "w", "d", "h", "base", "pedestal", "title"]) {
    if (JSON.stringify(a[k]) !== JSON.stringify(b[k])) return true;
  }
  return false;
}
