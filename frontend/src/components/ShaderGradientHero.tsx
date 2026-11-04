import React, { useEffect, useRef } from 'react';

/**
 * ShaderGradientHero — React component implementing the official
 * https://github.com/ruucm/shadergradient specification for the homepage hero
 * and login welcome panel.
 *
 * Official Brand Palette:
 *   - color1: #002583 (Strong Blue)
 *   - color2: #FFB800 (Mustard Gold)
 *   - color3: #E5E8EF (Cool Light Gray)
 */
export interface ShaderGradientProps {
  color1?: string;
  color2?: string;
  color3?: string;
  uSpeed?: number;
  uStrength?: number;
  uDensity?: number;
  uFrequency?: number;
  uAmplitude?: number;
  brightness?: number;
  pixelDensity?: number;
  fov?: number;
  animate?: 'on' | 'off';
  grain?: 'on' | 'off';
}

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace('#', '').trim();
  const num = parseInt(clean, 16);
  if (Number.isNaN(num)) return [0, 0.145, 0.514];
  return [((num >> 16) & 255) / 255, ((num >> 8) & 255) / 255, (num & 255) / 255];
}

const VERTEX_SHADER = `
attribute vec2 aPosition;
varying vec2 vUv;
void main() {
  vUv = aPosition * 0.5 + 0.5;
  gl_Position = vec4(aPosition, 0.0, 1.0);
}
`;

const FRAGMENT_SHADER = `
precision mediump float;
varying vec2 vUv;
uniform vec2 uResolution;
uniform float uTime;
uniform float uSpeed;
uniform float uStrength;
uniform float uDensity;
uniform float uFrequency;
uniform float uAmplitude;
uniform float uBrightness;
uniform float uGrain;
uniform float uFov;
uniform vec3 uColor1;
uniform vec3 uColor2;
uniform vec3 uColor3;

vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

float snoise(vec3 v) {
  const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i  = floor(v + dot(v, C.yyy));
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
  vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
}

float surfaceElevation(vec2 p, float t) {
  vec2 q = p * (uDensity * 1.15);
  float n1 = snoise(vec3(q * 0.85, t * 0.45));
  float n2 = snoise(vec3(q * (uFrequency * 0.48) + vec2(n1 * 0.45, -t * 0.25), t * 0.35));
  float n3 = snoise(vec3(q * 0.45 - vec2(t * 0.18, n2 * 0.3), t * 0.2));
  return (n1 * 0.52 + n2 * 0.33 + n3 * 0.15) * uStrength * (uAmplitude * 0.45);
}

void main() {
  float aspect = uResolution.x / max(uResolution.y, 1.0);
  float fovScale = tan(radians(uFov) * 0.5);
  vec2 p = (vUv - 0.5) * vec2(aspect, 1.0) * fovScale * 2.1;
  float t = uTime * uSpeed;

  float eps = 0.015;
  float hCenter = surfaceElevation(p, t);
  float hRight  = surfaceElevation(p + vec2(eps, 0.0), t);
  float hUp     = surfaceElevation(p + vec2(0.0, eps), t);

  vec3 normal = normalize(vec3(hCenter - hRight, hCenter - hUp, eps * 2.4));
  vec3 lightDir1 = normalize(vec3(0.55, 0.48, 0.68));
  vec3 lightDir2 = normalize(vec3(-0.6, -0.35, 0.7));
  vec3 viewDir   = vec3(0.0, 0.0, 1.0);

  float diff1 = max(dot(normal, lightDir1), 0.0);
  float diff2 = max(dot(normal, lightDir2), 0.0);
  vec3 halfVec = normalize(lightDir1 + viewDir);
  float spec = pow(max(dot(normal, halfVec), 0.0), 22.0);
  float fresnel = pow(1.0 - max(dot(normal, viewDir), 0.0), 2.4);

  vec3 deepBlue = uColor1 * 0.52;
  float blueFlow = smoothstep(-0.85, 0.85, hCenter + 0.15 * diff2);
  vec3 col = mix(deepBlue, uColor1, blueFlow);

  float goldRibbon = smoothstep(0.18, 0.88, hCenter * 0.65 + diff1 * 0.55 - 0.12);
  float goldMask = smoothstep(-0.2, 0.75, vUv.x * 0.7 + vUv.y * 0.5);
  col = mix(col, uColor2, clamp(goldRibbon * goldMask * 0.46, 0.0, 0.52));

  float coolHighlight = clamp(spec * 0.42 + fresnel * 0.28 + smoothstep(0.45, 1.0, diff2) * 0.14, 0.0, 0.42);
  col = mix(col, uColor3, coolHighlight);

  if (uGrain > 0.5) {
    float grainNoise = fract(sin(dot(vUv * uResolution, vec2(12.9898, 78.233))) * 43758.5453);
    col += (grainNoise - 0.5) * 0.018;
  }

  col *= uBrightness;
  gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
`;

export const ShaderGradientHero: React.FC<ShaderGradientProps> = ({
  color1 = '#002583',
  color2 = '#FFB800',
  color3 = '#E5E8EF',
  uSpeed = 0.16,
  uStrength = 1.35,
  uDensity = 1.15,
  uFrequency = 3.2,
  uAmplitude = 1.8,
  brightness = 1.08,
  pixelDensity = 1.0,
  fov = 45,
  animate = 'on',
  grain = 'on',
}) => {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    const canvas = canvasRef.current;
    if (!mount || !canvas) return undefined;

    let gl: WebGLRenderingContext | null = null;
    try {
      gl =
        (canvas.getContext('webgl', {
          alpha: false,
          antialias: false,
          depth: false,
          stencil: false,
          powerPreference: 'low-power',
        }) as WebGLRenderingContext | null) ||
        (canvas.getContext('experimental-webgl') as WebGLRenderingContext | null);
    } catch {
      gl = null;
    }

    if (!gl) {
      mount.setAttribute('data-shader-state', 'fallback');
      return undefined;
    }

    const compile = (type: number, src: string) => {
      const sh = gl!.createShader(type);
      if (!sh) return null;
      gl!.shaderSource(sh, src);
      gl!.compileShader(sh);
      if (!gl!.getShaderParameter(sh, gl!.COMPILE_STATUS)) {
        gl!.deleteShader(sh);
        return null;
      }
      return sh;
    };

    const vs = compile(gl.VERTEX_SHADER, VERTEX_SHADER);
    const fs = compile(gl.FRAGMENT_SHADER, FRAGMENT_SHADER);
    if (!vs || !fs) {
      mount.setAttribute('data-shader-state', 'fallback');
      return undefined;
    }

    const prog = gl.createProgram();
    if (!prog) return undefined;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      mount.setAttribute('data-shader-state', 'fallback');
      return undefined;
    }

    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
      gl.STATIC_DRAW
    );

    const aPos = gl.getAttribLocation(prog, 'aPosition');
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    const uRes = gl.getUniformLocation(prog, 'uResolution');
    const uTime = gl.getUniformLocation(prog, 'uTime');
    const c1 = hexToRgb(color1);
    const c2 = hexToRgb(color2);
    const c3 = hexToRgb(color3);

    const resize = () => {
      if (!gl) return;
      const rect = mount.getBoundingClientRect();
      const mobile = window.innerWidth < 768;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5) * (mobile ? 0.75 : pixelDensity);
      const w = Math.max(1, Math.floor(rect.width * dpr));
      const h = Math.max(1, Math.floor(rect.height * dpr));
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
      gl.uniform2f(uRes, w, h);
      gl.uniform1f(gl.getUniformLocation(prog, 'uSpeed'), uSpeed);
      gl.uniform1f(gl.getUniformLocation(prog, 'uStrength'), mobile ? uStrength * 0.85 : uStrength);
      gl.uniform1f(gl.getUniformLocation(prog, 'uDensity'), mobile ? uDensity * 0.85 : uDensity);
      gl.uniform1f(gl.getUniformLocation(prog, 'uFrequency'), uFrequency);
      gl.uniform1f(gl.getUniformLocation(prog, 'uAmplitude'), uAmplitude);
      gl.uniform1f(gl.getUniformLocation(prog, 'uBrightness'), brightness);
      gl.uniform1f(gl.getUniformLocation(prog, 'uGrain'), grain === 'on' && !mobile ? 1.0 : 0.0);
      gl.uniform1f(gl.getUniformLocation(prog, 'uFov'), fov);
      gl.uniform3f(gl.getUniformLocation(prog, 'uColor1'), c1[0], c1[1], c1[2]);
      gl.uniform3f(gl.getUniformLocation(prog, 'uColor2'), c2[0], c2[1], c2[2]);
      gl.uniform3f(gl.getUniformLocation(prog, 'uColor3'), c3[0], c3[1], c3[2]);
    };

    resize();

    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    let rafId = 0;
    let startTs: number | null = null;
    let elapsed = 1.4;
    let inViewport = true;

    const shouldAnimate = () =>
      animate === 'on' && !reducedMotion?.matches && !document.hidden && inViewport;

    const draw = (ts: number) => {
      if (!gl) return;
      if (startTs === null) startTs = ts;
      elapsed += Math.min((ts - startTs) * 0.001, 0.1);
      startTs = ts;
      gl.uniform1f(uTime, elapsed);
      gl.drawArrays(gl.TRIANGLES, 0, 6);
      if (shouldAnimate()) {
        rafId = window.requestAnimationFrame(draw);
      } else {
        rafId = 0;
      }
    };

    const startLoop = () => {
      if (!rafId && shouldAnimate()) {
        startTs = null;
        rafId = window.requestAnimationFrame(draw);
      }
    };

    const stopLoop = () => {
      if (rafId) {
        window.cancelAnimationFrame(rafId);
        rafId = 0;
      }
    };

    gl.uniform1f(uTime, elapsed);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
    mount.setAttribute('data-shader-state', 'ready');

    startLoop();

    let observer: IntersectionObserver | null = null;
    if ('IntersectionObserver' in window) {
      observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            inViewport = entry.isIntersecting;
            if (inViewport) startLoop();
            else stopLoop();
          });
        },
        { threshold: 0.05 }
      );
      observer.observe(mount);
    }

    const onVisibility = () => {
      if (document.hidden) stopLoop();
      else startLoop();
    };

    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('resize', resize, { passive: true });
    return () => {
      stopLoop();
      observer?.disconnect();
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('resize', resize);
    };
  }, [
    color1,
    color2,
    color3,
    uSpeed,
    uStrength,
    uDensity,
    uFrequency,
    uAmplitude,
    brightness,
    pixelDensity,
    fov,
    animate,
    grain,
  ]);

  return (
    <div
      ref={mountRef}
      className="shadergradient-mount"
      aria-hidden="true"
      data-color1={color1}
      data-color2={color2}
      data-color3={color3}
      data-pixel-density={pixelDensity}
    >
      <canvas
        ref={canvasRef}
        className="shadergradient-canvas"
        aria-hidden="true"
        tabIndex={-1}
        role="presentation"
      />
    </div>
  );
};
