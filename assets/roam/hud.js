// What is drawn over the 3D view: the crosshair and what it points at, walk / drone, your eyes /
// from behind, the drone's readings, the sun's time, the keys, models still loading (or left
// unloaded), the question before a big model loads, the map, the people here (a click flies to
// them, the button beside opens their profile) and, on touch screens, a stick and buttons.

import { initials } from "./people.js";

function el(tag, cls, parent, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}

// Bytes as people read them: "22 KB", "9.3 MB", "710 MB", "1.4 GB".
function bytes(n) {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n < 1e6) return `${Math.max(1, Math.round(n / 1e3))} KB`;
  const mb = n / 1e6;
  return mb >= 10 ? `${Number(mb.toPrecision(2))} MB` : `${mb.toFixed(1)} MB`;
}

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
// Someone's profile (Lucide's "user-round").
const PROFILE_ICON = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/></svg>';

// A time of the day (hours) as hh:mm.
export function clock(hours) {
  const m = Math.round(hours * 60);
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

export class Hud {
  constructor(root, { labels, touch, onMode, onView, onFollow, onProfile, onStick, onRise, onAction, sunTimes, onSunTime }) {
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
    const row = el("div", "rm-row", bottom);
    const modes = el("div", "rm-modes", row);
    this.walkBtn = el("button", "rm-mode-btn", modes);
    this.flyBtn = el("button", "rm-mode-btn", modes);
    this.walkBtn.type = this.flyBtn.type = "button";
    this.walkBtn.id = "rm-walk";
    this.flyBtn.id = "rm-fly";
    this.walkBtn.addEventListener("click", (e) => { e.stopPropagation(); onMode("walk"); });
    this.flyBtn.addEventListener("click", (e) => { e.stopPropagation(); onMode("fly"); });
    // Through your eyes, or yourself from a little behind (view.js).
    const views = el("div", "rm-modes", row);
    this.eyesBtn = el("button", "rm-mode-btn", views);
    this.behindBtn = el("button", "rm-mode-btn", views);
    this.eyesBtn.type = this.behindBtn.type = "button";
    this.eyesBtn.id = "rm-eyes";
    this.behindBtn.id = "rm-behind";
    this.eyesBtn.addEventListener("click", (e) => { e.stopPropagation(); onView("eyes"); });
    this.behindBtn.addEventListener("click", (e) => { e.stopPropagation(); onView("behind"); });
    for (const b of [this.walkBtn, this.flyBtn, this.eyesBtn, this.behindBtn]) b.addEventListener("pointerdown", (e) => e.stopPropagation());
    // The sun's time of day: dragged, the sun moves along its path (engine.js).
    this.sun = el("label", "rm-sun", bottom);
    el("span", "rm-sun-icon", this.sun, "☀");
    this.sunRange = el("input", "rm-sun-range", this.sun);
    Object.assign(this.sunRange, { type: "range", min: String(sunTimes.first), max: String(sunTimes.last), step: String(1 / 12) });
    this.sunTime = el("span", "rm-sun-time", this.sun);
    this.sun.addEventListener("pointerdown", (e) => e.stopPropagation());
    this.sunRange.addEventListener("input", () => onSunTime(Number(this.sunRange.value)));
    // Let go of, it gives the keys back to walking.
    this.sunRange.addEventListener("pointerup", () => this.sunRange.blur());
    this.flags = el("div", "rm-flags", bottom);

    this.hint = el("div", "rm-hint", this.root);
    this.help = el("div", "rm-help", this.root);
    this.loading = el("div", "rm-loading", this.root);
    this.map = el("canvas", "rm-map", this.root);
    this.map.width = this.map.height = 2 * 168;
    this.people = el("div", "rm-people", this.root);
    this.people.addEventListener("pointerdown", (e) => e.stopPropagation());
    this.onFollow = onFollow;
    this.onProfile = onProfile;
    this.onAction = onAction;
    this.notice = el("div", "rm-notice", this.root);

    // Before a big model loads (askBig): what it costs, load it or not.
    this.ask = el("div", "rm-ask", this.root);
    this.ask.setAttribute("role", "dialog");
    this.ask.setAttribute("aria-modal", "true");
    this.ask.setAttribute("aria-labelledby", "rm-ask-title");
    this.ask.addEventListener("pointerdown", (e) => e.stopPropagation());
    const box = el("div", "rm-ask-box", this.ask);
    this.askTitle = el("h2", "rm-ask-title", box);
    this.askTitle.id = "rm-ask-title";
    this.askBody = el("p", "rm-ask-body", box);
    this.askCosts = el("dl", "rm-ask-costs", box);
    this.askWarn = el("p", "rm-ask-warn", box);
    const buttons = el("div", "rm-ask-btns", box);
    this.askSkip = el("button", "rm-ask-btn", buttons);
    this.askLoad = el("button", "rm-ask-btn is-main", buttons);
    this.askSkip.type = this.askLoad.type = "button";
    this.askSkip.id = "rm-big-skip";
    this.askLoad.id = "rm-big-load";
    this.askSkip.addEventListener("click", () => this._answerBig(false));
    this.askLoad.addEventListener("click", () => this._answerBig(true));
    this.askLater = el("p", "rm-ask-later", box);
    this._big = null;
    this._bigAnswer = null;

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
    this.eyesBtn.textContent = this.t("view_eyes", "Eyes");
    this.behindBtn.textContent = this.t("view_behind", "Behind");
    this.eyesBtn.title = this.behindBtn.title = this.t("view_title", "V switches between your own eyes and seeing yourself from behind");
    this.sun.title = this.t("sun_time", "The sun's time of day (T: morning, day, evening)");
    this.sunRange.setAttribute("aria-label", this.sun.title);
    const keys = this.touch ? [] : [
      ["W A S D", this.t("k_move", "move")],
      ["Mouse", this.t("k_look", "look around")],
      ["Space", this.t("k_jump", "jump · drone: up")],
      ["Shift", this.t("k_run", "run · drone: down")],
      ["F", this.t("k_mode", "walk / drone")],
      ["V", this.t("k_view", "your eyes / from behind")],
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
    this._fillBig();
  }

  // A model with more triangles than the server's limit ({key, mesh, title, tris, limit, bytes,
  // memory}): what loading it costs, and two buttons; answer(true | false) when one is pressed.
  // Asked again about the same build, only answer is replaced.
  askBig(big, answer) {
    this._bigAnswer = answer;
    if (this._big && this._big.key === big.key && this._big.mesh === big.mesh) return;
    this._big = big;
    this._fillBig();
    this.root.classList.add("is-asking");
  }

  // Takes the question away (its model is gone); with a key, only when it is about that model.
  closeBig(key) {
    if (!this._big || (key && this._big.key !== key)) return;
    this._big = this._bigAnswer = null;
    this.root.classList.remove("is-asking");
  }

  _answerBig(load) {
    const answer = this._bigAnswer;
    this.closeBig();
    if (answer) answer(load);
  }

  _fillBig() {
    const b = this._big;
    if (!b) return;
    const times = b.tris / b.limit;
    this.askTitle.textContent = this.t("big_title", "This model is big");
    this.askBody.textContent = this.t("big_body", "{title} has {tris} triangles, {times} times the suggested limit of {limit}.")
      .replace("{title}", b.title)
      .replace("{tris}", b.tris.toLocaleString("en-US"))
      .replace("{times}", times < 10 ? times.toFixed(1) : String(Math.round(times)))
      .replace("{limit}", b.limit.toLocaleString("en-US"));
    this.askCosts.innerHTML = "";
    for (const [key, fallback, n] of [["big_download", "Download", b.bytes], ["big_memory", "Memory", b.memory]]) {
      el("dt", "", this.askCosts, this.t(key, fallback));
      el("dd", "", this.askCosts, this.t("big_about", "about {n}").replace("{n}", bytes(n)));
    }
    this.askWarn.textContent = this.t("big_warn", "A phone or an older computer may get very slow, or the tab may crash.");
    this.askSkip.textContent = this.t("big_skip", "Don't load");
    this.askLoad.textContent = this.t("big_load", "Load it");
    this.askLater.textContent = this.t("big_later", "Not loaded, it can still be loaded from the top left.");
  }

  setMode(mode, ghost, light) {
    this.walkBtn.classList.toggle("is-on", mode === "walk");
    this.flyBtn.classList.toggle("is-on", mode === "fly");
    const flags = [];
    if (mode === "fly" && ghost) flags.push(this.t("ghost", "Ghost: through walls"));
    if (light) flags.push(this.t("light", "Torch on"));
    this.flags.textContent = flags.join(" · ");
    this.root.dataset.mode = mode;
  }

  setView(view) {
    this.eyesBtn.classList.toggle("is-on", view === "eyes");
    this.behindBtn.classList.toggle("is-on", view === "behind");
    this.root.dataset.view = view;
  }

  // The sun's time (hours) on the slider and as hh:mm.
  setSunTime(hours) {
    this.sunRange.value = String(hours);
    this.sunTime.textContent = clock(hours);
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

  // Models loading, with their progress, and big ones left unloaded, with a button to load them.
  setLoading(rows) {
    this.loading.innerHTML = "";
    for (const r of rows) {
      const row = el("div", "rm-loading-row", this.loading);
      el("span", "rm-loading-name", row, r.title);
      if (r.skipped) {
        el("span", "rm-loading-note", row, r.newer ? this.t("big_newer", "its new build isn't loaded") : this.t("not_loaded", "not loaded"));
        const load = el("button", "rm-loading-btn", row, this.t("big_load", "Load it"));
        load.type = "button";
        load.id = "rm-big-later";
        load.addEventListener("pointerdown", (e) => e.stopPropagation());
        load.addEventListener("click", (e) => {
          e.stopPropagation();
          this.onAction("load_big", r.key);
        });
        continue;
      }
      const bar = el("span", "rm-loading-bar", row);
      el("i", "", bar).style.width = `${Math.round(r.progress * 100)}%`;
    }
  }

  // The others here: a chip each (a click flies to them), and beside it a button for the profile of
  // someone signed in.
  setPeople(list, me) {
    this.people.innerHTML = "";
    for (const p of list) {
      if (p.id === me) continue;
      const row = el("div", "rm-chip-row", this.people);
      const chip = el("button", "rm-chip", row);
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
      if (!p.profile) continue;
      const profile = el("button", "rm-chip-profile", row);
      profile.type = "button";
      profile.style.setProperty("--c", p.color);
      profile.dataset.peer = p.id;
      profile.title = this.t("profile_of", "{name}'s profile").replace("{name}", p.name);
      profile.setAttribute("aria-label", profile.title);
      profile.innerHTML = PROFILE_ICON;
      profile.addEventListener("click", (e) => {
        e.stopPropagation();
        this.onProfile(p.id);
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
