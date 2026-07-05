/*
 * orb3d.js — Johan's 3D plasma energy orb (Three.js, fullscreen canvas).
 *
 * The canvas covers the whole viewport (behind the UI) so glow and particles
 * never clip — the scene anchors itself to #orb-space's on-screen position
 * and size every frame, so the orb sits exactly where the layout puts it.
 *
 * The "rendered" look, cheaply:
 *   1. plasma core — simplex-noise displaced sphere, fbm energy wisps in the
 *      fragment shader, fresnel rim (volumetric, semi-transparent — not a ball)
 *   2. transparent fresnel shell — the glassy bubble around the plasma
 *   3. layered additive glow sprites + light streak (the fake bloom)
 *   4. additive particle field swirling around the core
 *
 * Exports Orb with the same API app.js has always used:
 *   Orb.setState('idle' | 'listening' | 'thinking' | 'speaking')
 *   Orb.setLevel(0..1)
 *
 * Falls back to the 2D canvas orb when WebGL is unavailable.
 * ?lowfx=1 forces the reduced-quality mode; an FPS watchdog auto-drops to it.
 */
import * as THREE from './vendor/three.module.min.js';
import { createOrb2D } from './orb2d.js';

const PARTICLE_COUNT = 2500;
const LOW_FX = new URLSearchParams(location.search).get('lowfx') === '1';

// Ashima/McEwen simplex noise (MIT) — the standard GLSL 3D snoise, shared by
// the core's vertex and fragment shaders.
const GLSL_SNOISE = /* glsl */`
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x * 34.0) + 10.0) * x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }
float snoise(vec3 v) {
  const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod289(i);
  vec4 p = permute(permute(permute(
      i.z + vec4(0.0, i1.z, i2.z, 1.0))
    + i.y + vec4(0.0, i1.y, i2.y, 1.0))
    + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.5 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
  m = m * m;
  return 105.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
}
float fbm(vec3 p) {
  float f = 0.0;
  f += 0.5000 * snoise(p); p *= 2.02;
  f += 0.2500 * snoise(p); p *= 2.03;
  f += 0.1250 * snoise(p);
  return f;
}
`;

function createOrb3D(canvas) {
  const orbSpace = document.getElementById('orb-space');
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setClearColor(0x000000, 0);

  const CAM_DIST = 6;
  const CAM_FOV = 38;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(CAM_FOV, 1, 0.1, 60);
  camera.position.set(0, 0, CAM_DIST);

  const orbGroup = new THREE.Group();
  scene.add(orbGroup);

  // ------------------------------------------------------------- state model
  const STATE_TARGETS = {
    idle:      { swirl: 1.0, spread: 1.00, core: 0.55, glow: 0.50, hue: 0.0 },
    listening: { swirl: 1.4, spread: 0.72, core: 0.65, glow: 0.62, hue: 0.06 },
    thinking:  { swirl: 4.2, spread: 0.95, core: 0.72, glow: 0.58, hue: 0.55 },
    speaking:  { swirl: 1.8, spread: 1.10, core: 0.70, glow: 0.65, hue: 0.0 },
  };
  let state = 'idle';
  let level = 0;
  let smoothLevel = 0;
  let transitionPulse = 0; // spikes on state change, decays — the "transition flare"
  // Live params ease toward the state targets so transitions feel organic.
  const p = { ...STATE_TARGETS.idle };

  // Blue -> violet blend axis (hue target 0..1 picks between these).
  const BLUE = new THREE.Color(0x4fb6ff);
  const VIOLET = new THREE.Color(0x8f7bff);
  const WHITE_BLUE = new THREE.Color(0xdff3ff);
  const tint = new THREE.Color();

  // ------------------------------------------------------------- plasma core
  const coreUniforms = {
    uTint: { value: new THREE.Color(0x4fb6ff) },
    uRim: { value: new THREE.Color(0xdff3ff) },
    uIntensity: { value: 0.55 },
    uTime: { value: 0 },
    uChurn: { value: 1.0 },   // noise animation speed (thinking cranks it up)
  };
  const coreMaterial = new THREE.ShaderMaterial({
    uniforms: coreUniforms,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    vertexShader: GLSL_SNOISE + /* glsl */`
      uniform float uTime;
      uniform float uChurn;
      varying vec3 vNormal;
      varying vec3 vView;
      varying vec3 vObjPos;
      varying float vBump;
      void main() {
        vObjPos = position;
        // Living surface: two octaves of slow noise ripple the sphere.
        float t = uTime * 0.35 * uChurn;
        float bump = 0.5 * snoise(normal * 2.1 + vec3(t, t * 0.7, -t))
                   + 0.25 * snoise(normal * 4.7 - vec3(t * 1.3, -t, t * 0.5));
        vBump = bump;
        vec3 displaced = position + normal * bump * 0.09;
        vNormal = normalize(normalMatrix * normal);
        vec4 mv = modelViewMatrix * vec4(displaced, 1.0);
        vView = normalize(-mv.xyz);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: GLSL_SNOISE + /* glsl */`
      uniform vec3 uTint;
      uniform vec3 uRim;
      uniform float uIntensity;
      uniform float uTime;
      uniform float uChurn;
      varying vec3 vNormal;
      varying vec3 vView;
      varying vec3 vObjPos;
      varying float vBump;
      void main() {
        float facing = clamp(dot(normalize(vNormal), normalize(vView)), 0.0, 1.0);
        float fresnel = pow(1.0 - facing, 2.2);

        // Volumetric energy wisps swimming through the sphere.
        float t = uTime * 0.30 * uChurn;
        float wisps = fbm(vObjPos * 2.6 + vec3(t, -t * 0.8, t * 0.6));
        wisps = smoothstep(-0.25, 0.75, wisps + vBump * 0.5);

        // Deep blue interior -> tint -> white-hot rim/filaments.
        vec3 deep = uTint * 0.22;
        vec3 color = mix(deep, uTint, wisps);
        color = mix(color, uRim, fresnel * 0.9 + wisps * wisps * 0.35);
        color *= uIntensity * 2.3;

        // Transparent where calm, bright where energetic — never a solid ball.
        float alpha = (0.10 + wisps * 0.42 + fresnel * 0.85) * clamp(uIntensity * 1.5, 0.0, 1.0);
        gl_FragColor = vec4(color, clamp(alpha, 0.0, 1.0));
      }
    `,
  });
  const core = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 96), coreMaterial);
  orbGroup.add(core);

  // Transparent fresnel shell — the glassy bubble that reads "3D sphere".
  const shellUniforms = {
    uRim: { value: new THREE.Color(0x9fd4ff) },
    uOpacity: { value: 0.55 },
  };
  const shell = new THREE.Mesh(
    new THREE.SphereGeometry(1.22, 64, 64),
    new THREE.ShaderMaterial({
      uniforms: shellUniforms,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexShader: /* glsl */`
        varying vec3 vNormal;
        varying vec3 vView;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          vView = normalize(-mv.xyz);
          gl_Position = projectionMatrix * mv;
        }
      `,
      fragmentShader: /* glsl */`
        uniform vec3 uRim;
        uniform float uOpacity;
        varying vec3 vNormal;
        varying vec3 vView;
        void main() {
          float facing = clamp(dot(normalize(vNormal), normalize(vView)), 0.0, 1.0);
          float fresnel = pow(1.0 - facing, 3.5);
          gl_FragColor = vec4(uRim, fresnel * uOpacity);
        }
      `,
    })
  );
  orbGroup.add(shell);

  // ------------------------------------------------------------ glow sprites
  function radialTexture(stops) {
    const size = 256;
    const c = document.createElement('canvas');
    c.width = c.height = size;
    const g = c.getContext('2d');
    const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    stops.forEach(([offset, color]) => grad.addColorStop(offset, color));
    g.fillStyle = grad;
    g.fillRect(0, 0, size, size);
    return new THREE.CanvasTexture(c);
  }

  // Small hot center — a soft sprite instead of a solid mesh, so the middle
  // glows without reading as an opaque white ball.
  const heart = new THREE.Sprite(new THREE.SpriteMaterial({
    map: radialTexture([[0, 'rgba(235,248,255,0.95)'], [0.22, 'rgba(170,220,255,0.5)'], [0.55, 'rgba(90,160,255,0.12)'], [1, 'rgba(0,0,0,0)']]),
    transparent: true,
    opacity: 0.9,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  }));
  heart.scale.setScalar(1.6);
  orbGroup.add(heart);

  const glowSpecs = [
    { scale: 3.4, opacity: 0.50, tex: radialTexture([[0, 'rgba(190,230,255,0.8)'], [0.35, 'rgba(90,170,255,0.30)'], [1, 'rgba(0,0,0,0)']]) },
    { scale: 5.6, opacity: 0.28, tex: radialTexture([[0, 'rgba(120,190,255,0.5)'], [0.5, 'rgba(60,120,220,0.12)'], [1, 'rgba(0,0,0,0)']]) },
    { scale: 9.0, opacity: 0.15, tex: radialTexture([[0, 'rgba(90,150,240,0.35)'], [0.6, 'rgba(40,80,180,0.07)'], [1, 'rgba(0,0,0,0)']]) },
  ];
  const glowSprites = glowSpecs.map((spec) => {
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
      map: spec.tex,
      transparent: true,
      opacity: spec.opacity,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }));
    sprite.scale.setScalar(spec.scale);
    sprite.userData.baseOpacity = spec.opacity;
    sprite.userData.baseScale = spec.scale;
    orbGroup.add(sprite);
    return sprite;
  });

  // Horizontal light streak — the lens-flare feel from the reference image.
  const streak = new THREE.Sprite(new THREE.SpriteMaterial({
    map: radialTexture([[0, 'rgba(220,240,255,0.9)'], [0.25, 'rgba(140,200,255,0.25)'], [1, 'rgba(0,0,0,0)']]),
    transparent: true,
    opacity: 0.32,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  }));
  streak.scale.set(10.5, 0.5, 1);
  streak.userData.baseOpacity = 0.32;
  orbGroup.add(streak);

  // --------------------------------------------------------------- particles
  const particleTexture = radialTexture([[0, 'rgba(255,255,255,1)'], [0.35, 'rgba(170,215,255,0.55)'], [1, 'rgba(0,0,0,0)']]);
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  // Per-particle orbital parameters, updated on the CPU each frame (cheap at 2.5k).
  const orbit = new Array(PARTICLE_COUNT);
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    orbit[i] = {
      radius: 1.35 + Math.pow(Math.random(), 1.7) * 2.1,
      theta: Math.random() * Math.PI * 2,
      phi: Math.acos(2 * Math.random() - 1),
      speed: (0.12 + Math.random() * 0.5) * (Math.random() < 0.5 ? 1 : -1),
      wobble: Math.random() * Math.PI * 2,
    };
  }
  const particleGeometry = new THREE.BufferGeometry();
  particleGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const particleMaterial = new THREE.PointsMaterial({
    size: 0.055,
    map: particleTexture,
    transparent: true,
    opacity: 0.85,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    sizeAttenuation: true,
    color: 0x9fd4ff,
  });
  const particles = new THREE.Points(particleGeometry, particleMaterial);
  orbGroup.add(particles);

  let activeParticles = PARTICLE_COUNT;

  function applyLowFx() {
    activeParticles = Math.floor(PARTICLE_COUNT / 2);
    particleGeometry.setDrawRange(0, activeParticles);
    const outer = glowSprites[2];
    if (outer) { orbGroup.remove(outer); glowSprites.pop(); }
    core.geometry = new THREE.SphereGeometry(1, 48, 48);
    renderer.setPixelRatio(1);
  }

  // ------------------------------------------------------------------ sizing
  function resize() {
    const w = canvas.clientWidth || window.innerWidth;
    const h = canvas.clientHeight || window.innerHeight;
    const dpr = LOW_FX ? 1 : Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(dpr);
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener('resize', resize);
  resize();
  if (LOW_FX) applyLowFx();

  // Anchor the orb to #orb-space: convert its on-screen center + width into
  // world-space position + scale at the z=0 plane.
  const anchor = new THREE.Vector3();
  let anchorScale = 1;
  function updateAnchor() {
    const rect = orbSpace.getBoundingClientRect();
    const vw = canvas.clientWidth || window.innerWidth;
    const vh = canvas.clientHeight || window.innerHeight;
    if (!rect.width || !vh) return;
    const worldPerPx = (2 * Math.tan(THREE.MathUtils.degToRad(CAM_FOV / 2)) * CAM_DIST) / vh;
    anchor.set(
      (rect.left + rect.width / 2 - vw / 2) * worldPerPx,
      -(rect.top + rect.height / 2 - vh / 2) * worldPerPx,
      0
    );
    anchorScale = Math.max(0.05, rect.width * 0.26 * worldPerPx);
  }

  // ------------------------------------------------------------ FPS watchdog
  let fpsAccum = 0;
  let fpsFrames = 0;
  let slowSince = 0;
  let degraded = LOW_FX;

  function watchFps(dt, now) {
    if (degraded) return;
    fpsAccum += dt;
    fpsFrames += 1;
    if (fpsAccum >= 0.5) {
      const fps = fpsFrames / fpsAccum;
      fpsAccum = 0;
      fpsFrames = 0;
      if (fps < 45) {
        if (!slowSince) slowSince = now;
        if (now - slowSince > 3) {
          degraded = true;
          applyLowFx();
        }
      } else {
        slowSince = 0;
      }
    }
  }

  // -------------------------------------------------------------- render loop
  let lastTime = 0;

  function frame(nowMs) {
    const now = nowMs / 1000;
    const dt = Math.min(now - (lastTime || now), 0.05);
    lastTime = now;
    watchFps(dt, now);
    updateAnchor();

    smoothLevel += (level - smoothLevel) * 0.18;

    // Ease live params toward the current state's targets.
    const target = STATE_TARGETS[state] || STATE_TARGETS.idle;
    const k = 1 - Math.pow(0.002, dt); // ~0.4s to close most of the gap
    p.swirl += (target.swirl - p.swirl) * k;
    p.spread += (target.spread - p.spread) * k;
    p.core += (target.core - p.core) * k;
    p.glow += (target.glow - p.glow) * k;
    p.hue += (target.hue - p.hue) * k;

    // Transition flare: bright burst that decays over ~0.6s after a state change.
    transitionPulse *= Math.pow(0.006, dt);

    // State-driven live modulation on top of the eased base.
    let coreIntensity = p.core + 0.5 * transitionPulse;
    let glowStrength = p.glow + 0.35 * transitionPulse;
    let spread = p.spread + 0.08 * transitionPulse;
    if (state === 'idle') {
      coreIntensity += 0.06 * Math.sin(now * (2 * Math.PI / 4)); // 4s breath
    } else if (state === 'listening') {
      coreIntensity += 0.55 * smoothLevel;
      glowStrength += 0.35 * smoothLevel;
    } else if (state === 'thinking') {
      coreIntensity += 0.08 * Math.sin(now * 7.0);
    } else if (state === 'speaking') {
      coreIntensity += 0.75 * smoothLevel;
      glowStrength += 0.45 * smoothLevel;
      spread += 0.10 * smoothLevel;
    }

    tint.copy(BLUE).lerp(VIOLET, Math.max(0, Math.min(1, p.hue)));
    coreUniforms.uTint.value.copy(tint);
    coreUniforms.uIntensity.value = coreIntensity;
    coreUniforms.uTime.value = now;
    coreUniforms.uChurn.value = 0.7 + p.swirl * 0.35;
    shellUniforms.uRim.value.copy(tint).lerp(WHITE_BLUE, 0.6);
    shellUniforms.uOpacity.value = 0.4 + 0.3 * Math.min(1, coreIntensity) + 0.25 * smoothLevel;
    heart.material.opacity = 0.55 + 0.45 * Math.min(1, coreIntensity);
    heart.scale.setScalar(1.6 * (1 + 0.22 * smoothLevel + 0.25 * transitionPulse));
    particleMaterial.color.copy(tint).lerp(WHITE_BLUE, 0.45);

    glowSprites.forEach((sprite, i) => {
      sprite.material.opacity = sprite.userData.baseOpacity * (glowStrength / 0.5);
      const pulse = 1 + 0.04 * Math.sin(now * 1.7 + i * 1.9) + 0.12 * smoothLevel;
      sprite.scale.setScalar(sprite.userData.baseScale * pulse);
    });
    streak.material.opacity = streak.userData.baseOpacity * (glowStrength / 0.5) * (0.7 + 0.6 * smoothLevel);

    // Particle swirl.
    const pos = particleGeometry.attributes.position.array;
    for (let i = 0; i < activeParticles; i++) {
      const o = orbit[i];
      o.theta += o.speed * p.swirl * dt;
      const r = o.radius * spread * (1 + 0.05 * Math.sin(now * 0.9 + o.wobble));
      const sinPhi = Math.sin(o.phi);
      pos[i * 3] = r * sinPhi * Math.cos(o.theta);
      pos[i * 3 + 1] = r * Math.cos(o.phi) * 0.82; // slightly flattened cloud
      pos[i * 3 + 2] = r * sinPhi * Math.sin(o.theta);
    }
    particleGeometry.attributes.position.needsUpdate = true;

    // Anchor to the layout slot, scale to it, then float on a slow Lissajous
    // drift so the orb "flies" without leaving its place in the page.
    orbGroup.scale.setScalar(anchorScale);
    orbGroup.position.set(
      anchor.x + anchorScale * 0.06 * Math.sin(now * 0.61),
      anchor.y + anchorScale * 0.08 * Math.sin(now * 0.43 + 1.3),
      0
    );
    orbGroup.rotation.y = now * 0.05;

    renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  return {
    setState(next) {
      const clean = STATE_TARGETS[next] ? next : 'idle';
      if (clean !== state) transitionPulse = clean === 'speaking' ? 1 : 0.55; // biggest flare when the answer starts
      state = clean;
    },
    setLevel(value) { level = Math.max(0, Math.min(1, value)); },
  };
}

function buildOrb() {
  const canvas = document.getElementById('orb');
  try {
    return createOrb3D(canvas);
  } catch (err) {
    console.warn('WebGL orb unavailable — using 2D fallback.', err);
    return createOrb2D(canvas);
  }
}

export const Orb = buildOrb();
