// The light inside a model, as it falls on everything in and round it: the sky's light coming in
// through its openings and its glass (in the glass's colours), the light of its lamps (parts that
// glow), and the light its floors, walls and vaults throw back, which is most of what lights an
// inside. Without it the sky lit an inside as much as the outside, or, held back under a roof, left
// a church dark however many lamps and windows it had.
//
// The model is cut into cells: a grid over it and a little round it, of about CELLS cells (about
// 2 m across over the Sagrada Família, never under CELL_MIN). When it loads, its surfaces are added
// up per cell, here in the browser: how much of the cell they block along each axis (how many of
// 4 x 4 lines through it along that axis meet one: a wall across the cell blocks it all, a column as
// much as it covers), their colour, the light they give, and the glass in the cell, as the colour
// it lets through. Coarser grids (each cell 2 x 2 x 2 of the one before) say the same of bigger
// blocks; along an axis, a block lets through what gets through both its halves, so a thin wall far
// away still stops the light.
//
// The GPU then works out, at the middle of every cell, the light coming from all round, along
// CONES cones: each goes out until something stops it, the farther the wider (so it reads the
// coarser grids). On its way it picks up the light of lamps, and the light thrown back by what it
// meets: the sunlight on it (from a picture of the model and of its glass seen from the sun) and
// the light the round before found there, on the side facing the cone. Where it gets out it gets
// the sky (or the ground), through the glass it crossed. What arrives is kept as a colour plus how
// much more of it comes from each side (spherical harmonics up to order 1), so a surface takes the
// light of the side it faces. Each round adds a bounce of the light; ROUNDS rounds are worked out a
// few layers of cells a frame, again when the sun moves, while the last finished round lights the
// picture.
//
// A surface takes the light of the cells round a point a little in front of it (so a wall is lit
// from its own side), leaving out cells inside something solid or with a wall across them (they
// have the light of both its sides). Away from the model the sky lights things as before.
//
// Indoors the view brightens, as eyes (or a camera) get used to the dark: by how much less light
// there is where you stand than out in the open, in the sky's and the sun's light.

import * as THREE from "three";

// At most this many cells (bigger ones for a bigger model), none smaller than CELL_MIN metres.
const CELLS = 1000000;
// About how much more memory the browser takes for a big model's light (all CELLS of it), while it
// is worked out (the Sagrada Família: 1.1 GB at its peak without it, 1.43 GB with it, on an M4 Mac).
export const LIGHT_BYTES = 350e6;
const CELL_MIN = 0.35;
// A model smaller than this (its longest side, metres) has no inside to light.
const MODEL_MIN = 3;
// The light a glowing part gives, against how bright it looks.
const LAMP_LIGHT = 3;
// How strongly a cell holds back the light crossing it along an axis is kept as a byte: what gets
// through is exp(-DEPTH * byte / 255), nothing at 255. Kept that way, not as what gets through, so
// that a wall blended between two grids (a cone reading a grid and the coarser one) still stops
// the light.
const DEPTH = 6;
const holds = (through) => Math.round((255 * Math.min(DEPTH, -Math.log(Math.max(through, 1e-6)))) / DEPTH);
const THROUGH = Float32Array.from({ length: 256 }, (_, b) => Math.exp((-DEPTH * b) / 255));
// How many of 16 bits are set.
const BITS = Uint8Array.from({ length: 65536 }, (_, m) => {
  let k = 0;
  for (; m; m &= m - 1) k++;
  return k;
});
// The cones the light is gathered along (all round a cell), how wide they are (the tangent of half
// their angle), how far apart their samples are (in their widths there), and at most how many.
const CONES = 16;
const CONE_TAN = 0.6;
const STEP = 0.7;
const STEPS = 20;
// The coarsest grid the cones read: each of its cells is 2^MAX_LOD cells of the finest across. A
// grid is a whole number of those across, so every coarser grid lines up with the finest one.
const MAX_LOD = 4;
const ALIGN = 2 ** MAX_LOD;
// Rounds of light thrown back; cells worked out per frame.
const ROUNDS = 4;
const PER_FRAME = 60000;
// The model and its glass seen from the sun, for the sunlight in the cells.
const SUN_MAP = 2048;
const GLASS_MAP = 1024;
// Eyes used to the dark: at most this many times brighter, as the open sky's light over the light
// where you stand to this power, in about this many seconds; how often it is looked at.
const ADAPT_MAX = 10;
const ADAPT_POWER = 0.85;
const ADAPT_TIME = 0.8;
const ADAPT_EVERY = 0.25;
// Light arrives smoothly: a new model's light fades in over this many seconds.
const FADE_TIME = 0.6;

// Gives way to the page for a moment. A message the page sends itself, not a timer: in a tab in the
// background timers wait a second (a minute, after a while), and an AI's picture (eyes.js) may need
// the light worked out there.
const waiting = [];
const channel = new MessageChannel();
channel.port1.onmessage = () => waiting.shift()?.();
export const pause = () => new Promise((resolve) => {
  waiting.push(resolve);
  channel.port2.postMessage(0);
});

// Directions spread evenly over the sphere (a Fibonacci spiral): as many point up as down, and
// they add up a sky's light on a floor (pi) exactly.
function coneDirections(n) {
  const out = [];
  const turn = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (2 * i + 1) / n, r = Math.sqrt(1 - y * y);
    out.push(new THREE.Vector3(Math.cos(i * turn) * r, y, Math.sin(i * turn) * r));
  }
  return out;
}

// The grid over a box of the world (metres), or null when there is nothing to light inside.
function gridOver(box) {
  const size = box.getSize(new THREE.Vector3());
  if (box.isEmpty() || Math.max(size.x, size.y, size.z) < MODEL_MIN) return null;
  const cell = Math.max(CELL_MIN, Math.cbrt(((size.x + 4) * (size.y + 4) * (size.z + 4)) / CELLS));
  // Three cells of open air round it (and over it: surfaces there fade to the sky's light), one
  // under the ground; a whole number of the coarsest cells (ALIGN).
  const min = box.min.clone().subScalar(3 * cell);
  min.y = Math.min(box.min.y, 0) - cell;
  const max = box.max.clone().addScalar(3 * cell);
  const dims = [max.x - min.x, max.y - min.y, max.z - min.z].map((d) => Math.ceil(d / cell / ALIGN) * ALIGN);
  return { min, cell, nx: dims[0], ny: dims[1], nz: dims[2] };
}

// The model's surfaces added up per cell, as the 3D textures' data (see the top). items:
// [{position, index, colour: [r, g, b], light: [r, g, b] | null, glass: [r, g, b] | null}], world
// coordinates, linear colours; light is a glowing part's colour times its strength, glass the
// colour a pane lets through. Gives way to the page now and then; null when `alive()` says the
// model went meanwhile.
//
// How much of a cell blocks the light along an axis is how many of 4 x 4 lines across it, along
// that axis, meet a surface in it: a wall across the cell (or the face of a thick one) meets them
// all, a column some, as much as it covers.
async function voxelize(items, grid, alive) {
  const { min, cell, nx, ny, nz } = grid;
  const n = nx * ny * nz, inv = 1 / cell;
  const dims = [nx, ny, nz], mins = [min.x, min.y, min.z], stride = [1, nx, nx * ny];
  const area = new Float32Array(n); // of solid surfaces
  const colour = new Float32Array(n * 3); // their colour x area
  let light = null; // light given x area (3), area of what gives it
  let glassArea = null; // of glass
  let tint = null; // colour let through x area
  // Per axis, the lines across each cell that meet a solid surface in it, or glass (16 bits).
  const blocks = [new Uint16Array(n), new Uint16Array(n), new Uint16Array(n)];
  let panes = null;
  let solid = true, rgb = null, glow = null;
  const tri = new Float64Array(9);
  const isub = 4 * inv, sub = cell / 4;

  const put = (c, w) => {
    const b = c * 3;
    if (solid) {
      area[c] += w;
      colour[b] += w * rgb[0];
      colour[b + 1] += w * rgb[1];
      colour[b + 2] += w * rgb[2];
    } else {
      glassArea[c] += w;
      tint[b] += w * rgb[0];
      tint[b + 1] += w * rgb[1];
      tint[b + 2] += w * rgb[2];
    }
    if (glow) {
      const a = c * 4;
      light[a] += w * glow[0];
      light[a + 1] += w * glow[1];
      light[a + 2] += w * glow[2];
      light[a + 3] += w;
    }
  };
  const cellOf = (x, y, z) => {
    const i = Math.min(nx - 1, Math.max(0, Math.floor((x - min.x) * inv)));
    const j = Math.min(ny - 1, Math.max(0, Math.floor((y - min.y) * inv)));
    const k = Math.min(nz - 1, Math.max(0, Math.floor((z - min.z) * inv)));
    return i + nx * (j + ny * k);
  };
  // The lines along axis `a` (4 x 4 across each cell) that meet the triangle in `tri`, marked in the
  // cell they meet it in.
  const cover = (marks, a, normal) => {
    if (Math.abs(normal) < 1e-9) return; // edge on
    const u = (a + 1) % 3, v = (a + 2) % 3;
    const pu = tri[u], pv = tri[v], qu = tri[3 + u], qv = tri[3 + v], ru = tri[6 + u], rv = tri[6 + v];
    const j0 = Math.max(0, Math.ceil((Math.min(pu, qu, ru) - mins[u]) * isub - 0.5));
    const j1 = Math.min(4 * dims[u] - 1, Math.floor((Math.max(pu, qu, ru) - mins[u]) * isub - 0.5));
    const k0 = Math.max(0, Math.ceil((Math.min(pv, qv, rv) - mins[v]) * isub - 0.5));
    const k1 = Math.min(4 * dims[v] - 1, Math.floor((Math.max(pv, qv, rv) - mins[v]) * isub - 0.5));
    if (j0 > j1 || k0 > k1) return;
    const d = (qu - pu) * (rv - pv) - (ru - pu) * (qv - pv);
    if (d === 0) return;
    const pa = tri[a], qa = tri[3 + a] - pa, ra = tri[6 + a] - pa;
    for (let k = k0; k <= k1; k++) {
      const sv = mins[v] + (k + 0.5) * sub - pv;
      for (let j = j0; j <= j1; j++) {
        const su = mins[u] + (j + 0.5) * sub - pu;
        const w1 = (su * (rv - pv) - (ru - pu) * sv) / d;
        const w2 = ((qu - pu) * sv - su * (qv - pv)) / d;
        if (w1 < 0 || w2 < 0 || w1 + w2 > 1) continue;
        const ia = Math.floor((pa + w1 * qa + w2 * ra - mins[a]) * inv);
        if (ia < 0 || ia >= dims[a]) continue;
        marks[ia * stride[a] + (j >> 2) * stride[u] + (k >> 2) * stride[v]] |= 1 << ((j & 3) + 4 * (k & 3));
      }
    }
  };

  let since = 0;
  for (const it of items) {
    solid = !it.glass;
    rgb = solid ? it.colour : it.glass;
    if (!solid) {
      glassArea ??= new Float32Array(n);
      tint ??= new Float32Array(n * 3);
      panes ??= [new Uint16Array(n), new Uint16Array(n), new Uint16Array(n)];
    }
    const marks = solid ? blocks : panes;
    glow = it.light;
    if (glow) light ??= new Float32Array(n * 4);
    const p = it.position, idx = it.index;
    const count = idx ? idx.length : p.length / 3;
    for (let t = 0; t < count; t += 3) {
      const i0 = (idx ? idx[t] : t) * 3, i1 = (idx ? idx[t + 1] : t + 1) * 3, i2 = (idx ? idx[t + 2] : t + 2) * 3;
      const x0 = p[i0], y0 = p[i0 + 1], z0 = p[i0 + 2];
      const ux = p[i1] - x0, uy = p[i1 + 1] - y0, uz = p[i1 + 2] - z0;
      const vx = p[i2] - x0, vy = p[i2 + 1] - y0, vz = p[i2 + 2] - z0;
      const cx = uy * vz - uz * vy, cy = uz * vx - ux * vz, cz = ux * vy - uy * vx;
      const len = Math.sqrt(cx * cx + cy * cy + cz * cz);
      if (!(len > 0)) continue;
      tri[0] = x0;
      tri[1] = y0;
      tri[2] = z0;
      tri[3] = x0 + ux;
      tri[4] = y0 + uy;
      tri[5] = z0 + uz;
      tri[6] = x0 + vx;
      tri[7] = y0 + vy;
      tri[8] = z0 + vz;
      cover(marks[0], 0, cx / len);
      cover(marks[1], 1, cy / len);
      cover(marks[2], 2, cz / len);
      // Its area (for colours and light) to the cells it is in.
      const surface = len / 2;
      const c0 = cellOf(x0, y0, z0);
      if (c0 === cellOf(tri[3], tri[4], tri[5]) && c0 === cellOf(tri[6], tri[7], tri[8])) {
        put(c0, surface);
      } else {
        // Across cells: shared out over points about half a cell apart, in strips along its
        // longest side (a long thin one gets a row of them).
        const lu = ux * ux + uy * uy + uz * uz, lv = vx * vx + vy * vy + vz * vz;
        const lw = (vx - ux) ** 2 + (vy - uy) ** 2 + (vz - uz) ** 2;
        // Its corners as a (the longest side from a to b) and c.
        let ax = x0, ay = y0, az = z0, bx = tri[3], by = tri[4], bz = tri[5], qx = tri[6], qy = tri[7], qz = tri[8];
        if (lv >= lu && lv >= lw) [bx, by, bz, qx, qy, qz] = [qx, qy, qz, bx, by, bz];
        else if (lw >= lu && lw >= lv) [ax, ay, az, qx, qy, qz] = [qx, qy, qz, ax, ay, az];
        const base = Math.sqrt(Math.max(lu, lv, lw)), h = cell / 2;
        const rows = Math.max(1, Math.ceil((2 * surface) / base / h));
        for (let r = 0; r < rows; r++) {
          const f = (r + 0.5) / rows, strip = surface * ((1 - r / rows) ** 2 - (1 - (r + 1) / rows) ** 2);
          const cols = Math.max(1, Math.ceil(((1 - f) * base) / h)), w = strip / cols;
          // The strip's middle line, from a + f (c - a) to b + f (c - b).
          const sx = ax + f * (qx - ax), sy = ay + f * (qy - ay), sz = az + f * (qz - az);
          const ex = bx + f * (qx - bx) - sx, ey = by + f * (qy - by) - sy, ez = bz + f * (qz - bz) - sz;
          for (let i = 0; i < cols; i++) {
            const g = (i + 0.5) / cols;
            put(cellOf(sx + g * ex, sy + g * ey, sz + g * ez), w);
          }
        }
      }
      if (++since === 100000) {
        since = 0;
        await pause();
        if (!alive()) return null;
      }
    }
  }
  await pause();
  if (!alive()) return null;

  // How strongly a cell holds back what crosses it along each axis (rgb: walls stop it, glass
  // colours it; a: its solid parts only, see DEPTH); the cells' colours (times how solid); the light
  // they give.
  const pass = [new Uint8Array(n * 4), new Uint8Array(n * 4), new Uint8Array(n * 4)];
  const matter = new Uint8Array(n * 4);
  const given = light ? new Uint16Array(n * 4) : null;
  const half = THREE.DataUtils.toHalfFloat, s2 = cell * cell;
  for (let c = 0; c < n; c++) {
    const a = c * 4, b = c * 3;
    let tr = 1, tg = 1, tb = 1;
    if (glassArea && glassArea[c] > 0) {
      tr = tint[b] / glassArea[c];
      tg = tint[b + 1] / glassArea[c];
      tb = tint[b + 2] / glassArea[c];
    }
    let most = 0;
    for (let axis = 0; axis < 3; axis++) {
      const blocked = BITS[blocks[axis][c]] / 16, g = panes ? BITS[panes[axis][c]] / 16 : 0;
      const open = 1 - blocked, out = pass[axis];
      out[a] = holds(open * (1 - g * (1 - tr)));
      out[a + 1] = holds(open * (1 - g * (1 - tg)));
      out[a + 2] = holds(open * (1 - g * (1 - tb)));
      out[a + 3] = holds(open);
      most = Math.max(most, blocked);
    }
    if (area[c] > 0 && most > 0) {
      matter[a] = Math.round(255 * Math.min(1, colour[b] / area[c]) * most);
      matter[a + 1] = Math.round(255 * Math.min(1, colour[b + 1] / area[c]) * most);
      matter[a + 2] = Math.round(255 * Math.min(1, colour[b + 2] / area[c]) * most);
      matter[a + 3] = Math.round(255 * most);
    }
    if (given && light[a + 3] > 0) {
      // Its light as seen from anywhere round: the area it shows is about a quarter of its surface.
      const la = light[a + 3], k = (Math.min(1, la / (4 * s2)) * LAMP_LIGHT) / la;
      given[a] = half(light[a] * k);
      given[a + 1] = half(light[a + 1] * k);
      given[a + 2] = half(light[a + 2] * k);
    }
  }
  return { pass, matter, given };
}

// The mip levels three.js gives a 3D texture of these sizes (and the GPU generates).
function levelsOf(nx, ny) {
  return Math.floor(Math.log2(Math.max(nx, ny))) + 1;
}

// Coarser grids of how strongly crossing a cell along `axis` holds the light back: each cell is
// 2 x 2 x 2 of the grid before, letting through, at each place across the axis, what gets through
// both of its halves along it, on average across.
function passLevels(base, nx, ny, nz, axis, levels) {
  const out = [];
  let w = nx, h = ny, d = nz, src = base;
  for (let l = 1; l < levels; l++) {
    const W = Math.max(1, w >> 1), H = Math.max(1, h >> 1), D = Math.max(1, d >> 1);
    const dst = new Uint8Array(W * H * D * 4);
    const size = [w, h, d], stride = [1, w, w * h];
    const o1 = (axis + 1) % 3, o2 = (axis + 2) % 3;
    for (let z = 0; z < D; z++) {
      for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
          const at = [2 * x, 2 * y, 2 * z];
          let r = 0, g = 0, b = 0, a = 0, count = 0;
          for (let i = 0; i < 2; i++) {
            for (let j = 0; j < 2; j++) {
              const p1 = at[o1] + i, p2 = at[o2] + j;
              if (p1 >= size[o1] || p2 >= size[o2]) continue;
              const f = (at[axis] * stride[axis] + p1 * stride[o1] + p2 * stride[o2]) * 4;
              let fr = THROUGH[src[f]], fg = THROUGH[src[f + 1]], fb = THROUGH[src[f + 2]], fa = THROUGH[src[f + 3]];
              if (at[axis] + 1 < size[axis]) {
                const s = f + stride[axis] * 4;
                fr *= THROUGH[src[s]];
                fg *= THROUGH[src[s + 1]];
                fb *= THROUGH[src[s + 2]];
                fa *= THROUGH[src[s + 3]];
              }
              r += fr;
              g += fg;
              b += fb;
              a += fa;
              count++;
            }
          }
          const o = (x + W * (y + H * z)) * 4;
          dst[o] = holds(r / count);
          dst[o + 1] = holds(g / count);
          dst[o + 2] = holds(b / count);
          dst[o + 3] = holds(a / count);
        }
      }
    }
    out.push({ data: dst, w: W, h: H, d: D });
    src = dst;
    w = W;
    h = H;
    d = D;
  }
  return out;
}

function volume(data, nx, ny, nz, type = THREE.UnsignedByteType) {
  const t = new THREE.Data3DTexture(data, nx, ny, nz);
  t.format = THREE.RGBAFormat;
  t.type = type;
  t.minFilter = THREE.LinearMipmapLinearFilter;
  t.magFilter = THREE.LinearFilter;
  t.generateMipmaps = true;
  t.unpackAlignment = 1;
  t.needsUpdate = true;
  return t;
}

// A 3D render target of `count` RGBA half-float textures, with mip levels made by mipmap().
function volumeTarget(nx, ny, nz, count) {
  const rt = new THREE.WebGL3DRenderTarget(nx, ny, nz, {
    type: THREE.HalfFloatType,
    minFilter: THREE.LinearMipmapLinearFilter,
    magFilter: THREE.LinearFilter,
    depthBuffer: false,
    count,
  });
  // three.js makes the extra textures of a target as 2D ones: these are layers of the same volume.
  for (let i = 1; i < count; i++) {
    const t = rt.texture.clone();
    t.isRenderTargetTexture = true;
    t.renderTarget = rt;
    rt.textures[i] = t;
  }
  return rt;
}

function mipmap(renderer, texture) {
  const gl = renderer.getContext();
  renderer.state.bindTexture(gl.TEXTURE_3D, renderer.properties.get(texture).__webglTexture);
  gl.generateMipmap(gl.TEXTURE_3D);
  renderer.state.unbindTexture();
}

const QUAD_VERTEX = /* glsl */ `
void main() {
	gl_Position = vec4( position.xy, 0.0, 1.0 );
}`;

// The sunlight at the middle of each cell of a layer: on a face turned to the sun, from 8 points
// round the middle, each lit unless the model's picture from the sun has something nearer the sun,
// and in the colour of the glass nearer the sun (as look.js colours the sun through glass).
const SUN_FRAGMENT = /* glsl */ `
uniform sampler2D sunDepth;
uniform sampler2D glassColour;
uniform sampler2D glassDepth;
uniform float glassOn;
uniform mat4 sunMatrix;
uniform float depthBias;
uniform vec3 sunLight;
uniform vec3 boxMin;
uniform vec3 boxSize;
uniform vec3 dims;
uniform float layer;
uniform float cell;
layout( location = 0 ) out vec4 outSun;

vec3 through( vec3 q ) {
	vec4 c = sunMatrix * vec4( q, 1.0 );
	vec3 s = c.xyz / c.w;
	if ( s.x < 0.0 || s.x > 1.0 || s.y < 0.0 || s.y > 1.0 || s.z > 1.0 ) return vec3( 1.0 );
	if ( s.z > texture( sunDepth, s.xy ).r + depthBias ) return vec3( 0.0 );
	if ( glassOn < 0.5 || s.z <= texture( glassDepth, s.xy ).r + depthBias ) return vec3( 1.0 );
	vec3 t = texture( glassColour, s.xy ).rgb;
	float top = max( max( t.r, t.g ), max( t.b, 0.001 ) );
	return t * ( 1.0 + 0.8 * ( 1.0 - min( min( t.r, t.g ), t.b ) / top ) );
}

void main() {
	vec3 p = boxMin + vec3( gl_FragCoord.xy, layer + 0.5 ) / dims * boxSize;
	vec3 sum = vec3( 0.0 );
	for ( int i = 0; i < 8; i ++ ) {
		vec3 o = vec3( float( i & 1 ), float( ( i >> 1 ) & 1 ), float( ( i >> 2 ) & 1 ) ) - 0.5;
		sum += through( p + o * cell * 0.5 );
	}
	outSun = vec4( sunLight * sum / 8.0, 1.0 );
}`;

// The light arriving at the middle of each cell of a layer, along the cones (see the top), as
// irradiance: e0 + dot( e1, n ) for each colour on a face turned to n, times the cell's
// trustworthiness (how much of the cones' first stretch is open, and of the cell itself: low
// inside something solid, nothing in a wall's cell).
const GATHER_FRAGMENT = /* glsl */ `
#define CONES ${CONES}
#define STEPS ${STEPS}
#define STEP ${STEP.toFixed(2)}
#define INV_PI 0.3183099
#define DEPTH ${DEPTH.toFixed(1)}
uniform highp sampler3D passX;
uniform highp sampler3D passY;
uniform highp sampler3D passZ;
uniform highp sampler3D matter;
uniform highp sampler3D given;
uniform highp sampler3D sun;
uniform highp sampler3D lastR;
uniform highp sampler3D lastG;
uniform highp sampler3D lastB;
uniform highp sampler3D lastV;
uniform float hasLast;
uniform vec3 boxMin;
uniform vec3 boxSize;
uniform vec3 dims;
uniform float layer;
uniform float cell;
uniform float maxLod;
uniform vec3 cones[ CONES ];
uniform float coneTan;
uniform vec3 sunDir;
uniform vec3 skyLight;
uniform vec3 groundLight;
uniform float groundY;
uniform float groundOpen;
layout( location = 0 ) out vec4 outR;
layout( location = 1 ) out vec4 outG;
layout( location = 2 ) out vec4 outB;
layout( location = 3 ) out vec4 outV;

// The light falling on a face at u (grid coordinates) turned to n: the sun's, and what the round
// before found there.
vec3 lightOn( vec3 u, vec3 n, float lod ) {
	vec3 e = textureLod( sun, u, lod ).rgb * max( dot( n, sunDir ), 0.0 );
	if ( hasLast > 0.5 ) {
		float v = textureLod( lastV, u, lod ).r;
		if ( v > 0.02 ) {
			vec4 r = textureLod( lastR, u, lod );
			vec4 g = textureLod( lastG, u, lod );
			vec4 b = textureLod( lastB, u, lod );
			e += max( vec3( r.x + dot( r.yzw, n ), g.x + dot( g.yzw, n ), b.x + dot( b.yzw, n ) ) / v, 0.0 );
		}
	}
	return e;
}

void main() {
	vec3 p = boxMin + vec3( gl_FragCoord.xy, layer + 0.5 ) / dims * boxSize;
	vec4 sumR = vec4( 0.0 ), sumG = vec4( 0.0 ), sumB = vec4( 0.0 );
	float near = 0.0;
	for ( int k = 0; k < CONES; k ++ ) {
		// How many of a cell's widths along each axis a step goes.
		vec3 d = cones[ k ], w = STEP * abs( d );
		vec3 light = vec3( 0.0 ), tau = vec3( 1.0 ), last = p;
		float t = cell, first = 1.0;
		bool open = true;
		for ( int s = 0; s < STEPS; s ++ ) {
			float size = max( 2.0 * coneTan * t, cell );
			float lod = min( log2( size / cell ), maxLod );
			vec3 q = p + d * t;
			if ( q.y < groundY && last.y >= groundY ) {
				// The ground, as bright as the light on it here against the open ground's (inside,
				// under a floor, it is that floor's light).
				vec3 hit = last + d * ( ( groundY - last.y ) / d.y ) + vec3( 0.0, 0.5 * cell, 0.0 );
				float here = dot( lightOn( ( hit - boxMin ) / boxSize, vec3( 0.0, 1.0, 0.0 ), 0.0 ), vec3( 0.2126, 0.7152, 0.0722 ) );
				light += tau * groundLight * min( here / groundOpen, 1.5 );
				open = false;
				break;
			}
			vec3 u = ( q - boxMin ) / boxSize;
			if ( any( lessThan( u, vec3( 0.0 ) ) ) || any( greaterThan( u, vec3( 1.0 ) ) ) ) {
				open = q.y >= groundY;
				break;
			}
			// How strongly the step's way holds the light back: crossing a cell along an axis as the
			// grid says; a cone going slantwise crosses a wall over a longer way, as much in all.
			vec4 held = ( textureLod( passX, u, lod ) * w.x + textureLod( passY, u, lod ) * w.y + textureLod( passZ, u, lod ) * w.z ) * DEPTH;
			vec3 through = exp( - held.rgb );
			float a = 1.0 - exp( - held.a );
			if ( a > 0.002 ) {
				vec4 m = textureLod( matter, u, lod );
				light += tau * a * ( m.rgb / max( m.a, 0.004 ) ) * lightOn( ( last - boxMin ) / boxSize, - d, lod ) * INV_PI;
			}
			// The light given in the cells the step crosses (the coarser grids average it over their
			// blocks; the step is as deep as STEP blocks).
			light += tau * textureLod( given, u, lod ).rgb * ( STEP * exp2( lod ) );
			tau *= through;
			if ( s == 0 ) first = ( tau.r + tau.g + tau.b ) / 3.0;
			if ( tau.r + tau.g + tau.b < 0.03 ) {
				open = false;
				break;
			}
			last = q;
			// A step at most as long as the coarsest grid's cells, so it skips none of them.
			t += min( size, cell * exp2( maxLod ) ) * STEP;
		}
		if ( open ) light += tau * ( d.y >= 0.0 ? skyLight : groundLight );
		near += first;
		vec4 basis = vec4( 1.0, 2.0 * d );
		sumR += light.r * basis;
		sumG += light.g * basis;
		sumB += light.b * basis;
	}
	// A cell with a wall across it has the light of both its sides: not for the surfaces round it.
	float own = textureLod( matter, ( p - boxMin ) / boxSize, 0.0 ).a;
	float v = clamp( ( near / float( CONES ) - 0.15 ) / 0.5, 0.0, 1.0 ) * ( 1.0 - own );
	float k = 3.14159265 / float( CONES ) * v;
	outR = sumR * k;
	outG = sumG * k;
	outB = sumB * k;
	outV = vec4( v, 0.0, 0.0, 1.0 );
}`;

// How much light there is where you stand (its brightness over all sides, the sun's too, as log2
// in r) and how far the cells there can be trusted (g).
const EYE_FRAGMENT = /* glsl */ `
uniform highp sampler3D gridR;
uniform highp sampler3D gridG;
uniform highp sampler3D gridB;
uniform highp sampler3D gridV;
uniform highp sampler3D sun;
uniform vec3 at;
layout( location = 0 ) out vec4 outEye;
void main() {
	float v = textureLod( gridV, at, 0.0 ).r;
	vec3 e = vec3( textureLod( gridR, at, 0.0 ).x, textureLod( gridG, at, 0.0 ).x, textureLod( gridB, at, 0.0 ).x ) / max( v, 0.001 );
	// The sun on all sides: a quarter of it on average.
	e = max( e, 0.0 ) + textureLod( sun, at, 0.0 ).rgb * 0.25;
	float y = dot( e, vec3( 0.2126, 0.7152, 0.0722 ) );
	outEye = vec4( clamp( ( log2( max( y, 1e-6 ) ) + 12.0 ) / 24.0, 0.0, 1.0 ), v, 0.0, 1.0 );
}`;

// The light on a face turned to n at a point (grid coordinates, a little in front of the face
// already), as surfaces get it, and how far the cells there can be trusted: for tests.
const SAMPLE_FRAGMENT = /* glsl */ `
uniform highp sampler3D gridR;
uniform highp sampler3D gridG;
uniform highp sampler3D gridB;
uniform highp sampler3D gridV;
uniform vec3 at;
uniform vec3 n;
layout( location = 0 ) out vec4 outLight;
void main() {
	float v = textureLod( gridV, at, 0.0 ).r;
	vec4 r = textureLod( gridR, at, 0.0 );
	vec4 g = textureLod( gridG, at, 0.0 );
	vec4 b = textureLod( gridB, at, 0.0 );
	outLight = vec4( max( vec3( r.x + dot( r.yzw, n ), g.x + dot( g.yzw, n ), b.x + dot( b.yzw, n ) ), 0.0 ) / max( v, 0.0001 ), v );
}`;

// What surfaces add to look up their light in the grid (look.js puts it in their shader): the
// light of the cells round a point a little in front of the surface, leaving out the cells it can't
// trust (see the gather); with none there (a surface in a narrow gap), a little further out; with
// none there either, dim.
export const RECEIVE_GRID = /* glsl */ `
uniform highp sampler3D roamGridR;
uniform highp sampler3D roamGridG;
uniform highp sampler3D roamGridB;
uniform highp sampler3D roamGridV;
uniform vec3 roamGridMin;
uniform vec3 roamGridSize;
uniform float roamGridCell;
uniform float roamGridOn;
vec3 roamGridAt( vec3 u, vec3 n, out float v ) {
	v = textureLod( roamGridV, u, 0.0 ).r;
	vec4 r = textureLod( roamGridR, u, 0.0 );
	vec4 g = textureLod( roamGridG, u, 0.0 );
	vec4 b = textureLod( roamGridB, u, 0.0 );
	return max( vec3( r.x + dot( r.yzw, n ), g.x + dot( g.yzw, n ), b.x + dot( b.yzw, n ) ), 0.0 ) / max( v, 0.0001 );
}
vec3 roamGridLight( vec3 irradiance, vec3 viewNormal ) {
	if ( roamGridOn <= 0.0 ) return irradiance;
	vec3 n = inverseTransformDirection( viewNormal, viewMatrix );
	vec3 u = ( vRoamWorld + n * roamGridCell * 0.6 - roamGridMin ) / roamGridSize;
	// Towards the grid's sides and top (open air), the sky's light again; its bottom is under the
	// ground.
	vec3 edge = min( u, 1.0 - u ) * roamGridSize / roamGridCell;
	float fade = roamGridOn * smoothstep( 0.5, 2.5, min( min( edge.x, edge.z ), ( 1.0 - u.y ) * roamGridSize.y / roamGridCell ) );
	if ( fade <= 0.0 ) return irradiance;
	float v, further;
	vec3 e = roamGridAt( u, n, v );
	if ( v < 0.02 ) {
		vec3 e2 = roamGridAt( u + n * roamGridCell * 1.2 / roamGridSize, n, further );
		if ( further > v ) {
			e = e2;
			v = further;
		}
	}
	return mix( irradiance, mix( irradiance * 0.15, e, smoothstep( 0.0, 0.01, v ) ), fade );
}
`;

// One grid over the model: its cells' textures, the sunlight in them, and two sets of light
// (the last finished round and the one being worked out).
class Grid {
  constructor(renderer, spec, data) {
    const { nx, ny, nz, cell, min } = spec;
    this.spec = spec;
    this.box = new THREE.Box3(min.clone(), min.clone().add(new THREE.Vector3(nx, ny, nz).multiplyScalar(cell)));
    // The coarser grids the cones read (the GPU's have more, unused).
    this.levels = Math.min(levelsOf(nx, ny), MAX_LOD + 1);
    this.pass = data.pass.map((d, axis) => {
      const t = volume(d, nx, ny, nz);
      // Read cell by cell (not blended with the cell beside it): a thin wall stays a wall, and
      // thin columns don't swell into their neighbours.
      t.magFilter = THREE.NearestFilter;
      t.minFilter = THREE.NearestMipmapLinearFilter;
      renderer.initTexture(t);
      // The GPU's coarser grids average; along its axis, a block lets through what gets through
      // both halves (see passLevels).
      const gl = renderer.getContext();
      renderer.state.bindTexture(gl.TEXTURE_3D, renderer.properties.get(t).__webglTexture);
      gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
      passLevels(d, nx, ny, nz, axis, this.levels).forEach((m, i) => {
        gl.texSubImage3D(gl.TEXTURE_3D, i + 1, 0, 0, 0, m.w, m.h, m.d, gl.RGBA, gl.UNSIGNED_BYTE, m.data);
      });
      renderer.state.unbindTexture();
      t.image.data = null; // on the GPU now
      return t;
    });
    this.matter = volume(data.matter, nx, ny, nz);
    this.given = data.given ? volume(data.given, nx, ny, nz, THREE.HalfFloatType) : null;
    for (const t of [this.matter, this.given]) {
      if (!t) continue;
      renderer.initTexture(t);
      t.image.data = null;
    }
    this.sun = volumeTarget(nx, ny, nz, 1);
    this.sets = [volumeTarget(nx, ny, nz, 4), volumeTarget(nx, ny, nz, 4)];
    this.shown = -1; // the set of the last finished round
    this.rounds = 0; // rounds since the light last changed
    this.layer = 0;
    this.lightKey = "";
    this.lit = 0; // when the sunlight was last worked out (s)
  }

  dispose() {
    for (const t of [...this.pass, this.matter, this.given]) if (t) t.dispose();
    for (const rt of [this.sun, ...this.sets]) rt.dispose();
  }
}

export class Light {
  constructor(look, sky, fill) {
    this.look = look;
    this.renderer = look.renderer;
    this.sky = sky; // the hemisphere light (the sky, and the ground's light under it)
    this.fill = fill; // the light everywhere
    const r = this.renderer;
    this.able = !!r.capabilities.isWebGL2 && r.extensions.has("EXT_color_buffer_float");
    this.inputs = new Map(); // a model's group -> its surfaces
    this.dirty = false;
    this.making = 0; // the grid being made from the surfaces (its number), or 0
    this.made = 0;
    this.wanted = false; // there is a model with an inside to light
    this.grid = null; // the grid that lights the picture
    this.next = null; // a new one, until its first round is done
    this.on = 0;
    this.brightness = 1; // eyes used to the dark
    this.adaptTo = 1;
    this._eyeAt = 0;
    this._eyeBusy = false;
    this._t = 0;
    this.uniforms = {
      roamGridR: { value: null },
      roamGridG: { value: null },
      roamGridB: { value: null },
      roamGridV: { value: null },
      roamGridMin: { value: new THREE.Vector3() },
      roamGridSize: { value: new THREE.Vector3(1, 1, 1) },
      roamGridCell: { value: 1 },
      roamGridOn: { value: 0 },
    };
    this.cones = coneDirections(CONES);
    this.none = new THREE.Data3DTexture(new Uint8Array(4), 1, 1, 1);
    this.none.needsUpdate = true;
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2));
    this.quad.frustumCulled = false;
    this.quadScene = new THREE.Scene();
    this.quadScene.add(this.quad);
    this.quadCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    this.sunCamera = new THREE.OrthographicCamera();
    this.sunMatrix = new THREE.Matrix4();
    this.sunTarget = null;
    this.glassTarget = null;
    this.sunMaterial = new THREE.ShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: QUAD_VERTEX,
      fragmentShader: SUN_FRAGMENT,
      uniforms: {
        sunDepth: { value: null },
        glassColour: { value: null },
        glassDepth: { value: null },
        glassOn: { value: 0 },
        sunMatrix: { value: this.sunMatrix },
        depthBias: { value: 0 },
        sunLight: { value: new THREE.Color() },
        boxMin: { value: new THREE.Vector3() },
        boxSize: { value: new THREE.Vector3() },
        dims: { value: new THREE.Vector3() },
        layer: { value: 0 },
        cell: { value: 1 },
      },
      depthTest: false,
      depthWrite: false,
    });
    this.gatherMaterial = new THREE.ShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: QUAD_VERTEX,
      fragmentShader: GATHER_FRAGMENT,
      uniforms: {
        passX: { value: null },
        passY: { value: null },
        passZ: { value: null },
        matter: { value: null },
        given: { value: null },
        sun: { value: null },
        lastR: { value: null },
        lastG: { value: null },
        lastB: { value: null },
        lastV: { value: null },
        hasLast: { value: 0 },
        boxMin: { value: new THREE.Vector3() },
        boxSize: { value: new THREE.Vector3() },
        dims: { value: new THREE.Vector3() },
        layer: { value: 0 },
        cell: { value: 1 },
        maxLod: { value: 0 },
        cones: { value: this.cones },
        coneTan: { value: CONE_TAN },
        sunDir: { value: new THREE.Vector3() },
        skyLight: { value: new THREE.Color() },
        groundLight: { value: new THREE.Color() },
        groundY: { value: 0 },
        groundOpen: { value: 1 },
      },
      depthTest: false,
      depthWrite: false,
    });
    this.eyeMaterial = new THREE.ShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: QUAD_VERTEX,
      fragmentShader: EYE_FRAGMENT,
      uniforms: {
        gridR: { value: null },
        gridG: { value: null },
        gridB: { value: null },
        gridV: { value: null },
        sun: { value: null },
        at: { value: new THREE.Vector3() },
      },
      depthTest: false,
      depthWrite: false,
    });
    this.eyeTarget = new THREE.WebGLRenderTarget(1, 1, { depthBuffer: false });
    this.eyePixel = new Uint8Array(4);
    this._v = new THREE.Vector3();
    this._dir = new THREE.Vector3();
  }

  // The model's surfaces (look.js classifies them), or none: worked into a new grid.
  set(owner, items) {
    this.inputs.set(owner, items);
    this.dirty = true;
  }

  remove(owner) {
    if (this.inputs.delete(owner)) this.dirty = true;
  }

  // Before each frame: the next steps of the work, the grid's light for the surfaces, and how used
  // to the dark the eyes are where `camera` is.
  frame(camera, dt) {
    const enabled = this.able && this.look.shadows;
    if (!enabled) {
      this.on = 0;
      this.uniforms.roamGridOn.value = 0;
      this.brightness = this.adaptTo = 1;
      return;
    }
    this._t += dt;
    if (this.dirty && !this.making) this._job = this._make();
    const grid = this.next || this.grid;
    if (grid) this._work(grid);
    const shown = this._show();
    const want = shown && this.wanted;
    this.on = THREE.MathUtils.clamp(this.on + (want ? 1 : -1) * (dt / FADE_TIME), 0, 1);
    this.uniforms.roamGridOn.value = this.on;
    if (!this.on && this.grid && !this.wanted) {
      this.grid.dispose();
      this.grid = null;
    }
    this._adapt(camera, dt, this.on > 0 ? shown : null);
  }

  // The grid that lights the picture (a new one once its first round is done): its last finished
  // round, for the surfaces. Null before there is one.
  _show() {
    if (this.next && this.next.shown >= 0) {
      if (this.grid) this.grid.dispose();
      this.grid = this.next;
      this.next = null;
    }
    const shown = this.grid && this.grid.shown >= 0 ? this.grid : null;
    const u = this.uniforms;
    if (shown) {
      const set = shown.sets[shown.shown].textures;
      u.roamGridR.value = set[0];
      u.roamGridG.value = set[1];
      u.roamGridB.value = set[2];
      u.roamGridV.value = set[3];
      u.roamGridMin.value.copy(shown.box.min);
      shown.box.getSize(u.roamGridSize.value);
      u.roamGridCell.value = shown.spec.cell;
    }
    return shown;
  }

  // Everything the light still has to work out for the sun as it is now, done at once, for an AI's
  // picture (eyes.js): a tab in the background draws no frames, so there none of it was done. Gives
  // way to the page between rounds. False when there is no light inside to work out (Fast, or no
  // model big enough to have an inside).
  async settle() {
    if (!(this.able && this.look.shadows)) return false;
    for (let tries = 0; (this.dirty || this.making) && tries < 5; tries++) {
      if (!this.making) this._job = this._make();
      await this._job;
    }
    const grid = this.next || this.grid;
    if (!grid || !this.wanted) return false;
    this._work(grid, true);
    while (grid.rounds < ROUNDS) {
      this._work(grid, true);
      if (grid.layer === 0) await pause(); // a round done
      if (this.disposed || (this.next || this.grid) !== grid) return false;
    }
    this._show();
    this.on = 1;
    this.uniforms.roamGridOn.value = 1;
    return true;
  }

  // Adds up the surfaces into a new grid (in the background, see voxelize). With nothing to light
  // inside (no model, or a small one), the grid there fades out and the sky lights it as before.
  async _make() {
    this.dirty = false;
    const number = ++this.made;
    this.making = number;
    const start = performance.now();
    const items = [], box = new THREE.Box3();
    for (const list of this.inputs.values()) {
      for (const it of list) {
        items.push(it);
        box.union(it.box);
      }
    }
    try {
      const spec = gridOver(box);
      const data = spec && (await voxelize(items, spec, () => this.made === number && !this.disposed));
      if (this.made !== number || this.disposed) return;
      if (this.next) this.next.dispose();
      this.next = data ? new Grid(this.renderer, spec, data) : null;
      this.wanted = !!data;
      this.makeMs = Math.round(performance.now() - start);
    } catch (e) {
      console.warn("Roam: light", e);
    } finally {
      if (this.made === number) this.making = 0;
    }
  }

  // The sun and the sky now, as a key: when it changes, the light is worked out again.
  _daylight() {
    const sun = this.look.sun, sky = this.sky, fill = this.fill;
    this._dir.subVectors(sun.position, sun.target.position).normalize();
    const d = this._dir;
    return [d.x, d.y, d.z, sun.intensity, sky.intensity, fill.intensity].map((v) => v.toFixed(4)).join(",") +
      sun.color.getHexString() + sky.color.getHexString() + sky.groundColor.getHexString() + fill.color.getHexString();
  }

  // The next cells of the round being worked out; `now`: a sun that moved is taken at once, not
  // only a quarter of a second after it last did (while it is dragged).
  _work(grid, now = false) {
    const key = this._daylight();
    if (key !== grid.lightKey && (now || this._t - grid.lit > 0.25 || !grid.lightKey)) {
      // The sun moved (or the grid is new): its light in the cells again, and the rounds again
      // from the light they have (it is near what it will be).
      grid.lightKey = key;
      grid.lit = this._t;
      this._sunlight(grid);
      grid.rounds = 0;
      grid.layer = 0;
    }
    if (grid.rounds >= ROUNDS) return;
    const { nx, ny, nz } = grid.spec;
    const write = grid.shown < 0 ? 0 : 1 - grid.shown;
    const m = this.gatherMaterial, u = m.uniforms;
    u.passX.value = grid.pass[0];
    u.passY.value = grid.pass[1];
    u.passZ.value = grid.pass[2];
    u.matter.value = grid.matter;
    u.given.value = grid.given || this.none;
    u.sun.value = grid.sun.texture;
    const last = grid.shown >= 0 ? grid.sets[grid.shown].textures : null;
    u.lastR.value = last ? last[0] : this.none;
    u.lastG.value = last ? last[1] : this.none;
    u.lastB.value = last ? last[2] : this.none;
    u.lastV.value = last ? last[3] : this.none;
    u.hasLast.value = last ? 1 : 0;
    u.boxMin.value.copy(grid.box.min);
    grid.box.getSize(u.boxSize.value);
    u.dims.value.set(nx, ny, nz);
    u.cell.value = grid.spec.cell;
    u.maxLod.value = grid.levels - 1;
    u.sunDir.value.copy(this._dir);
    const sky = this.sky, fill = this.fill;
    const ambient = fill.color.clone().multiplyScalar(fill.intensity);
    u.skyLight.value.copy(sky.color).multiplyScalar(sky.intensity).add(ambient).multiplyScalar(1 / Math.PI);
    u.groundLight.value.copy(sky.groundColor).multiplyScalar(sky.intensity).add(ambient).multiplyScalar(1 / Math.PI);
    u.groundY.value = 0;
    // The open ground's light (sky, light everywhere, sun), as lightOn() finds it there.
    const open = sky.color.clone().multiplyScalar(sky.intensity).add(ambient)
      .add(this.look.sun.color.clone().multiplyScalar(this.look.sun.intensity * Math.max(this._dir.y, 0)));
    u.groundOpen.value = Math.max(1e-3, 0.2126 * open.r + 0.7152 * open.g + 0.0722 * open.b);
    const layers = Math.max(1, Math.floor(PER_FRAME / (nx * ny)));
    const target = grid.sets[write];
    this._into(() => {
      this.quad.material = m;
      for (let i = 0; i < layers && grid.layer < nz; i++, grid.layer++) {
        u.layer.value = grid.layer;
        this.renderer.setRenderTarget(target, grid.layer);
        this.renderer.render(this.quadScene, this.quadCamera);
      }
    });
    if (grid.layer >= nz) {
      for (const t of target.textures) mipmap(this.renderer, t);
      grid.shown = write;
      grid.rounds++;
      grid.layer = 0;
    }
  }

  // The sunlight in the grid's cells: the model and its glass seen from the sun, then each cell.
  _sunlight(grid) {
    const r = this.renderer, look = this.look, sun = look.sun, cam = this.sunCamera;
    const dir = this._dir, c = grid.box.getCenter(this._v), radius = grid.box.getSize(new THREE.Vector3()).length() / 2;
    cam.left = cam.bottom = -radius;
    cam.right = cam.top = radius;
    cam.near = 0.5;
    cam.far = 2 * radius + 1;
    cam.position.copy(c).addScaledVector(dir, radius + 0.5);
    cam.up.set(0, 1, 0);
    if (Math.abs(dir.y) > 0.99) cam.up.set(0, 0, -1);
    cam.lookAt(c);
    cam.updateProjectionMatrix();
    cam.updateMatrixWorld();
    this.sunMatrix
      .set(0.5, 0, 0, 0.5, 0, 0.5, 0, 0.5, 0, 0, 0.5, 0.5, 0, 0, 0, 1)
      .multiply(cam.projectionMatrix)
      .multiply(cam.matrixWorldInverse);
    if (!this.sunTarget) {
      this.sunTarget = new THREE.WebGLRenderTarget(SUN_MAP, SUN_MAP, { depthTexture: new THREE.DepthTexture(SUN_MAP, SUN_MAP), generateMipmaps: false });
      this.glassTarget = new THREE.WebGLRenderTarget(GLASS_MAP, GLASS_MAP, { depthTexture: new THREE.DepthTexture(GLASS_MAP, GLASS_MAP), generateMipmaps: false });
    }
    const world = look.world;
    look._into(this.sunTarget, () => {
      const override = world.overrideMaterial, background = world.background, fog = world.fog;
      world.overrideMaterial = look.depthOnly;
      world.background = null;
      world.fog = null;
      cam.layers.set(look.solidLayer);
      r.render(world, cam);
      world.overrideMaterial = override;
      world.background = background;
      world.fog = fog;
    });
    if (look.glass > 0) {
      cam.layers.set(0);
      look._into(this.glassTarget, () => {
        look.scene.overrideMaterial = look.depthOnly;
        r.render(look.scene, cam);
        look.scene.overrideMaterial = null;
        r.render(look.scene, cam);
      });
    }
    const m = this.sunMaterial, u = m.uniforms, { nx, ny, nz } = grid.spec;
    u.sunDepth.value = this.sunTarget.depthTexture;
    u.glassColour.value = this.glassTarget.texture;
    u.glassDepth.value = this.glassTarget.depthTexture;
    u.glassOn.value = look.glass > 0 ? 1 : 0;
    u.depthBias.value = 0.1 / (cam.far - cam.near);
    u.sunLight.value.copy(sun.color).multiplyScalar(sun.intensity);
    u.boxMin.value.copy(grid.box.min);
    grid.box.getSize(u.boxSize.value);
    u.dims.value.set(nx, ny, nz);
    u.cell.value = grid.spec.cell;
    this._into(() => {
      this.quad.material = m;
      for (let z = 0; z < nz; z++) {
        u.layer.value = z;
        r.setRenderTarget(grid.sun, z);
        r.render(this.quadScene, this.quadCamera);
      }
    });
    mipmap(r, grid.sun.texture);
  }

  // Draws into our targets and leaves the renderer as it was.
  _into(draw) {
    const r = this.renderer;
    const was = r.getRenderTarget(), face = r.getActiveCubeFace(), level = r.getActiveMipmapLevel();
    const autoClear = r.autoClear, shadows = r.shadowMap.autoUpdate;
    r.autoClear = false;
    r.shadowMap.autoUpdate = false;
    try {
      draw();
    } finally {
      r.shadowMap.autoUpdate = shadows;
      r.autoClear = autoClear;
      r.setRenderTarget(was, face, level);
    }
  }

  // Eyes used to the dark: the light where the camera is, a few times a second, against the open
  // sky's; the brightness follows it smoothly.
  _adapt(camera, dt, grid) {
    if (!grid) this.adaptTo = 1;
    else if (camera && !this._eyeBusy && this._t - this._eyeAt >= ADAPT_EVERY) {
      this._eyeAt = this._t;
      if (!this._probe(grid, camera.getWorldPosition(this._v))) {
        this.adaptTo = 1;
      } else {
        this._eyeBusy = true;
        this.renderer.readRenderTargetPixelsAsync(this.eyeTarget, 0, 0, 1, 1, this.eyePixel)
          .then((px) => { this.adaptTo = this._eyes(px).brightness; })
          .catch(() => { this.adaptTo = 1; })
          .finally(() => { this._eyeBusy = false; });
      }
    }
    const want = this.on > 0 ? 1 + (this.adaptTo - 1) * this.on : 1;
    this.brightness *= (want / this.brightness) ** (1 - Math.exp(-dt / ADAPT_TIME));
  }

  // The light where `position` (world) is, drawn into the 1 x 1 eye target; false outside the grid.
  _probe(grid, position) {
    const at = position.clone().sub(grid.box.min).divide(grid.box.getSize(new THREE.Vector3()));
    if (at.x < 0 || at.y < 0 || at.z < 0 || at.x > 1 || at.y > 1 || at.z > 1) return false;
    const m = this.eyeMaterial, u = m.uniforms, set = grid.sets[grid.shown].textures;
    u.gridR.value = set[0];
    u.gridG.value = set[1];
    u.gridB.value = set[2];
    u.gridV.value = set[3];
    u.sun.value = grid.sun.texture;
    u.at.value.copy(at);
    this._into(() => {
      this.quad.material = m;
      this.renderer.setRenderTarget(this.eyeTarget);
      this.renderer.render(this.quadScene, this.quadCamera);
    });
    return true;
  }

  // What the eye target says: how many times brighter the view is drawn there (1 where it can't
  // tell), and the light there against the open sky's (null then).
  _eyes(px) {
    const here = 2 ** ((px[0] / 255) * 24 - 12), sure = px[1] / 255;
    if (sure < 0.05) return { brightness: 1, light: null };
    const light = here / this._outdoors();
    return { brightness: THREE.MathUtils.clamp((1 / light) ** ADAPT_POWER, 1, ADAPT_MAX), light };
  }

  // The same at once, at `position` (world), for an AI's picture (eyes.js): its brightness is what
  // the view eases to there.
  eyeAt(position) {
    const grid = this.on > 0 && this.grid && this.grid.shown >= 0 ? this.grid : null;
    if (!grid || !this._probe(grid, position)) return { brightness: 1, light: null };
    const px = new Uint8Array(4);
    this.renderer.readRenderTargetPixels(this.eyeTarget, 0, 0, 1, 1, px);
    return this._eyes(px);
  }

  // The light out in the open, sky and sun, on everything round (as where you stand is measured:
  // over all sides).
  _outdoors() {
    const sky = this.sky, fill = this.fill, sun = this.look.sun;
    const c = sky.color.clone().add(sky.groundColor).multiplyScalar(sky.intensity / 2)
      .add(fill.color.clone().multiplyScalar(fill.intensity))
      .add(sun.color.clone().multiplyScalar(sun.intensity / 4));
    return 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b;
  }

  // The light falling on a face at `point` (world, metres) turned to `normal` (a zero normal: the
  // average over all sides), as the surfaces there get it from the grid, and how far the cells
  // there can be trusted (0 to 1); null outside the grid or before its first round. For tests.
  sample(point, normal = new THREE.Vector3()) {
    const grid = this.grid;
    if (!grid || grid.shown < 0) return null;
    const size = grid.box.getSize(new THREE.Vector3());
    const at = point.clone().addScaledVector(normal, grid.spec.cell * 0.6).sub(grid.box.min).divide(size);
    if (at.x < 0 || at.y < 0 || at.z < 0 || at.x > 1 || at.y > 1 || at.z > 1) return null;
    if (!this.sampleMaterial) {
      this.sampleMaterial = new THREE.ShaderMaterial({
        glslVersion: THREE.GLSL3,
        vertexShader: QUAD_VERTEX,
        fragmentShader: SAMPLE_FRAGMENT,
        uniforms: { gridR: { value: null }, gridG: { value: null }, gridB: { value: null }, gridV: { value: null }, at: { value: new THREE.Vector3() }, n: { value: new THREE.Vector3() } },
        depthTest: false,
        depthWrite: false,
      });
      this.sampleTarget = new THREE.WebGLRenderTarget(1, 1, { type: THREE.FloatType, depthBuffer: false });
    }
    const u = this.sampleMaterial.uniforms, set = grid.sets[grid.shown].textures;
    u.gridR.value = set[0];
    u.gridG.value = set[1];
    u.gridB.value = set[2];
    u.gridV.value = set[3];
    u.at.value.copy(at);
    u.n.value.copy(normal);
    this._into(() => {
      this.quad.material = this.sampleMaterial;
      this.renderer.setRenderTarget(this.sampleTarget);
      this.renderer.render(this.quadScene, this.quadCamera);
    });
    const px = new Float32Array(4);
    this.renderer.readRenderTargetPixels(this.sampleTarget, 0, 0, 1, 1, px);
    return { light: [px[0], px[1], px[2]].map((v) => Math.round(v * 1000) / 1000), sure: Math.round(px[3] * 100) / 100 };
  }

  // For tests and the page: how far the light is.
  state() {
    const g = this.grid;
    return {
      cells: g ? [g.spec.nx, g.spec.ny, g.spec.nz] : null,
      cell: g ? Math.round(g.spec.cell * 1000) / 1000 : null,
      rounds: g ? g.rounds : 0,
      done: !!g && g.shown >= 0 && g.rounds >= ROUNDS && !this.next && !this.making,
      ms: this.makeMs ?? null, // adding up the surfaces into cells (in the background)
      on: Math.round(this.on * 100) / 100,
      brightness: Math.round(this.brightness * 100) / 100,
    };
  }

  dispose() {
    this.disposed = true;
    for (const g of [this.grid, this.next]) if (g) g.dispose();
    for (const t of [this.sunTarget, this.glassTarget]) {
      if (!t) continue;
      t.depthTexture.dispose();
      t.dispose();
    }
    this.eyeTarget.dispose();
    if (this.sampleTarget) this.sampleTarget.dispose();
    this.none.dispose();
    this.quad.geometry.dispose();
    for (const m of [this.sunMaterial, this.gatherMaterial, this.eyeMaterial, this.sampleMaterial]) if (m) m.dispose();
  }
}
