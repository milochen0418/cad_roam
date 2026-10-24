// What the person asks for: keys, the mouse (pointer lock or drag), touch sticks and a gamepad,
// turned into one set of numbers per frame (move, look, rise) plus one-off actions.
//
// Keys only count while focus is not in a text field, and never with Cmd/Ctrl held (so the
// browser's own shortcuts keep working).

const MOVE_KEYS = {
  KeyW: ["forward", 1], ArrowUp: ["forward", 1], KeyS: ["forward", -1], ArrowDown: ["forward", -1],
  KeyD: ["strafe", 1], ArrowRight: ["strafe", 1], KeyA: ["strafe", -1], ArrowLeft: ["strafe", -1],
};
const ACTION_KEYS = { KeyF: "mode", KeyG: "ghost", KeyL: "light", KeyT: "sun", KeyE: "interact", KeyH: "help", KeyM: "map", KeyR: "respawn" };

function typing(target) {
  if (!target) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

export class Input {
  constructor(surface, onAction) {
    this.surface = surface; // the element that takes the mouse (the canvas' parent)
    this.onAction = onAction;
    this.keys = new Set();
    this.lookX = 0; // radians to turn, gathered since the last frame
    this.lookY = 0;
    this.wheel = 0;
    this.locked = false;
    this.sensitivity = 0.0022;
    this.invertY = false;
    this.stick = { x: 0, y: 0 }; // touch joystick, -1..1
    this.touchRise = 0;
    this.touch = typeof window !== "undefined" && window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
    this._drag = null;
    this._pads = {};
    this._off = [];
    this._listen();
  }

  _on(target, type, fn, opts) {
    target.addEventListener(type, fn, opts);
    this._off.push(() => target.removeEventListener(type, fn, opts));
  }

  _listen() {
    const s = this.surface;
    this._on(window, "keydown", (e) => {
      if (typing(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (MOVE_KEYS[e.code] || e.code === "Space" || e.code.startsWith("Shift") || e.code === "KeyQ" || e.code === "KeyC") {
        this.keys.add(e.code);
        e.preventDefault();
        if (e.code === "Space" && !e.repeat) this.onAction("jump");
        return;
      }
      const action = ACTION_KEYS[e.code];
      if (action && !e.repeat) {
        this.onAction(action);
        e.preventDefault();
      }
      if ((e.code === "Equal" || e.code === "NumpadAdd") && !e.repeat) this.wheel -= 1;
      if ((e.code === "Minus" || e.code === "NumpadSubtract") && !e.repeat) this.wheel += 1;
    });
    this._on(window, "keyup", (e) => this.keys.delete(e.code));
    this._on(window, "blur", () => this.keys.clear());

    this._on(document, "pointerlockchange", () => {
      const was = this.locked;
      this.locked = document.pointerLockElement === s;
      if (was !== this.locked) this.onAction(this.locked ? "locked" : "unlocked");
    });
    this._on(document, "mousemove", (e) => {
      if (!this.locked) return;
      this.lookX -= e.movementX * this.sensitivity;
      this.lookY -= e.movementY * this.sensitivity * (this.invertY ? -1 : 1);
    });
    this._on(s, "pointerdown", (e) => {
      if (this.locked) {
        if (e.button === 0) this.onAction("interact");
        return;
      }
      this._drag = { id: e.pointerId, x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY, type: e.pointerType, moved: false, t: performance.now() };
    });
    this._on(window, "pointermove", (e) => {
      const d = this._drag;
      if (!d || d.id !== e.pointerId || this._stickId === e.pointerId) return;
      const dx = e.clientX - d.x, dy = e.clientY - d.y;
      d.x = e.clientX;
      d.y = e.clientY;
      if (Math.abs(e.clientX - d.sx) + Math.abs(e.clientY - d.sy) > 6) d.moved = true;
      if (d.moved) {
        const k = d.type === "touch" ? 0.006 : 0.004;
        this.lookX -= dx * k;
        this.lookY -= dy * k * (this.invertY ? -1 : 1);
      }
    });
    this._on(window, "pointerup", (e) => {
      const d = this._drag;
      if (!d || d.id !== e.pointerId) return;
      this._drag = null;
      if (d.moved) return;
      // A tap or click without dragging: touch picks what is there, a mouse starts looking.
      if (d.type === "touch") this.onAction("pick", { x: e.clientX, y: e.clientY });
      else if (e.button === 0) this.onAction("click", { x: e.clientX, y: e.clientY });
    });
    this._on(s, "wheel", (e) => {
      this.wheel += Math.sign(e.deltaY);
      e.preventDefault();
    }, { passive: false });
    this._on(s, "contextmenu", (e) => e.preventDefault());
  }

  lock() {
    if (this.touch || this.locked || !this.surface.requestPointerLock) return;
    try {
      const p = this.surface.requestPointerLock({ unadjustedMovement: true });
      if (p && p.catch) p.catch(() => { try { this.surface.requestPointerLock(); } catch (e) { /* not allowed here */ } });
    } catch (e) {
      /* not allowed here (e.g. a sandboxed frame): dragging still looks around */
    }
  }

  unlock() {
    if (this.locked && document.exitPointerLock) document.exitPointerLock();
  }

  // A touch stick (the HUD draws it): x right, y forward, -1..1.
  setStick(x, y, id) {
    this.stick.x = x;
    this.stick.y = y;
    this._stickId = id;
  }

  // The numbers for this frame; look and wheel are used up.
  read(dt) {
    const k = this.keys;
    let forward = 0, strafe = 0;
    for (const code of k) {
      const m = MOVE_KEYS[code];
      if (m) {
        if (m[0] === "forward") forward += m[1];
        else strafe += m[1];
      }
    }
    forward = Math.max(-1, Math.min(1, forward + this.stick.y));
    strafe = Math.max(-1, Math.min(1, strafe + this.stick.x));
    const shift = k.has("ShiftLeft") || k.has("ShiftRight");
    let rise = (k.has("Space") ? 1 : 0) - (shift || k.has("KeyQ") || k.has("KeyC") ? 1 : 0) + this.touchRise;
    let lookX = this.lookX, lookY = this.lookY;
    let run = shift;
    let jump = k.has("Space") || this.touchRise > 0;

    const pad = this._pad();
    if (pad) {
      const dead = (v) => (Math.abs(v) < 0.15 ? 0 : v);
      strafe += dead(pad.axes[0] || 0);
      forward -= dead(pad.axes[1] || 0);
      lookX -= dead(pad.axes[2] || 0) * 2.6 * dt;
      lookY -= dead(pad.axes[3] || 0) * 2.0 * dt * (this.invertY ? -1 : 1);
      const btn = (i) => (pad.buttons[i] ? pad.buttons[i].value || (pad.buttons[i].pressed ? 1 : 0) : 0);
      rise += btn(0) + btn(7) - btn(1) - btn(6);
      jump = jump || btn(0) > 0.5;
      run = run || btn(10) > 0.5;
      this._edge(pad, 3, "mode");
      this._edge(pad, 2, "interact");
    }
    this.lookX = 0;
    this.lookY = 0;
    const wheel = this.wheel;
    this.wheel = 0;
    return {
      forward: Math.max(-1, Math.min(1, forward)),
      strafe: Math.max(-1, Math.min(1, strafe)),
      rise: Math.max(-1, Math.min(1, rise)),
      run, jump, lookX, lookY, wheel,
      // Shift is "down" for the drone, so it doesn't make it run.
      shift,
    };
  }

  _pad() {
    if (!navigator.getGamepads) return null;
    for (const pad of navigator.getGamepads()) if (pad && pad.connected && pad.mapping === "standard") return pad;
    return null;
  }

  _edge(pad, i, action) {
    const down = !!(pad.buttons[i] && pad.buttons[i].pressed);
    const key = `${pad.index}:${i}`;
    if (down && !this._pads[key]) this.onAction(action);
    this._pads[key] = down;
  }

  dispose() {
    this.unlock();
    this._off.forEach((off) => off());
    this._off = [];
  }
}
