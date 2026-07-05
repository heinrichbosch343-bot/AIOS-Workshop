/*
 * orb2d.js — the Phase 1 canvas-2D orb, kept as the WebGL-unavailable fallback.
 *
 * export createOrb2D(canvas) -> { setState, setLevel }
 *   setState('idle' | 'listening' | 'thinking' | 'speaking')
 *   setLevel(0..1) — live audio level while listening/speaking
 */
export function createOrb2D(canvas) {
  const ctx = canvas.getContext('2d');

  let state = 'idle';
  let level = 0;          // raw input level
  let smoothLevel = 0;    // eased for animation
  let hueShift = 0;

  // Crisp rendering on high-DPI screens. The canvas may be fullscreen
  // (non-square) — the orb draws centered using the smaller dimension.
  function fitCanvas() {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = (canvas.clientWidth || 480) * dpr;
    canvas.height = (canvas.clientHeight || canvas.clientWidth || 480) * dpr;
  }
  window.addEventListener('resize', fitCanvas);

  function setState(next) {
    state = next;
    if (next === 'thinking') hueShift = 0;
  }

  function setLevel(value) {
    level = Math.max(0, Math.min(1, value));
  }

  const STATE_COLORS = {
    idle:      { core: '190, 225, 255', glow: '60, 140, 220' },
    listening: { core: '200, 245, 255', glow: '40, 190, 235' },
    thinking:  { core: '215, 205, 255', glow: '120, 110, 235' },
    speaking:  { core: '190, 235, 255', glow: '50, 170, 240' },
  };

  function draw(now) {
    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h / 2;
    const base = Math.min(w, h) * 0.22;
    const t = now / 1000;

    smoothLevel += (level - smoothLevel) * 0.18;

    // Radius modulation per state.
    let radius = base;
    if (state === 'idle') {
      radius = base * (1 + 0.035 * Math.sin(t * (2 * Math.PI / 4)));      // 4s breath
    } else if (state === 'listening') {
      radius = base * (1.04 + 0.22 * smoothLevel);
    } else if (state === 'thinking') {
      radius = base * (1 + 0.02 * Math.sin(t * 5));
      hueShift = (hueShift + 0.35) % 360;
    } else if (state === 'speaking') {
      radius = base * (1.03 + 0.18 * smoothLevel);
    }

    ctx.clearRect(0, 0, w, h);
    const colors = STATE_COLORS[state] || STATE_COLORS.idle;

    // Outer glow halo.
    const glowStrength = state === 'idle' ? 0.35 : 0.5 + 0.4 * smoothLevel;
    const halo = ctx.createRadialGradient(cx, cy, radius * 0.4, cx, cy, radius * 2.4);
    halo.addColorStop(0, `rgba(${colors.glow}, ${0.5 * glowStrength})`);
    halo.addColorStop(0.55, `rgba(${colors.glow}, ${0.12 * glowStrength})`);
    halo.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = halo;
    ctx.fillRect(0, 0, w, h);

    // Core sphere.
    const core = ctx.createRadialGradient(
      cx - radius * 0.25, cy - radius * 0.3, radius * 0.1,
      cx, cy, radius
    );
    core.addColorStop(0, `rgba(${colors.core}, 0.95)`);
    core.addColorStop(0.45, `rgba(${colors.glow}, 0.75)`);
    core.addColorStop(1, `rgba(${colors.glow}, 0.15)`);
    ctx.fillStyle = core;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fill();

    // Thin rim.
    ctx.strokeStyle = `rgba(${colors.core}, 0.25)`;
    ctx.lineWidth = w * 0.004;
    ctx.stroke();

    // Thinking: three orbiting dots.
    if (state === 'thinking') {
      for (let i = 0; i < 3; i++) {
        const angle = t * 2.4 + (i * 2 * Math.PI) / 3;
        const orbitR = radius * 1.45;
        const dotX = cx + Math.cos(angle) * orbitR;
        const dotY = cy + Math.sin(angle) * orbitR * 0.35; // elliptical orbit
        const dotSize = w * 0.008 * (1 + 0.4 * Math.sin(t * 3 + i));
        ctx.fillStyle = `hsla(${230 + hueShift % 40}, 80%, 75%, 0.85)`;
        ctx.beginPath();
        ctx.arc(dotX, dotY, dotSize, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    requestAnimationFrame(draw);
  }

  fitCanvas();
  requestAnimationFrame(draw);

  return { setState, setLevel };
}
