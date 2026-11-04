import React from 'react';
import { Link } from 'react-router-dom';
import { ShaderGradientHero } from '../components/ShaderGradientHero';
import { useAuth } from '../hooks/useAuth';
import { Badge } from '../components/ui';
import { BrandLogo } from '../components/BrandLogo';

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

      {/* Hero Section — 3-Layer Composition: Base Strong Blue + ShaderGradient + Blended heropic.png */}
      <section
        className="shadergradient-hero-stage"
        style={{
          padding: '140px 5% 96px',
          minHeight: 640,
          display: 'flex',
          alignItems: 'center',
        }}
      >
        <ShaderGradientHero
          color1="#002583"
          color2="#FFB800"
          color3="#E5E8EF"
          uSpeed={0.14}
          uStrength={1.32}
          uDensity={1.12}
          uFrequency={3.1}
          uAmplitude={1.75}
          brightness={1.06}
          pixelDensity={1.0}
          fov={45}
          animate="on"
          grain="on"
        />
        <div className="hero-readability-scrim" aria-hidden="true" />

        <div className="container" style={{ position: 'relative', zIndex: 3 }}>
          <div className="row align-items-center g-4 g-lg-5">
            <div className="col-lg-6 hero-content-column">
              <div
                className="d-inline-flex align-items-center gap-2 px-3 py-1 rounded-pill mb-3 text-uppercase"
                style={{
                  background: 'rgba(255, 184, 0, 0.16)',
                  border: '1px solid rgba(255, 184, 0, 0.48)',
                  color: 'var(--color-mustard)',
                  fontSize: 'var(--font-size-xs)',
                  fontWeight: 'var(--font-weight-semibold)',
                  letterSpacing: '0.08em',
                }}
              >
                <i className="bi bi-stars" /> Built for Zambian &amp; African Schools
              </div>

              <h1 className="edu-hero-heading mb-3" style={{ textShadow: '0 2px 18px rgba(0, 24, 88, 0.5)' }}>
                Run Your Entire School{' '}
                <span style={{ color: 'var(--color-mustard)', display: 'block' }}>
                  From One Unified Platform
                </span>
              </h1>

              <p
                style={{
                  color: 'var(--color-cool-gray)',
                  fontSize: 'var(--font-size-base)',
                  lineHeight: 1.6,
                  maxWidth: 560,
                  marginBottom: 28,
                }}
              >
                Manage admissions, class timetables, attendance, and automated report cards while
                collecting school fees online in ZMW via{' '}
                <strong className="text-white">
                  supported Mobile Money (MTN, Airtel, Zamtel) &amp; Cards
                </strong>
                .
              </p>

              <div className="d-flex align-items-center gap-3 flex-wrap">
                <Link
                  to={authenticated ? portalHref() : '/register'}
                  className="edu-btn edu-btn-accent"
                  style={{ padding: '10px 22px', fontSize: 'var(--font-size-sm)' }}
                >
                  {authenticated ? 'Go to Your Dashboard' : 'Register Your School'}
                  <i className="bi bi-arrow-right" />
                </Link>
                <Link
                  to="/login"
                  className="edu-btn"
                  style={{
                    padding: '10px 20px',
                    fontSize: 'var(--font-size-sm)',
                    background: 'rgba(229, 232, 239, 0.14)',
                    color: '#FFFFFF',
                    border: '1.5px solid rgba(229, 232, 239, 0.38)',
                  }}
                >
                  <i className="bi bi-box-arrow-in-right" /> Portal Sign In
                </Link>
              </div>

              <div
                className="d-flex align-items-center gap-4 flex-wrap mt-4 pt-1"
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

            <div className="col-lg-6">
              <div className="hero-image-stage">
                <div className="hero-image-aura" aria-hidden="true" />
                <div className="hero-image-float-wrap">
                  <div className="hero-image-blend-mask">
                    <img
                      src="/images/heropic.png"
                      alt="Students collaborating on digital learning tablets in uniform"
                      className="hero-blended-photo"
                      loading="eager"
                      decoding="async"
                    />
                    <div className="hero-image-edge-blend" aria-hidden="true" />
                    <div className="hero-image-color-harmonizer" aria-hidden="true" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section — Cool Light Gray (#E5E8EF) surface */}
      <section id="features" className="py-5 px-3" style={{ background: 'var(--color-cool-gray)' }}>
        <div className="container py-4">
          <div className="text-center mb-5">
            <Badge variant="mustard">UNIFIED SCHOOL PLATFORM</Badge>
            <h2 className="fw-bold mt-2">Dedicated Portals for Every Role</h2>
            <p className="text-muted mx-auto" style={{ maxWidth: 620 }}>
              Designed with a clean, high-contrast interface across desktop, tablet, and installable
              mobile PWA.
            </p>
          </div>

          <div className="row g-4">
            {[
              {
                icon: 'bi-building-check',
                title: 'School Administration',
                desc: 'Register students & teachers, configure classes, subjects, terms, fee structures, timetables, and school-wide announcements.',
              },
              {
                icon: 'bi-phone-vibrate',
                title: 'Mobile Money & Card Payments',
                desc: 'Parents and students pay school fees online in ZMW using supported mobile money services (MTN, Airtel, Zamtel) or debit/credit cards with instant RCT-xxxxx receipts.',
              },
              {
                icon: 'bi-journal-check',
                title: 'Teacher & Academic Suite',
                desc: 'Mark daily class attendance, enter exam scores with automatic ECZ grading, upload study materials, and grade assignments.',
              },
              {
                icon: 'bi-people-fill',
                title: 'Parent & Student Portals',
                desc: 'Track real-time attendance, download official term report cards, submit homework, and clear fee balances from any phone.',
              },
            ].map((f, i) => (
              <div className="col-md-6 col-lg-3" key={i}>
                <div className="edu-card h-100 p-4">
                  <div className="edu-stat-icon mustard mb-3">
                    <i className={`bi ${f.icon}`} />
                  </div>
                  <h5 className="fw-bold mb-2">{f.title}</h5>
                  <p className="small text-muted mb-0">{f.desc}</p>
                </div>
              </div>
            ))}
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

      {/* Footer — Strong Blue (#002583) with Brand Logo, Slogan & Mustard Gold border */}
      <footer
        className="py-4 text-white small"
        style={{
          background: 'var(--color-strong-blue)',
          borderTop: '3px solid var(--color-mustard)',
        }}
      >
        <div className="container d-flex flex-column flex-md-row justify-content-between align-items-center gap-3">
          <div className="d-flex align-items-center gap-3">
            <BrandLogo showSlogan={true} theme="light" size="sm" />
          </div>
          <div style={{ color: 'var(--color-cool-gray)', fontSize: 'var(--font-size-xs)' }}>
            Multi-Tenant School Management Platform &bull; Secure Online Payments &bull; Web &amp; Installable PWA
          </div>
        </div>
      </footer>
    </div>
  );
};
