/**
 * static/js/shader-gradient-hero.js
 *
 * Isolated ShaderGradient Hero integration for EduManage (Flask + Jinja2).
 * Configured using the official https://github.com/ruucm/shadergradient
 * ShaderGradientCanvas & ShaderGradient property specification:
 *
 *   ShaderGradientCanvas props:
 *     - pixelDensity: 1.0 (0.75 on narrow mobile viewports to conserve GPU/battery)
 *     - fov: 45
 *     - lazyLoad: true
 *     - pointerEvents: 'none'
 *
 *   ShaderGradient props:
 *     - control: 'props'
 *     - animate: 'on' | 'off' (respects prefers-reduced-motion)
 *     - type: 'waterPlane'
 *     - color1: '#002583' (Strong Blue)
 *     - color2: '#FFB800' (Mustard Gold)
 *     - color3: '#E5E8EF' (Cool Light Gray)
 *     - uSpeed: 0.16
 *     - uStrength: 1.35
 *     - uDensity: 1.15
 *     - uFrequency: 3.2
 *     - uAmplitude: 1.8
 *     - cAzimuthAngle: 180
 *     - cPolarAngle: 80
 *     - cDistance: 2.8
 *     - cameraZoom: 1.0
 *     - lightType: '3d'
 *     - brightness: 1.08
 *     - grain: 'on'
 */
(function () {
  'use strict';

  var OFFICIAL_SHADER_GRADIENT_CONFIG = {
    canvas: {
      pixelDensity: 1.0,
      mobilePixelDensity: 0.75,
      fov: 45,
      lazyLoad: true,
      pointerEvents: 'none'
    },
    gradient: {
      control: 'props',
      animate: 'on',
      type: 'waterPlane',
      color1: '#002583',
      color2: '#FFB800',
      color3: '#E5E8EF',
      uSpeed: 0.16,
      uTime: 1.4,
      uStrength: 1.35,
      uDensity: 1.15,
      uFrequency: 3.2,
      uAmplitude: 1.8,
      cAzimuthAngle: 180,
      cPolarAngle: 80,
      cDistance: 2.8,
      cameraZoom: 1.0,
      lightType: '3d',
      brightness: 1.08,
      grain: 'on'
    }
  };

  function hexToNormalizedRgb(hex) {
    var clean = String(hex || '').replace('#', '').trim();
    if (clean.length === 3) {
      clean = clean[0] + clean[0] + clean[1] + clean[1] + clean[2] + clean[2];
    }
    var num = parseInt(clean, 16);
    if (isNaN(num)) {
      return [0, 0.145, 0.514];
    }
    return [
      ((num >> 16) & 255) / 255,
      ((num >> 8) & 255) / 255,
      (num & 255) / 255
    ];
  }

  var VERTEX_SHADER_SOURCE = [
    'attribute vec2 aPosition;',
    'varying vec2 vUv;',
    'void main() {',
    '  vUv = aPosition * 0.5 + 0.5;',
    '  gl_Position = vec4(aPosition, 0.0, 1.0);',
    '}'
  ].join('\n');

  /*
   * 3D Flowing WaterPlane / Organic Fold Shader using 3D Simplex Noise,
   * finite-difference surface normals, 3D directional + rim lighting,
   * and strictly the 3 official brand colour uniforms (uColor1, uColor2, uColor3).
   */
  var FRAGMENT_SHADER_SOURCE = [
    'precision mediump float;',
    'varying vec2 vUv;',
    'uniform vec2 uResolution;',
    'uniform float uTime;',
    'uniform float uSpeed;',
    'uniform float uStrength;',
    'uniform float uDensity;',
    'uniform float uFrequency;',
    'uniform float uAmplitude;',
    'uniform float uBrightness;',
    'uniform float uGrain;',
    'uniform float uFov;',
    'uniform float uCameraZoom;',
    'uniform vec3 uColor1;', // #002583 Strong Blue
    'uniform vec3 uColor2;', // #FFB800 Mustard Gold
    'uniform vec3 uColor3;', // #E5E8EF Cool Light Gray
    '',
    'vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }',
    'vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }',
    'vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }',
    'vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }',
    '',
    'float snoise(vec3 v) {',
    '  const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);',
    '  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);',
    '  vec3 i  = floor(v + dot(v, C.yyy));',
    '  vec3 x0 = v - i + dot(i, C.xxx);',
    '  vec3 g = step(x0.yzx, x0.xyz);',
    '  vec3 l = 1.0 - g;',
    '  vec3 i1 = min(g.xyz, l.zxy);',
    '  vec3 i2 = max(g.xyz, l.zxy);',
    '  vec3 x1 = x0 - i1 + C.xxx;',
    '  vec3 x2 = x0 - i2 + C.yyy;',
    '  vec3 x3 = x0 - D.yyy;',
    '  i = mod289(i);',
    '  vec4 p = permute(permute(permute(',
    '             i.z + vec4(0.0, i1.z, i2.z, 1.0))',
    '           + i.y + vec4(0.0, i1.y, i2.y, 1.0))',
    '           + i.x + vec4(0.0, i1.x, i2.x, 1.0));',
    '  float n_ = 0.142857142857;',
    '  vec3 ns = n_ * D.wyz - D.xzx;',
    '  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);',
    '  vec4 x_ = floor(j * ns.z);',
    '  vec4 y_ = floor(j - 7.0 * x_);',
    '  vec4 x = x_ * ns.x + ns.yyyy;',
    '  vec4 y = y_ * ns.x + ns.yyyy;',
    '  vec4 h = 1.0 - abs(x) - abs(y);',
    '  vec4 b0 = vec4(x.xy, y.xy);',
    '  vec4 b1 = vec4(x.zw, y.zw);',
    '  vec4 s0 = floor(b0) * 2.0 + 1.0;',
    '  vec4 s1 = floor(b1) * 2.0 + 1.0;',
    '  vec4 sh = -step(h, vec4(0.0));',
    '  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;',
    '  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;',
    '  vec3 p0 = vec3(a0.xy, h.x);',
    '  vec3 p1 = vec3(a0.zw, h.y);',
    '  vec3 p2 = vec3(a1.xy, h.z);',
    '  vec3 p3 = vec3(a1.zw, h.w);',
    '  vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));',
    '  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;',
    '  vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);',
    '  m = m * m;',
    '  return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));',
    '}',
    '',
    'float surfaceElevation(vec2 p, float t) {',
    '  vec2 q = p * (uDensity * 1.15);',
    '  float n1 = snoise(vec3(q * 0.85, t * 0.45));',
    '  float n2 = snoise(vec3(q * (uFrequency * 0.48) + vec2(n1 * 0.45, -t * 0.25), t * 0.35));',
    '  float n3 = snoise(vec3(q * 0.45 - vec2(t * 0.18, n2 * 0.3), t * 0.2));',
    '  return (n1 * 0.52 + n2 * 0.33 + n3 * 0.15) * uStrength * (uAmplitude * 0.45);',
    '}',
    '',
    'void main() {',
    '  float aspect = uResolution.x / max(uResolution.y, 1.0);',
    '  float fovScale = tan(radians(uFov) * 0.5) / max(uCameraZoom, 0.1);',
    '  vec2 p = (vUv - 0.5) * vec2(aspect, 1.0) * fovScale * 2.1;',
    '  float t = uTime * uSpeed;',
    '',
    '  float eps = 0.015;',
    '  float hCenter = surfaceElevation(p, t);',
    '  float hRight  = surfaceElevation(p + vec2(eps, 0.0), t);',
    '  float hUp     = surfaceElevation(p + vec2(0.0, eps), t);',
    '',
    '  vec3 normal = normalize(vec3(hCenter - hRight, hCenter - hUp, eps * 2.4));',
    '',
    '  // Cinematic 3D directional lighting from upper-right + soft cool fill light',
    '  vec3 lightDir1 = normalize(vec3(0.55, 0.48, 0.68));',
    '  vec3 lightDir2 = normalize(vec3(-0.6, -0.35, 0.7));',
    '  vec3 viewDir   = vec3(0.0, 0.0, 1.0);',
    '',
    '  float diff1 = max(dot(normal, lightDir1), 0.0);',
    '  float diff2 = max(dot(normal, lightDir2), 0.0);',
    '  vec3 halfVec = normalize(lightDir1 + viewDir);',
    '  float spec = pow(max(dot(normal, halfVec), 0.0), 22.0);',
    '  float fresnel = pow(1.0 - max(dot(normal, viewDir), 0.0), 2.4);',
    '',
    '  // Base composition: Deep Strong Blue (#002583) with subtle tonal depth',
    '  vec3 deepBlue = uColor1 * 0.52;',
    '  float blueFlow = smoothstep(-0.85, 0.85, hCenter + 0.15 * diff2);',
    '  vec3 col = mix(deepBlue, uColor1, blueFlow);',
    '',
    '  // Controlled Mustard Gold (#FFB800) illumination ribbons on warm-lit folds',
    '  float goldRibbon = smoothstep(0.18, 0.88, hCenter * 0.65 + diff1 * 0.55 - 0.12);',
    '  float goldMask = smoothstep(-0.2, 0.75, vUv.x * 0.7 + vUv.y * 0.5);',
    '  col = mix(col, uColor2, clamp(goldRibbon * goldMask * 0.46, 0.0, 0.52));',
    '',
    '  // Cool Light Gray (#E5E8EF) soft highlights & specular sheen',
    '  float coolHighlight = clamp(spec * 0.42 + fresnel * 0.28 + smoothstep(0.45, 1.0, diff2) * 0.14, 0.0, 0.42);',
    '  col = mix(col, uColor3, coolHighlight);',
    '',
    '  // Subtle film grain when grain == "on"',
    '  if (uGrain > 0.5) {',
    '    float grainNoise = fract(sin(dot(vUv * uResolution, vec2(12.9898, 78.233))) * 43758.5453);',
    '    col += (grainNoise - 0.5) * 0.018;',
    '  }',
    '',
    '  col *= uBrightness;',
    '  gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);',
    '}'
  ].join('\n');

  function compileShader(gl, type, source) {
    var shader = gl.createShader(type);
    if (!shader) return null;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      gl.deleteShader(shader);
      return null;
    }
    return shader;
  }

  function createShaderProgram(gl, vsSource, fsSource) {
    var vs = compileShader(gl, gl.VERTEX_SHADER, vsSource);
    var fs = compileShader(gl, gl.FRAGMENT_SHADER, fsSource);
    if (!vs || !fs) return null;

    var program = gl.createProgram();
    if (!program) return null;
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);

    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      gl.deleteProgram(program);
      return null;
    }
    return program;
  }

  function parseMountConfig(mountEl) {
    var cfg = JSON.parse(JSON.stringify(OFFICIAL_SHADER_GRADIENT_CONFIG));
    var ds = mountEl.dataset || {};

    if (ds.color1) cfg.gradient.color1 = ds.color1;
    if (ds.color2) cfg.gradient.color2 = ds.color2;
    if (ds.color3) cfg.gradient.color3 = ds.color3;
    if (ds.uSpeed) cfg.gradient.uSpeed = parseFloat(ds.uSpeed);
    if (ds.uStrength) cfg.gradient.uStrength = parseFloat(ds.uStrength);
    if (ds.uDensity) cfg.gradient.uDensity = parseFloat(ds.uDensity);
    if (ds.uFrequency) cfg.gradient.uFrequency = parseFloat(ds.uFrequency);
    if (ds.uAmplitude) cfg.gradient.uAmplitude = parseFloat(ds.uAmplitude);
    if (ds.brightness) cfg.gradient.brightness = parseFloat(ds.brightness);
    if (ds.pixelDensity) cfg.canvas.pixelDensity = parseFloat(ds.pixelDensity);
    if (ds.fov) cfg.canvas.fov = parseFloat(ds.fov);
    if (ds.animate) cfg.gradient.animate = ds.animate;
    if (ds.grain) cfg.gradient.grain = ds.grain;

    return cfg;
  }

  function initShaderGradientMount(mountEl) {
    if (!mountEl || mountEl.dataset.shaderInitialized === 'true') return;
    mountEl.dataset.shaderInitialized = 'true';

    var cfg = parseMountConfig(mountEl);
    var canvas = mountEl.querySelector('canvas.shadergradient-canvas');
    if (!canvas) {
      canvas = document.createElement('canvas');
      canvas.className = 'shadergradient-canvas';
      canvas.setAttribute('aria-hidden', 'true');
      canvas.setAttribute('tabindex', '-1');
      canvas.setAttribute('role', 'presentation');
      mountEl.appendChild(canvas);
    }

    var reducedMotionQuery = window.matchMedia
      ? window.matchMedia('(prefers-reduced-motion: reduce)')
      : { matches: false };

    var gl = null;
    try {
      gl =
        canvas.getContext('webgl', {
          alpha: false,
          antialias: false,
          depth: false,
          stencil: false,
          preserveDrawingBuffer: false,
          powerPreference: 'low-power'
        }) ||
        canvas.getContext('experimental-webgl', {
          alpha: false,
          antialias: false,
          depth: false,
          stencil: false
        });
    } catch (err) {
      gl = null;
    }

    if (!gl) {
      mountEl.setAttribute('data-shader-state', 'fallback');
      return;
    }

    var program = createShaderProgram(gl, VERTEX_SHADER_SOURCE, FRAGMENT_SHADER_SOURCE);
    if (!program) {
      mountEl.setAttribute('data-shader-state', 'fallback');
      return;
    }

    gl.useProgram(program);

    var vertices = new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]);
    var buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);

    var aPosition = gl.getAttribLocation(program, 'aPosition');
    gl.enableVertexAttribArray(aPosition);
    gl.vertexAttribPointer(aPosition, 2, gl.FLOAT, false, 0, 0);

    var uniforms = {
      uResolution: gl.getUniformLocation(program, 'uResolution'),
      uTime: gl.getUniformLocation(program, 'uTime'),
      uSpeed: gl.getUniformLocation(program, 'uSpeed'),
      uStrength: gl.getUniformLocation(program, 'uStrength'),
      uDensity: gl.getUniformLocation(program, 'uDensity'),
      uFrequency: gl.getUniformLocation(program, 'uFrequency'),
      uAmplitude: gl.getUniformLocation(program, 'uAmplitude'),
      uBrightness: gl.getUniformLocation(program, 'uBrightness'),
      uGrain: gl.getUniformLocation(program, 'uGrain'),
      uFov: gl.getUniformLocation(program, 'uFov'),
      uCameraZoom: gl.getUniformLocation(program, 'uCameraZoom'),
      uColor1: gl.getUniformLocation(program, 'uColor1'),
      uColor2: gl.getUniformLocation(program, 'uColor2'),
      uColor3: gl.getUniformLocation(program, 'uColor3')
    };

    var c1 = hexToNormalizedRgb(cfg.gradient.color1);
    var c2 = hexToNormalizedRgb(cfg.gradient.color2);
    var c3 = hexToNormalizedRgb(cfg.gradient.color3);

    var isMobileViewport = function () {
      return window.innerWidth < 768;
    };

    function applyStaticUniforms() {
      var mobile = isMobileViewport();
      gl.uniform1f(uniforms.uSpeed, cfg.gradient.uSpeed);
      gl.uniform1f(uniforms.uStrength, mobile ? cfg.gradient.uStrength * 0.85 : cfg.gradient.uStrength);
      gl.uniform1f(uniforms.uDensity, mobile ? cfg.gradient.uDensity * 0.85 : cfg.gradient.uDensity);
      gl.uniform1f(uniforms.uFrequency, cfg.gradient.uFrequency);
      gl.uniform1f(uniforms.uAmplitude, cfg.gradient.uAmplitude);
      gl.uniform1f(uniforms.uBrightness, cfg.gradient.brightness);
      gl.uniform1f(uniforms.uGrain, cfg.gradient.grain === 'on' && !mobile ? 1.0 : 0.0);
      gl.uniform1f(uniforms.uFov, cfg.canvas.fov);
      gl.uniform1f(uniforms.uCameraZoom, cfg.gradient.cameraZoom);
      gl.uniform3f(uniforms.uColor1, c1[0], c1[1], c1[2]);
      gl.uniform3f(uniforms.uColor2, c2[0], c2[1], c2[2]);
      gl.uniform3f(uniforms.uColor3, c3[0], c3[1], c3[2]);
    }

    function resizeCanvas() {
      if (!gl) return;
      var rect = mountEl.getBoundingClientRect();
      var targetDensity = isMobileViewport()
        ? cfg.canvas.mobilePixelDensity
        : cfg.canvas.pixelDensity;
      var dpr = Math.min(window.devicePixelRatio || 1, 1.5) * targetDensity;
      dpr = Math.max(0.65, Math.min(dpr, 1.25));

      var width = Math.max(1, Math.floor(rect.width * dpr));
      var height = Math.max(1, Math.floor(rect.height * dpr));

      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
        gl.viewport(0, 0, width, height);
        gl.uniform2f(uniforms.uResolution, width, height);
      }
      applyStaticUniforms();
    }

    var rafId = null;
    var isVisibleInViewport = true;
    var startTimestamp = null;
    var accumulatedTime = cfg.gradient.uTime || 1.4;

    function renderFrame(timestamp) {
      if (!gl) return;
      if (startTimestamp === null) startTimestamp = timestamp;
      var elapsedSec = (timestamp - startTimestamp) * 0.001;
      startTimestamp = timestamp;
      accumulatedTime += Math.min(elapsedSec, 0.1);

      gl.uniform1f(uniforms.uTime, accumulatedTime);
      gl.drawArrays(gl.TRIANGLES, 0, 6);

      if (shouldAnimate()) {
        rafId = window.requestAnimationFrame(renderFrame);
      } else {
        rafId = null;
      }
    }

    function renderSingleStaticFrame() {
      if (!gl) return;
      gl.uniform1f(uniforms.uTime, accumulatedTime);
      gl.drawArrays(gl.TRIANGLES, 0, 6);
    }

    function shouldAnimate() {
      if (cfg.gradient.animate === 'off') return false;
      if (reducedMotionQuery && reducedMotionQuery.matches) return false;
      if (document.hidden) return false;
      if (!isVisibleInViewport) return false;
      return true;
    }

    function updateLoopState() {
      if (shouldAnimate()) {
        mountEl.setAttribute('data-shader-state', 'ready');
        if (!rafId) {
          startTimestamp = null;
          rafId = window.requestAnimationFrame(renderFrame);
        }
      } else {
        if (rafId) {
          window.cancelAnimationFrame(rafId);
          rafId = null;
        }
        renderSingleStaticFrame();
        mountEl.setAttribute('data-shader-state', 'static');
      }
    }

    canvas.addEventListener(
      'webglcontextlost',
      function (e) {
        e.preventDefault();
        if (rafId) {
          window.cancelAnimationFrame(rafId);
          rafId = null;
        }
        gl = null;
        mountEl.setAttribute('data-shader-state', 'fallback');
      },
      false
    );

    resizeCanvas();
    renderSingleStaticFrame();
    updateLoopState();

    var resizeTimer = null;
    window.addEventListener(
      'resize',
      function () {
        if (resizeTimer) window.clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(function () {
          resizeCanvas();
          renderSingleStaticFrame();
        }, 120);
      },
      { passive: true }
    );

    document.addEventListener('visibilitychange', updateLoopState);

    if (reducedMotionQuery && typeof reducedMotionQuery.addEventListener === 'function') {
      reducedMotionQuery.addEventListener('change', updateLoopState);
    }

    if ('IntersectionObserver' in window) {
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            isVisibleInViewport = entry.isIntersecting;
          });
          updateLoopState();
        },
        { rootMargin: '100px 0px', threshold: 0.01 }
      );
      observer.observe(mountEl);
    }
  }

  function bootShaderGradientMounts() {
    var mounts = document.querySelectorAll('.shadergradient-mount');
    if (!mounts.length) return;

    if ('IntersectionObserver' in window) {
      var lazyObserver = new IntersectionObserver(
        function (entries, obs) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              initShaderGradientMount(entry.target);
              obs.unobserve(entry.target);
            }
          });
        },
        { rootMargin: '160px 0px', threshold: 0.01 }
      );
      for (var i = 0; i < mounts.length; i++) {
        lazyObserver.observe(mounts[i]);
      }
    } else {
      for (var j = 0; j < mounts.length; j++) {
        initShaderGradientMount(mounts[j]);
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootShaderGradientMounts);
  } else {
    bootShaderGradientMounts();
  }

  window.EduManageShaderGradient = {
    config: OFFICIAL_SHADER_GRADIENT_CONFIG,
    initMount: initShaderGradientMount
  };
})();
