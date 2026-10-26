// How you see the place: through your own eyes, or yourself from a little behind and above (V,
// or the buttons beside Walk / Drone), walking as the others see you (your figure, in your
// colour) or flying your drone, which leans into its turns.
//
// From behind, the camera stays on your side of walls, floors, ceilings and glass: something
// behind you brings it closer at once, and it goes back out smoothly once there is room again
// (a ghost drone's camera goes through walls too). Right up against you, your figure isn't
// drawn, so it doesn't fill the view. A browser keeps the choice.

import * as THREE from "three";
import { drone, walker } from "./people.js";
import { BODY, FLY } from "./player.js";

export const EYES = "eyes";
export const BEHIND = "behind";
const VIEW_KEY = "cad_roam_view";

// From behind: how far back the camera is, and how far above your eyes (walking) or your drone
// (flying), in metres. Your head is then just under the middle of the view, your feet above the
// buttons at the bottom.
const BACK = { walk: 4.0, fly: 2.0 };
const ABOVE = { walk: 0.45, fly: 0.5 };
// How far it keeps from what is behind you, and from the ground.
const CLEAR = 0.25;
const GROUND = 0.12;
// How fast it moves when you switch, and back out once something is no longer behind you (1/s).
const SWITCH_RATE = 7;
const OUT_RATE = 3;
// Nearer than this to your body (or your drone), your figure isn't drawn.
const NEAR = 0.65;
// Your drone tips forward more than its camera does when you look through it.
const TIP = 3;
const COLOR = "#14b8a6"; // yours until the place has given you one

const _from = new THREE.Vector3();
const _back = new THREE.Vector3();
const _up = new THREE.Vector3(0, 1, 0);
const _ray = new THREE.Ray();
const _body = new THREE.Line3();
const _near = new THREE.Vector3();

function savedView() {
  try {
    return localStorage.getItem(VIEW_KEY) === BEHIND ? BEHIND : EYES;
  } catch (e) {
    return EYES;
  }
}

// How far from `from` along `dir` (a unit vector) nothing is in the way, up to `far` (also how far
// the others' torch beams go: people.js).
export function reach(colliders, from, dir, far) {
  _ray.origin.copy(from);
  _ray.direction.copy(dir);
  let free = far;
  for (const c of colliders) {
    if (c.box.distanceToPoint(from) >= free || !_ray.intersectsBox(c.box)) continue;
    const hit = c.bvh.raycastFirst(_ray, THREE.DoubleSide, 0, free);
    if (hit && hit.distance < free) free = hit.distance;
  }
  return free;
}

export class View {
  constructor(scene, look) {
    this.scene = scene;
    this.look = look;
    this.kind = savedView();
    this.mix = this.kind === BEHIND ? 1 : 0; // 0: your eyes, 1: from behind
    this.back = 0; // how far behind you the camera is now
    this.shown = false; // your figure drawn
    this.color = "";
    this.me = null;
  }

  set(kind) {
    this.kind = kind === BEHIND ? BEHIND : EYES;
    try {
      localStorage.setItem(VIEW_KEY, this.kind);
    } catch (e) {
      // A browser that keeps nothing asks again on the next page.
    }
  }

  // Your colour, as the others see you (it comes once you are in the place).
  setColor(color) {
    color = color || COLOR;
    if (color === this.color) return;
    this.color = color;
    this._dispose();
  }

  // Each frame, once you have moved: the camera where it looks from and your figure.
  frame(camera, player, colliders, dt) {
    const want = this.kind === BEHIND ? 1 : 0;
    this.mix += (want - this.mix) * (1 - Math.exp(-dt * SWITCH_RATE));
    if (Math.abs(want - this.mix) < 0.002) this.mix = want;
    player.eye(camera);
    if (this.mix === 0) {
      this.back = 0;
      this._show(false);
      return;
    }
    const fly = player.mode === FLY, m = this.mix, mode = fly ? "fly" : "walk";
    const through = fly && player.ghost;
    // Above your eyes (less under a low ceiling), then back from where you look.
    _from.copy(camera.position);
    if (!fly) _from.y += (player.position.y + BODY.eye - _from.y) * m; // your figure doesn't bob
    let above = ABOVE[mode];
    if (!through) above = Math.min(above, reach(colliders, _from, _up, above + CLEAR) - CLEAR);
    _from.y += Math.max(0, above) * m;
    const { pitch, yaw } = player;
    _back.set(Math.sin(yaw) * Math.cos(pitch), -Math.sin(pitch), Math.cos(yaw) * Math.cos(pitch));
    let free = BACK[mode] * m;
    if (!through) free = Math.min(free, reach(colliders, _from, _back, free + CLEAR) - CLEAR);
    if (_back.y < 0) free = Math.min(free, (_from.y - GROUND) / -_back.y);
    free = Math.max(0, free);
    if (free < this.back) this.back = free;
    else this.back += (free - this.back) * (1 - Math.exp(-dt * OUT_RATE));
    camera.position.copy(_from).addScaledVector(_back, this.back);
    camera.rotation.set(pitch + player.tilt * (1 - m), yaw, player.roll * (1 - m), "YXZ");
    this._place(player, camera, dt);
  }

  _figure() {
    if (this.me) return this.me;
    const color = this.color || COLOR;
    const group = new THREE.Group();
    const w = walker(color), d = drone(color);
    group.add(w, d);
    // Lit as the place you are in, as the others' figures are.
    group.traverse((o) => { if (o.isMesh && o.material.isMeshStandardMaterial) this.look.receive(o.material); });
    group.visible = false;
    this.scene.add(group);
    this.me = { group, walker: w, drone: d };
    return this.me;
  }

  _place(player, camera, dt) {
    const f = this._figure(), fly = player.mode === FLY, p = player.position;
    f.group.position.copy(p);
    f.walker.visible = !fly;
    f.drone.visible = fly;
    if (fly) {
      f.group.rotation.set(player.tilt * TIP, player.yaw, player.roll, "YXZ");
      for (const r of f.drone.userData.rotors) r.rotation.z += dt * 40;
    } else {
      f.group.rotation.set(0, player.yaw, 0);
    }
    let near;
    if (fly) near = camera.position.distanceTo(p);
    else {
      _body.start.set(p.x, p.y + 0.3, p.z);
      _body.end.set(p.x, p.y + 1.6, p.z);
      near = _body.closestPointToPoint(camera.position, true, _near).distanceTo(camera.position);
    }
    this._show(near > NEAR);
  }

  _show(on) {
    this.shown = on;
    if (this.me) this.me.group.visible = on;
  }

  _dispose() {
    if (!this.me) return;
    this.scene.remove(this.me.group);
    this.me.group.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) o.material.dispose();
    });
    this.me = null;
  }

  dispose() {
    this._dispose();
  }
}
