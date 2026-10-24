// The person in the world: walking (a body with gravity that bumps into walls, climbs low steps
// and jumps) or flying a drone (no gravity, a little inertia, banks into turns, bumps into
// things unless it is a ghost).
//
// Collisions use the things' BVHs (three-mesh-bvh), all in world coordinates: the body is a
// capsule, the drone a sphere. The ground is the plane y = 0.

import * as THREE from "three";

export const WALK = "walk";
export const FLY = "fly";
export const BODY = { radius: 0.3, height: 1.75, eye: 1.62 };
const DRONE = 0.35;
const GRAVITY = -20;
const JUMP = 6.6;
const STEP_UP = 0.36; // a ledge this high (a stair, a kerb) is stepped onto, not bumped into
const WALK_SPEED = 4.2;
const RUN_SPEED = 8.5;
const PITCH_LIMIT = Math.PI / 2 - 0.02;
export const FLY_SPEEDS = [1, 2, 4, 7, 12, 20, 35, 60, 100, 160];

const _seg = new THREE.Line3();
const _box = new THREE.Box3();
const _tri = new THREE.Vector3();
const _cap = new THREE.Vector3();
const _dir = new THREE.Vector3();
const _mid = new THREE.Vector3();
const _wish = new THREE.Vector3();
const _fwd = new THREE.Vector3();
const _right = new THREE.Vector3();
const _delta = new THREE.Vector3();
const _ray = new THREE.Raycaster();
const _down = new THREE.Vector3(0, -1, 0);

export function forwardOf(yaw, out = new THREE.Vector3()) {
  return out.set(-Math.sin(yaw), 0, -Math.cos(yaw));
}

export function rightOf(yaw, out = new THREE.Vector3()) {
  return out.set(Math.cos(yaw), 0, -Math.sin(yaw));
}

// Pushes the segment (a capsule of `radius` around it) out of every collider it is inside.
// `info`, when given, learns whether anything pushed sideways and the highest point touched.
export function pushOut(colliders, segment, radius, info) {
  _box.makeEmpty();
  _box.expandByPoint(segment.start);
  _box.expandByPoint(segment.end);
  _box.min.addScalar(-radius);
  _box.max.addScalar(radius);
  let hit = false;
  for (const c of colliders) {
    if (!c.box.intersectsBox(_box)) continue;
    c.bvh.shapecast({
      intersectsBounds: (box) => box.intersectsBox(_box),
      intersectsTriangle: (tri) => {
        const d = tri.closestPointToSegment(segment, _tri, _cap);
        if (d >= radius) return false;
        if (d > 1e-6) {
          _dir.subVectors(_cap, _tri).normalize();
        } else {
          // Right on the triangle: out along its normal, on the side of the segment's middle.
          tri.getNormal(_dir);
          segment.getCenter(_mid);
          if (_dir.dot(_mid.sub(_tri)) < 0) _dir.negate();
        }
        const depth = radius - d;
        segment.start.addScaledVector(_dir, depth);
        segment.end.addScaledVector(_dir, depth);
        if (info && Math.abs(_dir.y) < 0.7) {
          info.side = true;
          if (_tri.y > info.top) info.top = _tri.y;
        }
        hit = true;
        return false;
      },
    });
  }
  return hit;
}

export class Player {
  constructor() {
    this.position = new THREE.Vector3(); // walking: the feet; flying: the drone
    this.velocity = new THREE.Vector3();
    this.yaw = 0;
    this.pitch = 0;
    this.mode = WALK;
    this.onGround = false;
    this.ghost = false;
    this.speedIndex = 4; // FLY_SPEEDS[4] = 12 m/s
    this.roll = 0;
    this.tilt = 0;
    this.bob = 0;
    this.moving = false;
    this.altitude = 0; // above whatever is below, when flying
    this.safe = new THREE.Vector3(); // the last place it stood on something
  }

  get flySpeed() {
    return FLY_SPEEDS[this.speedIndex];
  }

  look(dx, dy) {
    this.yaw = (this.yaw + dx) % (Math.PI * 2);
    this.pitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, this.pitch + dy));
  }

  setMode(mode) {
    if (mode === this.mode) return;
    if (mode === FLY) {
      // Take off from eye height.
      this.position.y += BODY.eye + 0.4;
      this.velocity.set(0, 1.5, 0);
    } else {
      // Land: the drone becomes eyes; the feet are below them.
      this.position.y = Math.max(0, this.position.y - BODY.eye);
      this.velocity.multiplyScalar(0.2);
      this.roll = this.tilt = 0;
    }
    this.mode = mode;
    this.onGround = false;
  }

  place(x, y, z, yaw, pitch = 0) {
    this.position.set(x, y, z);
    this.velocity.set(0, 0, 0);
    this.yaw = yaw;
    this.pitch = pitch;
    this.roll = this.tilt = 0;
    if (this.mode === WALK) this.safe.copy(this.position);
  }

  // The camera's place and turn.
  eye(camera) {
    if (this.mode === WALK) {
      const bob = this.onGround && this.moving ? Math.sin(this.bob) * 0.035 : 0;
      camera.position.set(this.position.x, this.position.y + BODY.eye + bob, this.position.z);
      camera.rotation.set(this.pitch, this.yaw, 0, "YXZ");
    } else {
      camera.position.copy(this.position);
      camera.rotation.set(this.pitch + this.tilt, this.yaw, this.roll, "YXZ");
    }
  }

  step(dt, input, colliders) {
    if (input.wheel && this.mode === FLY) {
      this.speedIndex = Math.max(0, Math.min(FLY_SPEEDS.length - 1, this.speedIndex - input.wheel));
    }
    const speedNow = Math.hypot(this.velocity.x, this.velocity.z) + Math.abs(this.velocity.y);
    const radius = this.mode === WALK ? BODY.radius : DRONE;
    const steps = Math.min(30, Math.max(2, Math.ceil((speedNow * dt) / (radius * 0.4))));
    const h = dt / steps;
    for (let i = 0; i < steps; i++) {
      if (this.mode === WALK) this._walk(h, input, colliders);
      else this._fly(h, input, colliders);
    }
    if (this.mode === WALK) {
      const flat = Math.hypot(this.velocity.x, this.velocity.z);
      this.moving = flat > 0.3;
      if (this.moving && this.onGround) this.bob += dt * flat * 2.4;
      if (this.position.y < -60) this.position.copy(this.safe), this.velocity.set(0, 0, 0);
    } else {
      this.moving = this.velocity.lengthSq() > 0.05;
    }
  }

  _wishDir(input) {
    forwardOf(this.yaw, _fwd);
    rightOf(this.yaw, _right);
    _wish.set(0, 0, 0).addScaledVector(_fwd, input.forward).addScaledVector(_right, input.strafe);
    if (_wish.lengthSq() > 1) _wish.normalize();
    return _wish;
  }

  _walk(dt, input, colliders) {
    const wish = this._wishDir(input).multiplyScalar(input.run ? RUN_SPEED : WALK_SPEED);
    const grip = this.onGround ? 12 : 2.5;
    const k = Math.min(1, grip * dt);
    this.velocity.x += (wish.x - this.velocity.x) * k;
    this.velocity.z += (wish.z - this.velocity.z) * k;
    if (this.onGround && input.jump) {
      this.velocity.y = JUMP;
      this.onGround = false;
    } else if (this.onGround) {
      this.velocity.y = GRAVITY * dt; // keep touching the floor, so stepping off a ledge falls
    } else {
      this.velocity.y += GRAVITY * dt;
    }
    const wasOnGround = this.onGround;
    const fromX = this.position.x, fromY = this.position.y, fromZ = this.position.z;
    const vx = this.velocity.x, vz = this.velocity.z;
    this.position.addScaledVector(this.velocity, dt);
    const toX = this.position.x, toY = this.position.y, toZ = this.position.z;
    const info = this._collide(dt, colliders);

    // Walked into a ledge no higher than a step: try the same move from on top of it.
    const rise = info.top - fromY;
    if (wasOnGround && info.side && rise > 0.02 && rise <= STEP_UP) {
      const blocked = Math.hypot(this.position.x - fromX, this.position.z - fromZ);
      const keep = [this.position.x, this.position.y, this.position.z, this.velocity.x, this.velocity.y, this.velocity.z, this.onGround];
      this.position.set(toX, Math.max(toY, info.top + 0.005), toZ);
      this.velocity.set(vx, 0, vz);
      const again = this._collide(dt, colliders);
      const moved = Math.hypot(this.position.x - fromX, this.position.z - fromZ);
      if (moved > blocked + 1e-4 && !(again.side && again.top - this.position.y > 0.02)) {
        this.onGround = true;
        this.velocity.y = 0;
      } else {
        this.position.set(keep[0], keep[1], keep[2]);
        this.velocity.set(keep[3], keep[4], keep[5]);
        this.onGround = keep[6];
      }
    }
    if (this.position.y <= 0) {
      this.position.y = 0;
      if (this.velocity.y < 0) this.velocity.y = 0;
      this.onGround = true;
    }
    if (this.onGround) this.safe.copy(this.position);
  }

  // The body pushed out of whatever it is in; what touched it.
  _collide(dt, colliders) {
    const r = BODY.radius;
    const info = { side: false, top: -Infinity };
    _seg.start.set(this.position.x, this.position.y + r, this.position.z);
    _seg.end.set(this.position.x, this.position.y + BODY.height - r, this.position.z);
    pushOut(colliders, _seg, r, info);
    _delta.set(_seg.start.x - this.position.x, _seg.start.y - r - this.position.y, _seg.start.z - this.position.z);
    this.onGround = _delta.y > Math.abs(dt * this.velocity.y * 0.25);
    this.position.add(_delta);
    if (_delta.lengthSq() > 1e-12) {
      _delta.normalize();
      const into = this.velocity.dot(_delta);
      if (into < 0) this.velocity.addScaledVector(_delta, -into);
    }
    return info;
  }

  _fly(dt, input, colliders) {
    const wish = this._wishDir(input);
    wish.y = input.rise;
    if (wish.lengthSq() > 1) wish.normalize();
    wish.multiplyScalar(this.flySpeed);
    const k = 1 - Math.exp(-dt * 2.8);
    this.velocity.lerp(wish, k);
    this.position.addScaledVector(this.velocity, dt);
    if (!this.ghost) {
      _seg.start.copy(this.position);
      _seg.end.copy(this.position);
      if (pushOut(colliders, _seg, DRONE)) {
        _delta.subVectors(_seg.start, this.position);
        this.position.copy(_seg.start);
        if (_delta.lengthSq() > 1e-12) {
          _delta.normalize();
          const into = this.velocity.dot(_delta);
          if (into < 0) this.velocity.addScaledVector(_delta, -into * 1.2);
        }
      }
    }
    if (this.position.y < DRONE) {
      this.position.y = DRONE;
      if (this.velocity.y < 0) this.velocity.y = 0;
    }
    // Lean into the motion, as a drone does.
    rightOf(this.yaw, _right);
    forwardOf(this.yaw, _fwd);
    const s = Math.max(4, this.flySpeed);
    const targetRoll = -THREE.MathUtils.clamp(this.velocity.dot(_right) / s, -1, 1) * 0.22;
    const targetTilt = -THREE.MathUtils.clamp(this.velocity.dot(_fwd) / s, -1, 1) * 0.06;
    const e = Math.min(1, dt * 5);
    this.roll += (targetRoll - this.roll) * e;
    this.tilt += (targetTilt - this.tilt) * e;
  }

  // Height above whatever is below the drone (the ground or a roof), for the HUD.
  measureAltitude(meshes) {
    if (this.mode !== FLY) return 0;
    _ray.set(this.position, _down);
    _ray.firstHitOnly = true;
    _ray.far = this.position.y + 1;
    const hits = meshes.length ? _ray.intersectObjects(meshes, false) : [];
    const below = hits.length ? hits[0].distance : this.position.y;
    this.altitude = Math.max(0, Math.min(below, this.position.y));
    return this.altitude;
  }
}
