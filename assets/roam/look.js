// How a model with colours looks (drawn from the GLB its build wrote beside the STL, see
// cad_roam/models.py): each part in its colour, see-through parts (glTF's alpha under 1) as
// glass, and parts that give light (glTF's emissive colour: lamps) lit in their colour, also in
// the dark (their light doesn't fall on anything yet). Glass tints what is behind it (the sky
// through a stained-glass window), glows where the sun is behind it, and lets the sun through in
// its colour: the floor and the pillars it falls on take that colour.
//
// Glass is drawn twice, after everything solid: once multiplying what is behind it by its colour
// (each face by the square root: a pane has two), once adding its own light (reflections, and
// the sun coming through it).
//
// The sun through glass: before each frame, the glass is drawn from the sun's shadow camera into
// a picture of its colours (panes multiply, so the light through two takes both) and of its
// nearest depth. Surfaces that take shadows look it up where they look up their shadow: farther
// from the sun than the glass at that spot, the sun reaches them in the glass's colour. Whether
// it gets there at all is still the shadows' say (glass casts none).
//
// Under a roof: the sky lights the world from everywhere (a hemisphere light), insides too, so
// a church would be as bright inside as out and its windows' light wouldn't show. The solid parts
// of the model are drawn once from straight above (their depth): a surface with something over it
// (looked up a little off the surface, so outer walls are not under their own top) gets only part
// of the sky's light.

import * as THREE from "three";

const LIGHT_MAP = 2048;
const SKY_MAP = 2048;
// The layer the model's solid parts are on as well, for the picture from above.
export const SOLID_LAYER = 1;
// How much of the sky's light reaches under a roof.
const COVERED = 0.5;
// What of the light around it a part that gives light still shows (its shape): a lamp is seen in
// its own light, drawn without the view's tone mapping, which pales a bright warm lamp to cream
// and a blue one to white. At glow 1 it shows its colour as it is, by day and in the dark.
const LIT_BY_OTHERS = 0.25;

// The shader of the lights, as three.js has it: what is added goes after (or before) `anchor`,
// found after `section`.
function patched(chunk, edits) {
  for (const [section, anchor, text, after] of edits) {
    const at = chunk.indexOf(section);
    const i = at < 0 ? -1 : chunk.indexOf(anchor, at);
    if (i < 0) {
      console.warn("Roam: three.js' lights changed, models are drawn without light through glass");
      continue;
    }
    const j = after ? i + anchor.length : i;
    chunk = chunk.slice(0, j) + text + chunk.slice(j);
  }
  return chunk;
}

const SUN_BLOCK = "#if ( NUM_DIR_LIGHTS > 0 ) && defined( RE_Direct )";
const SKY_BLOCK = "#if defined( RE_IndirectDiffuse )";

const RECEIVE_VERTEX = /* glsl */ `
	vRoamWorld = ( modelMatrix * vec4( transformed, 1.0 ) ).xyz;`;

const RECEIVE_PARS = /* glsl */ `
varying vec3 vRoamWorld;
uniform sampler2D roamSkyDepth;
uniform mat4 roamSkyMatrix;
uniform float roamSkyOn;
uniform float roamSkyBias;
uniform vec2 roamSkyTexel;
float roamSkyLight( vec3 viewNormal ) {
	if ( roamSkyOn < 0.5 ) return 1.0;
	vec3 n = inverseTransformDirection( viewNormal, viewMatrix );
	vec4 c = roamSkyMatrix * vec4( vRoamWorld + n * 0.6, 1.0 );
	vec3 p = c.xyz / c.w;
	if ( p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0 ) return 1.0;
	float under = 0.0;
	for ( int k = 0; k < 5; k ++ ) {
		vec2 o = k == 0 ? vec2( 0.0 ) : vec2( k == 1 ? 1.5 : k == 2 ? -1.5 : 0.0, k == 3 ? 1.5 : k == 4 ? -1.5 : 0.0 );
		under += p.z > texture2D( roamSkyDepth, p.xy + o * roamSkyTexel ).r + roamSkyBias ? 0.2 : 0.0;
	}
	return mix( 1.0, ${COVERED.toFixed(2)}, under );
}
#if defined( USE_SHADOWMAP ) && NUM_DIR_LIGHT_SHADOWS > 0
uniform sampler2D roamGlassColor;
uniform sampler2D roamGlassDepth;
uniform float roamGlassOn;
uniform float roamGlassBias;
vec3 roamGlassLight( vec4 coord ) {
	vec3 p = coord.xyz / coord.w;
	if ( roamGlassOn < 0.5 || p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0 || p.z > 1.0 ) return vec3( 1.0 );
	if ( p.z <= texture2D( roamGlassDepth, p.xy ).r + roamGlassBias ) return vec3( 1.0 );
	// Coloured light the more, the deeper its colour (as eyes used to a dim inside see it).
	vec3 t = texture2D( roamGlassColor, p.xy ).rgb;
	float top = max( max( t.r, t.g ), max( t.b, 0.001 ) );
	return t * ( 1.0 + 0.8 * ( 1.0 - min( min( t.r, t.g ), t.b ) / top ) );
}
#endif
`;

const RECEIVE_LIGHTS = patched(THREE.ShaderChunk.lights_fragment_begin, [
  [SUN_BLOCK, "vDirectionalShadowCoord[ i ] ) : 1.0;", `
		#if UNROLLED_LOOP_INDEX == 0
		directLight.color *= roamGlassLight( vDirectionalShadowCoord[ i ] );
		#endif`, true],
  [SKY_BLOCK, "#ifdef USE_LIGHT_PROBES_GRID", "irradiance *= roamSkyLight( geometryNormal );\n\n\t", false],
]);

const SHINE_LIGHTS = patched(THREE.ShaderChunk.lights_fragment_begin, [
  [SUN_BLOCK, "RE_Direct(", "roamThrough += directLight.color * saturate( - dot( geometryNormal, directLight.direction ) );\n\t\t", false],
]);

// glTF's BLEND parts (three.js makes them transparent, their alpha the opacity).
export function isGlass(material) {
  return !!material.transparent && material.opacity < 0.999;
}

// Parts that give light: glTF's emissive colour (KHR_materials_emissive_strength, its intensity).
export function isGlowing(material) {
  const e = material.emissive;
  return !!e && e.r + e.g + e.b > 0 && (material.emissiveIntensity ?? 1) > 0;
}

// What a see-through part lets through: its colour, all of it from about half covering (stained
// glass), only a hint of it when it is nearly clear.
export function transmittance(material) {
  const c = material.color;
  const s = THREE.MathUtils.clamp((material.opacity - 0.2) / 0.35, 0, 1);
  return new THREE.Color(1 + (c.r - 1) * s, 1 + (c.g - 1) * s, 1 + (c.b - 1) * s);
}

// The light a pane lets through, as it falls on things: its colour at full strength, so a deep
// blue window still casts a patch you see (the window itself keeps its depth).
function vivid(t) {
  const top = Math.max(t.r, t.g, t.b, 0.05);
  return new THREE.Color(t.r / top, t.g / top, t.b / top);
}

function multiplying(t, depthTest) {
  return new THREE.MeshBasicMaterial({
    color: new THREE.Color(Math.sqrt(t.r), Math.sqrt(t.g), Math.sqrt(t.b)),
    side: THREE.DoubleSide,
    transparent: true,
    depthTest,
    depthWrite: false,
    fog: false,
    toneMapped: false,
    blending: THREE.CustomBlending,
    blendEquation: THREE.AddEquation,
    blendSrc: THREE.ZeroFactor,
    blendDst: THREE.SrcColorFactor,
    blendSrcAlpha: THREE.ZeroFactor,
    blendDstAlpha: THREE.OneFactor,
  });
}

function shining(source, t, flat) {
  const m = new THREE.MeshStandardMaterial({
    color: source.color.clone().multiplyScalar(0.25 * source.opacity),
    metalness: 0,
    roughness: 0.15,
    side: THREE.DoubleSide,
    flatShading: flat,
    transparent: true,
    depthWrite: false,
    fog: false,
    blending: THREE.AdditiveBlending,
    // A glowing pane (a lamp's glass shade) adds its own light.
    emissive: source.emissive || 0x000000,
    emissiveIntensity: source.emissiveIntensity ?? 1,
    toneMapped: !isGlowing(source),
  });
  // The sun through the pane (per face): its colour, a little more saturated than the light it
  // lets through, so a window the sun is behind glows in its colour, not white.
  const glow = { value: new THREE.Color(t.r * t.r, t.g * t.g, t.b * t.b).multiplyScalar(0.22) };
  m.onBeforeCompile = (shader) => {
    shader.uniforms.roamGlow = glow;
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nuniform vec3 roamGlow;")
      .replace("#include <lights_fragment_begin>", `vec3 roamThrough = vec3( 0.0 );\n${SHINE_LIGHTS}`)
      .replace("#include <opaque_fragment>", "outgoingLight += roamThrough * roamGlow;\n#include <opaque_fragment>");
  };
  m.customProgramCacheKey = () => "roam-shine";
  return m;
}

export class Look {
  constructor(renderer, world, sun) {
    this.renderer = renderer;
    this.world = world; // the scene the models are in
    this.sun = sun;
    this.scene = new THREE.Scene(); // the glass, as the sun sees it
    this.glass = 0;
    this.target = null;
    this.depthOnly = new THREE.MeshBasicMaterial({ colorWrite: false, side: THREE.DoubleSide });
    this.uniforms = {
      roamGlassColor: { value: null },
      roamGlassDepth: { value: null },
      roamGlassOn: { value: 0 },
      roamGlassBias: { value: 0 },
      roamSkyDepth: { value: null },
      roamSkyMatrix: { value: new THREE.Matrix4() },
      roamSkyOn: { value: 0 },
      roamSkyBias: { value: 0 },
      roamSkyTexel: { value: new THREE.Vector2(1 / SKY_MAP, 1 / SKY_MAP) },
    };
    this.skyCamera = new THREE.OrthographicCamera();
    this.skyCamera.layers.set(SOLID_LAYER);
    this.skyTarget = null;
    this.skyDirty = false; // solid parts came or went: draw them from above again
    this._clear = new THREE.Color();
  }

  get shadows() {
    return this.renderer.shadowMap.enabled && this.sun.castShadow;
  }

  // Lets the sun reach a surface in the colour of the glass it came through, and the sky less
  // under a roof.
  receive(material) {
    const uniforms = this.uniforms;
    material.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, uniforms);
      shader.vertexShader = shader.vertexShader
        .replace("#include <common>", "#include <common>\nvarying vec3 vRoamWorld;")
        .replace("#include <worldpos_vertex>", `#include <worldpos_vertex>${RECEIVE_VERTEX}`);
      shader.fragmentShader = shader.fragmentShader
        .replace("#include <shadowmap_pars_fragment>", `#include <shadowmap_pars_fragment>\n${RECEIVE_PARS}`)
        .replace("#include <lights_fragment_begin>", RECEIVE_LIGHTS);
    };
    material.customProgramCacheKey = () => "roam-glass-light";
    return material;
  }

  // A solid part of a model: it casts shadows and roofs what is under it.
  solid(mesh) {
    mesh.castShadow = this.shadows;
    mesh.receiveShadow = true;
    mesh.layers.enable(SOLID_LAYER);
    this.skyDirty = true;
    return mesh;
  }

  // The meshes of one part of a model in its material (from the GLB): one for a solid part, two
  // for glass.
  meshes(geometry, source) {
    const flat = !geometry.attributes.normal;
    if (!isGlass(source)) {
      const glowing = isGlowing(source);
      const material = this.receive(new THREE.MeshStandardMaterial({
        color: glowing ? source.color.clone().multiplyScalar(LIT_BY_OTHERS) : source.color,
        metalness: source.metalness ?? 0,
        roughness: source.roughness ?? 1,
        emissive: source.emissive || 0x000000,
        emissiveIntensity: source.emissiveIntensity ?? 1,
        toneMapped: !glowing,
        side: THREE.DoubleSide,
        flatShading: flat,
      }));
      return [this.solid(new THREE.Mesh(geometry, material))];
    }
    const t = transmittance(source);
    const tint = new THREE.Mesh(geometry, multiplying(t, true));
    tint.renderOrder = 1;
    const shine = new THREE.Mesh(geometry, shining(source, t, flat));
    shine.renderOrder = 2;
    shine.receiveShadow = true;
    const light = new THREE.Mesh(geometry, multiplying(vivid(t), false));
    light.matrixAutoUpdate = false;
    this.scene.add(light);
    this.glass++;
    tint.userData.light = light;
    tint.userData.glass = true;
    return [tint, shine];
  }

  // A model that goes: its glass out of the sun's picture, its roofs out of the one from above.
  release(object) {
    object.traverse((o) => {
      if (o.layers && o.layers.isEnabled(SOLID_LAYER)) this.skyDirty = true;
      const light = o.userData && o.userData.light;
      if (!light) return;
      this.scene.remove(light);
      light.material.dispose();
      o.userData.light = null;
      this.glass--;
    });
  }

  // Before each frame, once the sun is where it will be: the glass as the sun sees it (and, when
  // the model changed, the model from above).
  frame() {
    const on = this.shadows;
    if (on && this.skyDirty) this._drawSky();
    this.uniforms.roamSkyOn.value = on && this.skyTarget ? 1 : 0;
    this.uniforms.roamGlassOn.value = on && this.glass > 0 ? 1 : 0;
    if (!this.uniforms.roamGlassOn.value) return;
    const r = this.renderer, sun = this.sun, cam = sun.shadow.camera;
    if (!this.target) {
      this.target = new THREE.WebGLRenderTarget(LIGHT_MAP, LIGHT_MAP, {
        depthTexture: new THREE.DepthTexture(LIGHT_MAP, LIGHT_MAP),
        generateMipmaps: false,
      });
      this.uniforms.roamGlassColor.value = this.target.texture;
      this.uniforms.roamGlassDepth.value = this.target.depthTexture;
    }
    // The shadow camera as the frame's shadows will have it (three.js moves it while drawing).
    sun.updateMatrixWorld();
    sun.target.updateMatrixWorld();
    sun.shadow.updateMatrices(sun);
    this.uniforms.roamGlassBias.value = 0.05 / Math.max(1e-3, cam.far - cam.near);
    this._into(this.target, () => {
      this.scene.overrideMaterial = this.depthOnly; // the nearest glass ...
      this.renderer.render(this.scene, cam);
      this.scene.overrideMaterial = null; // ... and the colours of all of it
      this.renderer.render(this.scene, cam);
    });
  }

  // The model's solid parts from straight above, over all of them: their depth.
  _drawSky() {
    this.skyDirty = false;
    const box = new THREE.Box3(), part = new THREE.Box3();
    this.world.traverse((o) => {
      if (!o.isMesh || !o.layers.isEnabled(SOLID_LAYER) || !o.geometry.boundingBox) return;
      box.union(part.copy(o.geometry.boundingBox).applyMatrix4(o.matrixWorld));
    });
    if (box.isEmpty()) {
      this.uniforms.roamSkyDepth.value = null;
      if (this.skyTarget) {
        this.skyTarget.depthTexture.dispose();
        this.skyTarget.dispose();
      }
      this.skyTarget = null;
      return;
    }
    if (!this.skyTarget) {
      this.skyTarget = new THREE.WebGLRenderTarget(SKY_MAP, SKY_MAP, {
        depthTexture: new THREE.DepthTexture(SKY_MAP, SKY_MAP),
        generateMipmaps: false,
      });
      this.uniforms.roamSkyDepth.value = this.skyTarget.depthTexture;
    }
    const cam = this.skyCamera, c = box.getCenter(new THREE.Vector3());
    const half = Math.max(box.max.x - box.min.x, box.max.z - box.min.z) / 2 + 2;
    cam.left = cam.bottom = -half;
    cam.right = cam.top = half;
    cam.near = 1;
    cam.far = box.max.y - box.min.y + 6;
    cam.position.set(c.x, box.max.y + 3, c.z);
    cam.up.set(0, 0, -1);
    cam.lookAt(c.x, box.min.y, c.z);
    cam.updateProjectionMatrix();
    cam.updateMatrixWorld();
    this.uniforms.roamSkyMatrix.value
      .set(0.5, 0, 0, 0.5, 0, 0.5, 0, 0.5, 0, 0, 0.5, 0.5, 0, 0, 0, 1)
      .multiply(cam.projectionMatrix)
      .multiply(cam.matrixWorldInverse);
    this.uniforms.roamSkyBias.value = 0.3 / (cam.far - cam.near);
    this._into(this.skyTarget, () => {
      const scene = this.world, override = scene.overrideMaterial, background = scene.background, fog = scene.fog;
      scene.overrideMaterial = this.depthOnly;
      scene.background = null;
      scene.fog = null;
      this.renderer.render(scene, cam);
      scene.overrideMaterial = override;
      scene.background = background;
      scene.fog = fog;
    });
  }

  // Draws into a target of ours, cleared to white and far, and leaves the renderer as it was.
  _into(target, draw) {
    const r = this.renderer;
    const was = r.getRenderTarget(), autoClear = r.autoClear, alpha = r.getClearAlpha(), shadows = r.shadowMap.autoUpdate;
    r.getClearColor(this._clear);
    r.setRenderTarget(target);
    r.setClearColor(0xffffff, 1);
    r.clear(true, true, false);
    r.autoClear = false;
    r.shadowMap.autoUpdate = false;
    draw();
    r.shadowMap.autoUpdate = shadows;
    r.autoClear = autoClear;
    r.setRenderTarget(was);
    r.setClearColor(this._clear, alpha);
  }

  dispose() {
    this.release(this.scene);
    this.depthOnly.dispose();
    for (const t of [this.target, this.skyTarget]) {
      if (!t) continue;
      t.depthTexture.dispose();
      t.dispose();
    }
  }
}
