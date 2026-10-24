// What is drawn over the 3D view: the crosshair and what it points at, walk / drone and the
// drone's readings, the keys, models still loading, the map, the people here (a click flies to
// them) and, on touch screens, a stick and buttons.

import { initials } from "./people.js";

function el(tag, cls, parent, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

export class Hud {
  constructor(root, { labels, touch, onMode, onFollow, onStick, onRise, onAction }) {
    this.labels = labels || {};
    this.touch = touch;
    this.root = el("div", "rm-hud", root);
    this.fade = el("div", "rm-fade", this.root);
    this.cross = el("div", "rm-cross", this.root);
    this.target = el("div", "rm-target", this.root);
    this.targetTitle = el("div", "rm-target-title", this.target);
    this.targetHint = el("div", "rm-target-hint", this.target);

    const bottom = el("div", "rm-bottom", this.root);
    this.tele = el("div", "rm-tele", bottom);
    const modes = el("div", "rm-modes", bottom);
    this.walkBtn = el("button", "rm-mode-btn", modes);
    this.flyBtn = el("button", "rm-mode-btn", modes);
    this.walkBtn.type = this.flyBtn.type = "button";
    this.walkBtn.id = "rm-walk";
    this.flyBtn.id = "rm-fly";
    this.walkBtn.addEventListener("click", (e) => { e.stopPropagation(); onMode("walk"); });
    this.flyBtn.addEventListener("click", (e) => { e.stopPropagation(); onMode("fly"); });
    for (const b of [this.walkBtn, this.flyBtn]) b.addEventListener("pointerdown", (e) => e.stopPropagation());
    this.flags = el("div", "rm-flags", bottom);

    this.hint = el("div", "rm-hint", this.root);
    this.help = el("div", "rm-help", this.root);
    this.loading = el("div", "rm-loading", this.root);
    this.map = el("canvas", "rm-map", this.root);
    this.map.width = this.map.height = 2 * 168;
    this.people = el("div", "rm-people", this.root);
    this.people.addEventListener("pointerdown", (e) => e.stopPropagation());
    this.onFollow = onFollow;
    this.notice = el("div", "rm-notice", this.root);

    if (touch) this._touch(onStick, onRise, onAction);
    this.root.classList.toggle("is-touch", !!touch);
    this.setLabels(this.labels);
  }

  t(key, fallback) {
    return this.labels[key] || fallback;
  }

  setLabels(labels) {
    this.labels = labels || {};
    this.walkBtn.textContent = this.t("walk", "Walk");
    this.flyBtn.textContent = this.t("fly", "Drone");
    this.walkBtn.title = this.flyBtn.title = this.t("mode_title", "F switches between walking and flying");
    const keys = this.touch ? [] : [
      ["W A S D", this.t("k_move", "move")],
      ["Mouse", this.t("k_look", "look around")],
      ["Space", this.t("k_jump", "jump · drone: up")],
      ["Shift", this.t("k_run", "run · drone: down")],
      ["F", this.t("k_mode", "walk / drone")],
      ["E", this.t("k_open", "details of what you look at")],
      ["Wheel", this.t("k_speed", "drone speed")],
      ["G", this.t("k_ghost", "drone through walls")],
      ["L", this.t("k_light", "torch")],
      ["T", this.t("k_sun", "the sun: morning, day, evening")],
      ["Esc", this.t("k_esc", "free the mouse")],
    ];
    this.hint.textContent = this.touch ? this.t("touch_hint", "Drag to look, use the stick to move") : this.t("click_to_look", "Click the view to look around");
    this.help.innerHTML = "";
    const grid = el("div", "rm-help-keys", this.help);
    for (const [k, v] of keys) {
      el("kbd", "", grid, k);
      el("span", "", grid, v);
    }
  }

  setMode(mode, ghost, light, sun) {
    this.walkBtn.classList.toggle("is-on", mode === "walk");
    this.flyBtn.classList.toggle("is-on", mode === "fly");
    const flags = [];
    if (mode === "fly" && ghost) flags.push(this.t("ghost", "Ghost: through walls"));
    if (light) flags.push(this.t("light", "Torch on"));
    if (sun === "morning") flags.push(this.t("sun_morning", "Morning sun"));
    if (sun === "evening") flags.push(this.t("sun_evening", "Evening sun"));
    this.flags.textContent = flags.join(" · ");
    this.root.dataset.mode = mode;
  }

  setLocked(locked) {
    this.root.classList.toggle("is-locked", locked);
  }

  // The "click to look around" hint (while the mouse is free).
  showHelp(show) {
    this.root.classList.toggle("show-help", show);
  }

  // The list of keys.
  showKeys(show) {
    this.root.classList.toggle("show-keys", show);
  }

  telemetry(player) {
    if (player.mode !== "fly") {
      this.tele.textContent = "";
      return;
    }
    let deg = Math.round(((-player.yaw * 180) / Math.PI) % 360);
    if (deg < 0) deg += 360;
    const dir = COMPASS[Math.round(deg / 45) % 8];
    const speed = Math.hypot(player.velocity.x, player.velocity.y, player.velocity.z);
    this.tele.textContent = `${this.t("alt", "ALT")} ${player.altitude.toFixed(1)} m   ${speed.toFixed(1)} / ${player.flySpeed} m/s   ${deg}° ${dir}`;
  }

  aim(thing, hint) {
    if (!thing) {
      this.target.classList.remove("is-on");
      return;
    }
    this.targetTitle.textContent = thing.data.title;
    this.targetHint.textContent = hint;
    this.target.classList.add("is-on");
  }

  setLoading(rows) {
    this.loading.innerHTML = "";
    for (const r of rows) {
      const row = el("div", "rm-loading-row", this.loading);
      el("span", "rm-loading-name", row, r.title);
      const bar = el("span", "rm-loading-bar", row);
      el("i", "", bar).style.width = `${Math.round(r.progress * 100)}%`;
    }
  }

  setPeople(list, me) {
    this.people.innerHTML = "";
    for (const p of list) {
      if (p.id === me) continue;
      const chip = el("button", "rm-chip", this.people);
      chip.type = "button";
      chip.style.setProperty("--c", p.color);
      chip.title = this.t("follow", "Go to {name}").replace("{name}", p.name);
      chip.dataset.peer = p.id;
      const face = el("span", "rm-chip-face", chip);
      if (p.avatar) {
        const img = el("img", "", face);
        img.src = p.avatar;
        img.alt = "";
      } else {
        face.textContent = initials(p.name);
      }
      el("span", "rm-chip-name", chip, p.name);
      el("span", "rm-chip-mode", chip, p.mode === "fly" ? "✈" : "");
      chip.addEventListener("click", (e) => {
        e.stopPropagation();
        this.onFollow(p.id);
      });
    }
  }

  say(text, ms = 2600) {
    this.notice.textContent = text;
    this.notice.classList.add("is-on");
    clearTimeout(this._noticeTimer);
    this._noticeTimer = setTimeout(() => this.notice.classList.remove("is-on"), ms);
  }

  flash() {
    this.fade.classList.remove("is-on");
    void this.fade.offsetWidth;
    this.fade.classList.add("is-on");
  }

  // The map: north up, around the person; things as their footprints, people as dots.
  drawMap(player, things, people, me) {
    const c = this.map, g = c.getContext("2d");
    const S = c.width, R = this._mapRange || 120;
    g.clearRect(0, 0, S, S);
    g.fillStyle = "rgba(15,23,42,0.62)";
    g.beginPath();
    g.arc(S / 2, S / 2, S / 2, 0, Math.PI * 2);
    g.fill();
    g.save();
    g.beginPath();
    g.arc(S / 2, S / 2, S / 2 - 2, 0, Math.PI * 2);
    g.clip();
    const k = S / 2 / R;
    const px = player.position.x, pz = player.position.z;
    const sx = (x) => S / 2 + (x - px) * k;
    const sy = (z) => S / 2 + (z - pz) * k;
    for (const t of things) {
      const d = t.data;
      g.fillStyle = t.status === "ready" ? "rgba(226,232,240,0.85)" : "rgba(148,163,184,0.5)";
      const w = Math.max(3, d.w * k), h = Math.max(3, d.d * k);
      g.fillRect(sx(d.x) - w / 2, sy(d.z) - h / 2, w, h);
    }
    for (const p of people) {
      if (p.id === me || !p.p) continue;
      g.fillStyle = p.color;
      g.beginPath();
      g.arc(sx(p.p[0]), sy(p.p[2]), 6, 0, Math.PI * 2);
      g.fill();
    }
    g.restore();
    // Me: an arrow pointing where I look.
    g.save();
    g.translate(S / 2, S / 2);
    g.rotate(-player.yaw);
    g.fillStyle = "#2dd4bf";
    g.beginPath();
    g.moveTo(0, -13);
    g.lineTo(9, 10);
    g.lineTo(0, 5);
    g.lineTo(-9, 10);
    g.closePath();
    g.fill();
    g.restore();
    g.fillStyle = "#e2e8f0";
    g.font = "600 22px system-ui, sans-serif";
    g.textAlign = "center";
    g.fillText("N", S / 2, 26);
  }

  setMapRange(r) {
    this._mapRange = r;
  }

  _touch(onStick, onRise, onAction) {
    const pad = el("div", "rm-stick", this.root);
    const knob = el("div", "rm-knob", pad);
    let id = null, cx = 0, cy = 0;
    const R = 56;
    const move = (e) => {
      if (e.pointerId !== id) return;
      let dx = e.clientX - cx, dy = e.clientY - cy;
      const len = Math.hypot(dx, dy);
      if (len > R) { dx = (dx / len) * R; dy = (dy / len) * R; }
      knob.style.transform = `translate(${dx}px, ${dy}px)`;
      onStick(dx / R, -dy / R, id);
    };
    const end = (e) => {
      if (e.pointerId !== id) return;
      id = null;
      knob.style.transform = "";
      onStick(0, 0, null);
    };
    pad.addEventListener("pointerdown", (e) => {
      e.stopPropagation();
      e.preventDefault();
      const r = pad.getBoundingClientRect();
      id = e.pointerId;
      cx = r.left + r.width / 2;
      cy = r.top + r.height / 2;
      pad.setPointerCapture(id);
      move(e);
    });
    pad.addEventListener("pointermove", move);
    pad.addEventListener("pointerup", end);
    pad.addEventListener("pointercancel", end);

    const buttons = el("div", "rm-touch-btns", this.root);
    const hold = (label, value) => {
      const b = el("button", "rm-touch-btn", buttons, label);
      b.type = "button";
      const off = () => onRise(0);
      b.addEventListener("pointerdown", (e) => { e.stopPropagation(); e.preventDefault(); onRise(value); });
      b.addEventListener("pointerup", off);
      b.addEventListener("pointercancel", off);
      b.addEventListener("pointerleave", off);
      return b;
    };
    hold("▲", 1);
    hold("▼", -1);
    const mode = el("button", "rm-touch-btn", buttons, "✈");
    mode.type = "button";
    mode.addEventListener("pointerdown", (e) => { e.stopPropagation(); e.preventDefault(); onAction("mode"); });
  }

  dispose() {
    clearTimeout(this._noticeTimer);
    this.root.remove();
  }
}
