import React from 'react';
import { Link } from 'react-router-dom';
import { ShaderGradientHero } from '../components/ShaderGradientHero';
import { useAuth } from '../hooks/useAuth';
import { Badge } from '../components/ui';
import { BrandLogo } from '../components/BrandLogo';
import { Footer } from '../components/Footer';

export const LandingPage: React.FC = () => {
  const { authenticated, user, pricing } = useAuth();

  const portalHref = () => {
    if (!authenticated || !user) return '/login';
    if (user.role === 'superadmin') return '/superadmin';
    return `/${user.role}/dashboard`;
  };

  const prices = pricing?.prices || {
    free: { name: 'Free Trial', amount_monthly: 0, amount_yearly: 0, currency: 'ZMW' },
    starter: { name: 'Starter', amount_monthly: 499, amount_yearly: 4990, currency: 'ZMW' },
    growth: { name: 'Growth', amount_monthly: 1200, amount_yearly: 12000, currency: 'ZMW' },
    enterprise: { name: 'Enterprise', amount_monthly: 2200, amount_yearly: 22000, currency: 'ZMW' },
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-background)' }}>
      {/* Top Navbar — Strong Blue (#002583) with Brand Logo, Slogan & Mustard Gold CTA */}
      <header
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 1030,
          minHeight: 74,
          background: 'rgba(0, 37, 131, 0.96)',
          backdropFilter: 'blur(14px)',
          borderBottom: '1px solid rgba(229, 232, 239, 0.16)',
          padding: '10px 5%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
        }}
      >
        <BrandLogo showSlogan={true} theme="light" />

        <nav className="d-flex align-items-center gap-3 gap-md-4">
          <a
            href="#features"
            className="d-none d-md-inline"
            style={{
              color: 'var(--color-cool-gray)',
              fontSize: 'var(--font-size-sm)',
              fontWeight: 'var(--font-weight-medium)',
            }}
          >
            Features
          </a>
          <Link
            to="/pricing"
            style={{
              color: 'var(--color-cool-gray)',
              fontSize: 'var(--font-size-sm)',
              fontWeight: 'var(--font-weight-medium)',
            }}
          >
            Pricing (ZMW)
          </Link>
          {authenticated ? (
            <Link to={portalHref()} className="edu-btn edu-btn-accent edu-btn-sm">
              <i className="bi bi-speedometer2" /> Open Portal
            </Link>
          ) : (
            <>
              <Link
                to="/login"
                style={{
                  color: '#FFFFFF',
                  fontSize: 'var(--font-size-sm)',
                  fontWeight: 'var(--font-weight-medium)',
                }}
              >
                Sign In
              </Link>
              <Link to="/register" className="edu-btn edu-btn-accent edu-btn-sm">
                Start 14-Day Free Trial
              </Link>
            </>
          )}
        </nav>
      </header>

      {/* Hero Section — Full-Width Hero Background with Multi-Layer Gradient Overlay & Left-Aligned Content */}
      <section className="hero-fullscreen-stage" aria-labelledby="hero-heading">
        {/* Layer 1: Ambient Restrained ShaderGradient behind the image for organic brand color motion */}
        <div className="hero-ambient-shader" aria-hidden="true">
          <ShaderGradientHero
            color1="#002583"
            color2="#FFB800"
            color3="#E5E8EF"
            uSpeed={0.10}
            uStrength={1.15}
            uDensity={1.05}
            uFrequency={2.8}
            uAmplitude={1.5}
            brightness={0.98}
            pixelDensity={1.0}
            fov={45}
            animate="on"
            grain="on"
          />
        </div>

        {/* Layer 2: Full-Width Background Image */}
        <div className="hero-bg-media-container" aria-hidden="true">
          <img
            src="/images/heropic.png"
            alt="Students collaborating on digital learning tablets in uniform"
            className="hero-bg-fullscreen-img"
            loading="eager"
            decoding="async"
          />
        </div>

        {/* Layer 3: Multi-Layer Cinematic Gradient Overlay */}
        <div className="hero-cinematic-overlay hero-readability-scrim" aria-hidden="true" />

        {/* Layer 4: Left-Aligned Hero Content */}
        <div className="container" style={{ position: 'relative', zIndex: 10 }}>
          <div className="row">
            <div className="col-12 col-lg-8 col-xl-7 hero-content-column">
              <div
                className="hero-anim-eyebrow d-inline-flex align-items-center gap-2 px-3 py-1 rounded-pill mb-3 text-uppercase"
                style={{
                  background: 'rgba(255, 184, 0, 0.16)',
                  border: '1px solid rgba(255, 184, 0, 0.48)',
                  color: 'var(--color-mustard)',
                  fontSize: 'var(--font-size-xs)',
                  fontWeight: 'var(--font-weight-semibold)',
                  letterSpacing: '0.08em',
                  backdropFilter: 'blur(6px)',
                  WebkitBackdropFilter: 'blur(6px)',
                }}
              >
                <i className="bi bi-stars" /> Built for Zambian &amp; African Schools
              </div>

              <h1 id="hero-heading" className="edu-hero-heading hero-anim-heading mb-3">
                Run Your Entire School{' '}
                <span className="hero-highlight">
                  From One Unified Platform
                </span>
              </h1>

              <p className="hero-description-text hero-anim-description mb-4">
                Manage admissions, class timetables, attendance, and automated report cards while
                collecting school fees online in ZMW via{' '}
                <strong className="text-white">
                  supported Mobile Money (MTN, Airtel, Zamtel) &amp; Cards
                </strong>
                .
              </p>

              <div className="hero-anim-actions d-flex align-items-center gap-3 flex-wrap">
                <Link
                  to={authenticated ? portalHref() : '/register'}
                  className="hero-btn-primary"
                >
                  {authenticated ? 'Go to Your Dashboard' : 'Register Your School'}
                  <i className="bi bi-arrow-right" />
                </Link>
                <Link
                  to="/login"
                  className="hero-btn-secondary"
                >
                  <i className="bi bi-box-arrow-in-right" /> Portal Sign In
                </Link>
              </div>

              <div
                className="hero-anim-trust d-flex align-items-center gap-4 flex-wrap mt-4 pt-1"
                style={{ color: 'var(--color-cool-gray)', fontSize: 'var(--font-size-xs)' }}
              >
                <span>
                  <i className="bi bi-check-circle-fill me-1" style={{ color: 'var(--color-mustard)' }} />
                  14-Day Free Trial
                </span>
                <span>
                  <i className="bi bi-phone-fill me-1" style={{ color: 'var(--color-mustard)' }} />
                  Mobile Money &amp; Card Payments
                </span>
                <span>
                  <i className="bi bi-shield-lock-fill me-1" style={{ color: 'var(--color-mustard)' }} />
                  Multi-Tenant School Isolation
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section — Premium Two-Column Layout (#E5E8EF Surface) */}
      <section id="features" className="features-two-col-section px-3" aria-labelledby="features-heading">
        <div className="container">
          <div className="text-center mb-5">
            <Badge variant="mustard">KEY PLATFORM CAPABILITIES</Badge>
            <h2 id="features-heading" className="fw-bold mt-2" style={{ color: 'var(--color-strong-blue)', fontSize: '2.25rem' }}>
              Everything Your School Needs in One Place
            </h2>
            <p className="text-muted mx-auto" style={{ maxWidth: 620 }}>
              Purpose-built for modern educational institutions across Zambia and Africa with seamless fee collections, instant communication, and centralized management.
            </p>
          </div>

          <div className="row align-items-center g-4 g-lg-5">
            {/* Left Column — Large Feature Image */}
            <div className="col-12 col-lg-6 order-1 order-lg-1">
              <div className="feature-image-wrapper">
                <img
                  src="/images/feature.png"
                  alt="School-Magi feature platform preview"
                  className="feature-preview-img"
                  loading="lazy"
                  decoding="async"
                />
              </div>
            </div>

            {/* Right Column — 3 Vertically Arranged Feature Information Blocks */}
            <div className="col-12 col-lg-6 order-2 order-lg-2">
              <div className="features-list-wrapper">
                {/* FEATURE 1 */}
                <div className="feature-block-card">
                  <div className="feature-icon-badge" aria-hidden="true">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="26"
                      height="26"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <rect width="20" height="14" x="2" y="5" rx="2" />
                      <line x1="2" x2="22" y1="10" y2="10" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="feature-block-title">Seamless Mobile Payments</h3>
                    <p className="feature-block-desc">
                      Accept mobile money and card payments conveniently.
                    </p>
                  </div>
                </div>

                {/* FEATURE 2 */}
                <div className="feature-block-card">
                  <div className="feature-icon-badge" aria-hidden="true">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="26"
                      height="26"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z" />
                      <path d="M8 12h.01" />
                      <path d="M12 12h.01" />
                      <path d="M16 12h.01" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="feature-block-title">Instant SMS Communication</h3>
                    <p className="feature-block-desc">
                      Keep parents and guardians informed with timely updates.
                    </p>
                  </div>
                </div>

                {/* FEATURE 3 */}
                <div className="feature-block-card">
                  <div className="feature-icon-badge" aria-hidden="true">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="26"
                      height="26"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="m4 6 8-4 8 4" />
                      <path d="m18 10 4 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-8l4-2" />
                      <path d="M14 22v-4a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v4" />
                      <path d="M18 5v17" />
                      <path d="M6 5v17" />
                      <circle cx="12" cy="9" r="2" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="feature-block-title">Centralized School Administration</h3>
                    <p className="feature-block-desc">
                      Everything your school needs in one platform.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Transparent ZMW Pricing Preview */}
      <section className="py-5 px-3" style={{ background: 'var(--color-surface)' }}>
        <div className="container py-4">
          <div className="text-center mb-5">
            <h2 className="fw-bold">Transparent School Plans in ZMW</h2>
            <p className="text-muted">Start with a 14-day free trial and choose a subscription plan anytime</p>
          </div>
          <div className="row g-4">
            {(['free', 'starter', 'growth', 'enterprise'] as const).map((planKey) => {
              const p = prices[planKey];
              if (!p) return null;
              const isPopular = planKey === 'growth';
              return (
                <div className="col-md-6 col-lg-3" key={planKey}>
                  <div
                    className="edu-card h-100 p-4 d-flex flex-column"
                    style={
                      isPopular
                        ? {
                            borderTop: '4px solid var(--color-mustard)',
                            boxShadow: 'var(--shadow-hover)',
                          }
                        : { borderTop: '4px solid var(--color-strong-blue)' }
                    }
                  >
                    <div className="d-flex justify-content-between align-items-center mb-2">
                      <span className="fw-bold text-uppercase small" style={{ color: 'var(--color-strong-blue)' }}>
                        {p.name}
                      </span>
                      {isPopular && <Badge variant="mustard">Most Popular</Badge>}
                    </div>
                    <div className="my-3">
                      <span
                        className="fw-bold"
                        style={{ fontSize: '24px', color: 'var(--color-strong-blue)' }}
                      >
                        K{p.amount_monthly}
                      </span>
                      <span className="text-muted ms-1" style={{ fontSize: 'var(--font-size-xs)' }}>/month</span>
                    </div>
                    <ul className="list-unstyled small text-muted flex-grow-1 mb-4">
                      {(pricing?.features?.[planKey] || [
                        'Full multi-role school portal',
                        'Mobile Money & Card fee collections',
                        'Automated PDF report cards',
                      ]).map((feat, idx) => (
                        <li key={idx} className="mb-2 d-flex align-items-start gap-2">
                          <i
                            className="bi bi-check-circle-fill mt-1"
                            style={{ color: 'var(--color-mustard)' }}
                          />
                          <span>{feat}</span>
                        </li>
                      ))}
                    </ul>
                    <Link
                      to="/register"
                      className={`edu-btn w-100 ${isPopular ? 'edu-btn-accent' : 'edu-btn-primary'}`}
                    >
                      Get Started
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Comprehensive Website Footer */}
      <Footer />
    </div>
  );
};
