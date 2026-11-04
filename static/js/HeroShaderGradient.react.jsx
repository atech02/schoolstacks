/**
 * static/js/HeroShaderGradient.react.jsx
 *
 * Official @shadergradient/react isolated component specification
 * (https://github.com/ruucm/shadergradient).
 *
 * Mirrors the exact props used by static/js/shader-gradient-hero.js in the
 * server-rendered Flask/Jinja2 templates so that if a React bundler is used,
 * this component renders with identical brand colours, camera, and motion.
 */
import React, { useEffect, useState } from 'react';
import { ShaderGradientCanvas, ShaderGradient } from '@shadergradient/react';

export const BRAND_SHADER_PROPS = {
  control: 'props',
  type: 'waterPlane',
  color1: '#002583', // Official Strong Blue
  color2: '#FFB800', // Official Mustard Gold
  color3: '#E5E8EF', // Official Cool Light Gray
  uSpeed: 0.16,
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
  grain: 'on',
};

export default function HeroShaderGradient({ pixelDensity = 1.0, fov = 45 }) {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPrefersReducedMotion(mq.matches);
    const handler = (event) => setPrefersReducedMotion(event.matches);
    if (mq.addEventListener) {
      mq.addEventListener('change', handler);
      return () => mq.removeEventListener('change', handler);
    }
    return undefined;
  }, []);

  return (
    <div
      className="shadergradient-mount"
      aria-hidden="true"
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
      }}
    >
      <ShaderGradientCanvas
        lazyLoad={true}
        pixelDensity={pixelDensity}
        fov={fov}
        pointerEvents="none"
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          pointerEvents: 'none',
        }}
      >
        <ShaderGradient
          {...BRAND_SHADER_PROPS}
          animate={prefersReducedMotion ? 'off' : 'on'}
        />
      </ShaderGradientCanvas>
    </div>
  );
}
