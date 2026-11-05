import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { BrandLogo } from './BrandLogo';

export const Footer: React.FC = () => {
  const PRODUCTION_PWA_URL = 'https://schoolstacks.vercel.app';

  const [deferredPrompt, setDeferredPrompt] = useState<any>(null);
  const [isInstalled, setIsInstalled] = useState(false);
  const [showInstallModal, setShowInstallModal] = useState(false);
  const [copied, setCopied] = useState(false);
  const [isIos, setIsIos] = useState(false);

  useEffect(() => {
    // Detect if already installed (standalone display mode)
    const isStandalone =
      window.matchMedia('(display-mode: standalone)').matches ||
      (window.navigator as any).standalone === true;

    if (isStandalone) {
      setIsInstalled(true);
    }

    // Detect iOS device
    const userAgent = window.navigator.userAgent.toLowerCase();
    const isIosDevice = /iphone|ipad|ipod/.test(userAgent);
    setIsIos(isIosDevice);

    const handleBeforeInstallPrompt = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e);
    };

    const handleAppInstalled = () => {
      setIsInstalled(true);
      setDeferredPrompt(null);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    window.addEventListener('appinstalled', handleAppInstalled);

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
      window.removeEventListener('appinstalled', handleAppInstalled);
    };
  }, []);

  const handleInstallClick = async () => {
    if (isInstalled) {
      setShowInstallModal(true);
      return;
    }

    if (deferredPrompt) {
      try {
        deferredPrompt.prompt();
        const choice = await deferredPrompt.userChoice;
        if (choice.outcome === 'accepted') {
          setIsInstalled(true);
        }
        setDeferredPrompt(null);
      } catch (err) {
        setShowInstallModal(true);
      }
    } else {
      setShowInstallModal(true);
    }
  };

  const handleCopyLink = () => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(PRODUCTION_PWA_URL).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2500);
      });
    }
  };

  return (
    <footer className="site-footer" aria-label="Website footer">
      <div className="container py-5">
        <div className="row g-4 g-lg-5">
          {/* Column 1 — School-Magi Brand & Overview */}
          <div className="col-12 col-md-6 col-lg-3">
            <div className="mb-3">
              <BrandLogo showSlogan={true} theme="light" size="sm" />
            </div>
            <p className="footer-description mb-3">
              A comprehensive digital school operating system powering student admissions, timetables, ECZ grade reports, and instant fee collections in ZMW.
            </p>
            <div className="d-flex align-items-center gap-2 text-white-50 small">
              <i className="bi bi-shield-check text-warning" aria-hidden="true" />
              <span>Multi-Tenant School Isolation</span>
            </div>
          </div>

          {/* Column 2 — Quick Links */}
          <div className="col-6 col-md-6 col-lg-2">
            <h6 className="footer-heading">Quick Links</h6>
            <ul className="footer-links list-unstyled mb-0">
              <li>
                <Link to="/" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
                  <i className="bi bi-chevron-right me-1" aria-hidden="true" /> Home
                </Link>
              </li>
              <li>
                <a href="#features">
                  <i className="bi bi-chevron-right me-1" aria-hidden="true" /> Features
                </a>
              </li>
              <li>
                <a href="#contact">
                  <i className="bi bi-chevron-right me-1" aria-hidden="true" /> Contact
                </a>
              </li>
              <li>
                <Link to="/login">
                  <i className="bi bi-chevron-right me-1" aria-hidden="true" /> Login
                </Link>
              </li>
            </ul>
          </div>

          {/* Column 3 — Contact Us */}
          <div id="contact" className="col-6 col-md-6 col-lg-3">
            <h6 className="footer-heading">Contact Us</h6>
            <p className="footer-contact-note mb-2 small text-white-50">
              Official inquiries, onboarding, and platform support:
            </p>
            <div className="footer-email-box">
              <a
                href="mailto:edumanage@gmail.com"
                className="footer-email-link"
                title="Send an email to edumanage@gmail.com"
              >
                <span className="footer-email-icon-wrap" aria-hidden="true">
                  <i className="bi bi-envelope-at-fill" />
                </span>
                <span className="footer-email-text">edumanage@gmail.com</span>
              </a>
            </div>
            <div className="mt-3 text-white-50 small d-flex align-items-center gap-2">
              <i className="bi bi-clock-history text-warning" aria-hidden="true" />
              <span>Support Hours: Mon – Fri (08:00 – 17:00 CAT)</span>
            </div>
          </div>

          {/* Column 4 — Download School-Magi App */}
          <div className="col-12 col-md-6 col-lg-4">
            <h6 className="footer-heading">Download School-Magi App</h6>
            <div className="footer-pwa-card p-3 rounded-3">
              <div className="d-flex align-items-start gap-2 mb-2">
                <div className="pwa-badge-icon" aria-hidden="true">
                  <i className="bi bi-phone-fill" />
                </div>
                <div>
                  <div className="fw-semibold text-white small">Installable Web Application</div>
                  <div className="text-white-50 extra-small">Fast &bull; Offline-ready &bull; Standalone</div>
                </div>
              </div>
              <p className="footer-pwa-text small mb-3">
                Install School-Magi on your device for convenient access anytime.
              </p>
              <button
                type="button"
                className={`pwa-install-btn w-100 ${isInstalled ? 'installed' : ''}`}
                onClick={handleInstallClick}
                aria-label={isInstalled ? 'App already installed' : 'Install School-Magi App'}
              >
                {isInstalled ? (
                  <>
                    <i className="bi bi-check2-circle me-2" aria-hidden="true" />
                    App Installed
                  </>
                ) : (
                  <>
                    <i className="bi bi-download me-2" aria-hidden="true" />
                    Install App
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Bottom Footer Line */}
        <div className="footer-bottom mt-5 pt-4 border-top border-white-10 d-flex flex-column flex-md-row align-items-center justify-content-between gap-2 text-white-50 small">
          <div>
            &copy; {new Date().getFullYear()} School-Magi &bull; SchoolStacks Platform. All rights reserved.
          </div>
          <div className="d-flex align-items-center gap-3">
            <span>Built for Zambian &amp; African Schools</span>
            <span>&bull;</span>
            <span className="text-warning">Lipila Online Payments</span>
          </div>
        </div>
      </div>

      {/* PWA Installation Instructions Modal */}
      {showInstallModal && (
        <div
          className="pwa-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="pwa-modal-title"
          onClick={() => setShowInstallModal(false)}
        >
          <div className="pwa-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="d-flex justify-content-between align-items-center mb-3">
              <div className="d-flex align-items-center gap-2">
                <div className="pwa-modal-icon">
                  <i className="bi bi-phone-vibrate-fill" />
                </div>
                <h5 id="pwa-modal-title" className="mb-0 fw-bold" style={{ color: 'var(--color-strong-blue)' }}>
                  {isInstalled ? 'App Already Installed' : 'Install School-Magi'}
                </h5>
              </div>
              <button
                type="button"
                className="btn-close"
                onClick={() => setShowInstallModal(false)}
                aria-label="Close"
              />
            </div>

            {isInstalled ? (
              <div>
                <p className="text-muted small">
                  School-Magi is already installed on your device in standalone mode. You can launch it directly from your home screen or application launcher.
                </p>
                <div className="alert alert-success d-flex align-items-center gap-2 small mb-3">
                  <i className="bi bi-check-circle-fill text-success" />
                  <span>Verified production instance: <strong>{PRODUCTION_PWA_URL}</strong></span>
                </div>
              </div>
            ) : isIos ? (
              <div>
                <p className="text-muted small mb-3">
                  To install School-Magi on your iPhone or iPad:
                </p>
                <ol className="pwa-steps-list small text-muted mb-3 ps-3">
                  <li className="mb-2">
                    Open Safari and navigate to <strong className="text-dark">{PRODUCTION_PWA_URL}</strong>
                  </li>
                  <li className="mb-2">
                    Tap the <strong>Share</strong> button (the square icon with an arrow pointing upward) in the Safari toolbar.
                  </li>
                  <li className="mb-2">
                    Scroll down and tap <strong>Add to Home Screen</strong>.
                  </li>
                  <li>
                    Tap <strong>Add</strong> in the top right corner.
                  </li>
                </ol>
              </div>
            ) : (
              <div>
                <p className="text-muted small mb-3">
                  To install School-Magi on your Android device or computer:
                </p>
                <ol className="pwa-steps-list small text-muted mb-3 ps-3">
                  <li className="mb-2">
                    Open this website in <strong>Google Chrome</strong>, <strong>Microsoft Edge</strong>, or any Chromium browser.
                  </li>
                  <li className="mb-2">
                    Click the <strong>Install</strong> icon in the address bar (or select <em>Install School-Magi</em> from the browser menu <strong>&vellip;</strong>).
                  </li>
                  <li>
                    Confirm installation when prompted.
                  </li>
                </ol>
              </div>
            )}

            <div className="pwa-modal-actions pt-2 border-top d-flex justify-content-between align-items-center gap-2">
              <button
                type="button"
                className="edu-btn edu-btn-outline edu-btn-sm"
                onClick={handleCopyLink}
              >
                <i className={`bi ${copied ? 'bi-check2' : 'bi-clipboard'} me-1`} />
                {copied ? 'Link Copied!' : 'Copy App Link'}
              </button>
              <button
                type="button"
                className="edu-btn edu-btn-accent edu-btn-sm"
                onClick={() => setShowInstallModal(false)}
              >
                Got It
              </button>
            </div>
          </div>
        </div>
      )}
    </footer>
  );
};
