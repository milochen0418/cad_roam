// Pictures for an AI (cad_roam/eyes.py, asked over the people socket): the model seen from a place,
// at a time of the day, drawn as this page draws it (the sun and its shadows, the light inside,
// eyes used to the dark), without moving your own view.
//
// A tab in the background draws nothing (no frames; timers wait a second or a minute), so what a
// picture needs is done here, when it is asked for, waiting only on the network and the GPU: the
// place loaded again when the server has a newer one (the model was rebuilt), its model, its light
// worked out for that time (light.js settle). The picture is drawn on this page's own canvas, at its
// size, and read back at once: the page shows your view again before anything is seen.
//
// The sun stays at the picture's time a moment longer (the next picture of a tour finds its light
// worked out), then goes back to yours.

import * as THREE from "three";

const JPEG = 0.85;
// After an AI's last picture, the sun goes back to your time (ms).
const BACK = 1500;
// A picture's pixels this dark (or this bright), 0 to 255, count as nearly black (white).
const DARK = 25, BRIGHT = 245;

class Refused extends Error {
  constructor(text, why) {
    super(text);
    this.why = why;
  }
}

const round = (v, n = 2) => Math.round(v * 10 ** n) / 10 ** n;

// How bright the pixels are (rows from readPixels): the mean, and the shares nearly black and white.
function brightness(px) {
  let sum = 0, dark = 0, bright = 0;
  const n = px.length / 4;
  for (let i = 0; i < px.length; i += 4) {
    const l = 0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2];
    sum += l;
    if (l < DARK) dark++;
    else if (l > BRIGHT) bright++;
  }
  return { mean: Math.round(sum / n), dark: round(dark / n), bright: round(bright / n) };
}

// readPixels' rows (bottom up) as a JPEG, base64.
async function jpeg(px, w, h) {
  const rows = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) rows.set(px.subarray((h - 1 - y) * w * 4, (h - y) * w * 4), y * w * 4);
  const canvas = new OffscreenCanvas(w, h);
  canvas.getContext("2d").putImageData(new ImageData(rows, w, h), 0, 0);
  const blob = await canvas.convertToBlob({ type: "image/jpeg", quality: JPEG });
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let text = "";
  for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(text);
}

export class Eyes {
  constructor(engine) {
    this.engine = engine;
    this.camera = new THREE.PerspectiveCamera(72, 1.6, 0.05, 30000);
    this.camera.rotation.order = "YXZ";
    this.queue = Promise.resolve();
    this.busy = 0; // pictures being taken
    this.last = 0; // when the last one was taken (performance.now())
    this.time = null; // the sun's time of the pictures, while it isn't yours
    this.taken = 0;
  }

  // A request from the server ({rev, time, size, wait, by, view}); its answer, one at a time.
  shoot(req) {
    const run = this.queue.then(() => this._shoot(req));
    this.queue = run.catch(() => {});
    return run.then(
      (picture) => ({ ok: true, ...picture }),
      (e) => ({ ok: false, error: String((e && e.message) || e), why: (e && e.why) || "failed" }),
    );
  }

  async _shoot(req) {
    const e = this.engine;
    const until = performance.now() + Math.max(1, Number(req.wait) || 40) * 1000;
    this.busy++;
    try {
      await this._place(req.rev, until);
      const view = req.view || {};
      const at = new THREE.Vector3().fromArray(view.p || [0, 0, 0]);
      // The sun at the picture's time, its shadows round the place, and the light for it.
      this.time = Number.isFinite(req.time) ? req.time : e.time;
      const sun = e.sunTo(this.time);
      e.shade(at);
      const lit = await e.look.light.settle();
      if (e.disposed) throw new Refused("The CAD Roam page closed.", "gone");
      const [w, h] = (req.size || [1280, 800]).map((v) => Math.max(64, Math.min(2048, Math.round(v))));
      const shot = this._draw(view, w, h);
      const data = await jpeg(shot.pixels, w, h);
      this.last = performance.now();
      this.taken++;
      if (req.by) e.hud.say(e.hud.t("ai_picture", "{who} took a picture inside").replace("{who}", req.by), 3500);
      return {
        jpeg: data,
        info: {
          ...shot.info,
          lit,
          quality: e.quality,
          sun: { bearing: round(sun.bearing, 1), elevation: round(sun.elevation, 1) },
        },
      };
    } finally {
      this.busy--;
    }
  }

  // The place as the server has it (rev), with its model loaded, or why it can't be.
  async _place(rev, until) {
    const e = this.engine;
    for (;;) {
      if (e.disposed) throw new Refused("The CAD Roam page closed.", "gone");
      if (e.ready && !e.loadingWorld && rev && rev !== e.rev) await e.reload();
      const current = e.ready && !e.loadingWorld && (!rev || rev === e.rev);
      const t = [...e.things.values()][0];
      if (current) {
        if (!t) throw new Refused("The model has no build to show yet: build it in Codoc in CAD first.", "none");
        if (t.status === "failed") throw new Refused("The CAD Roam page could not load the model.", "failed");
        if (t.status === "skipped") {
          throw new Refused(
            `The person on the CAD Roam page chose not to load this big model (${t.data.tris.toLocaleString("en")} triangles). Ask them to load it (the button at the top left), then call again.`,
            "big",
          );
        }
        if (t.status === "waiting" && t.data.big && e.bigWanted(t.key) !== true) {
          throw new Refused(
            `The model is big (${t.data.tris.toLocaleString("en")} triangles), so the CAD Roam page asks the person whether to load it. Ask them to press "Load it", then call again.`,
            "big",
          );
        }
        if (t.status === "ready" && !e.replacing.size) return t;
      }
      if (performance.now() >= until) {
        const loading = t && t.status === "loading" ? ` (${Math.round(100 * t.progress)}% downloaded)` : "";
        throw new Refused(`The CAD Roam page is still loading the model${loading}: call again in a moment.`, "loading");
      }
      await e.changed(until);
    }
  }

  // Draws the view ({p, yaw, pitch, fov}: world) on the page's canvas at w x h and reads it back.
  _draw(view, w, h) {
    const e = this.engine, r = e.renderer, cam = this.camera;
    cam.fov = view.fov || 72;
    cam.aspect = w / h;
    cam.updateProjectionMatrix();
    cam.position.fromArray(view.p || [0, 0, 0]);
    cam.rotation.set(view.pitch || 0, view.yaw || 0, 0, "YXZ");
    cam.updateMatrixWorld(true);
    e.shade(cam.position);
    // The glass as the sun sees it from there (no eyes used to the dark yet: they are measured here).
    e.look.frame(null, 0);
    const eye = e.look.light.eyeAt(cam.position);
    // Neither your figure (seen from behind) nor your torch in it, nor the others' torches.
    const me = e.view.me && e.view.me.group, shown = !!(me && me.visible), torch = e.torch.intensity;
    if (me) me.visible = false;
    e.torch.intensity = 0;
    const others = e.people.dim();
    const exposure = r.toneMappingExposure, ratio = r.getPixelRatio();
    const gl = r.getContext(), pixels = new Uint8Array(w * h * 4);
    try {
      r.toneMappingExposure = e.exposure * eye.brightness;
      r.setPixelRatio(1);
      r.setSize(w, h, false);
      r.render(e.scene, cam);
      gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    } finally {
      r.setPixelRatio(ratio);
      e.resize();
      r.toneMappingExposure = exposure;
      e.torch.intensity = torch;
      others();
      if (me) me.visible = shown;
    }
    return {
      pixels,
      info: {
        eyes: round(eye.brightness),
        light: eye.light === null ? null : round(eye.light, 4),
        ...brightness(pixels),
        ahead: this._ahead(cam),
      },
    };
  }

  // How far the first surface straight ahead is (metres), null when nothing is.
  _ahead(cam) {
    const ray = new THREE.Raycaster();
    ray.firstHitOnly = true;
    ray.far = 5000;
    ray.setFromCamera(new THREE.Vector2(0, 0), cam);
    const hit = ray.intersectObjects(this.engine.pickables(), false)[0];
    return hit ? round(hit.distance) : null;
  }

  // Each frame: once no picture has been taken for a moment, the sun goes back to your time.
  frame() {
    if (this.time === null || this.busy || performance.now() - this.last < BACK) return;
    this.time = null;
    this.engine.sunTo(this.engine.time);
  }
}
