import React from 'react';

export interface DashboardHeaderProps {
  title?: string;
  subtitle?: string;
  userName?: string;
  userRole?: string;
  schoolName?: string;
  academicYear?: string;
  academicTerm?: string;
  dateString?: string;
  badgeText?: string;
  badgeVariant?: 'gold' | 'blue' | 'green';
  quickStats?: Array<{
    label: string;
    value: string | number;
    icon?: string;
  }>;
  actions?: React.ReactNode;
}

export const DashboardHeader: React.FC<DashboardHeaderProps> = ({
  title,
  subtitle,
  userName,
  userRole,
  schoolName,
  academicYear = '2026',
  academicTerm,
  dateString,
  badgeText,
  badgeVariant = 'gold',
  quickStats = [],
  actions,
}) => {
  const currentDate =
    dateString ||
    new Date().toLocaleDateString('en-GB', {
      weekday: 'long',
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });

  return (
    <div className="edu-dashboard-hero mb-4">
      <div className="edu-dashboard-hero-content">
        <div className="d-flex flex-column flex-lg-row align-items-start align-items-lg-center justify-content-between gap-3">
          {/* Left Column: Greeting & Info */}
          <div>
            <div className="d-flex align-items-center flex-wrap gap-2 mb-2">
              {schoolName && (
                <span className="edu-hero-pill edu-hero-pill-school">
                  <i className="bi bi-buildings-fill me-1" />
                  {schoolName}
                </span>
              )}
              {academicTerm && (
                <span className="edu-hero-pill edu-hero-pill-term">
                  <i className="bi bi-calendar3 me-1" />
                  {academicTerm} ({academicYear})
                </span>
              )}
              {badgeText && (
                <span
                  className={`edu-hero-pill ${
                    badgeVariant === 'green'
                      ? 'edu-hero-pill-green'
                      : badgeVariant === 'blue'
                      ? 'edu-hero-pill-blue'
                      : 'edu-hero-pill-gold'
                  }`}
                >
                  <i className="bi bi-patch-check-fill me-1" />
                  {badgeText}
                </span>
              )}
              <span className="edu-hero-pill edu-hero-pill-date">
                <i className="bi bi-clock-history me-1" />
                {currentDate}
              </span>
            </div>

            <h1 className="edu-hero-title mb-1">
              {userName ? (
                <>
                  Welcome back, <span className="edu-hero-accent">{userName}</span>! 👋
                </>
              ) : (
                title || 'Dashboard Overview'
              )}
            </h1>

            <p className="edu-hero-subtitle mb-0">
              {subtitle ||
                (userRole
                  ? `Access your ${userRole.toLowerCase()} controls, academic records, and real-time operational insights.`
                  : 'Manage and monitor all school operations from your unified SchoolStacks command centre.')}
            </p>
          </div>

          {/* Right Column: Quick Stats & Actions */}
          <div className="d-flex flex-wrap align-items-center gap-2 mt-2 mt-lg-0">
            {quickStats.map((stat, idx) => (
              <div key={idx} className="edu-hero-stat-badge">
                {stat.icon && <i className={`bi ${stat.icon} me-1.5`} />}
                <span className="edu-hero-stat-label">{stat.label}:</span>
                <span className="edu-hero-stat-val">{stat.value}</span>
              </div>
            ))}
            {actions && <div className="d-flex gap-2 ms-lg-2">{actions}</div>}
          </div>
        </div>
      </div>

      {/* Decorative Background Elements */}
      <div className="edu-dashboard-hero-glow" aria-hidden="true" />
      <svg
        className="edu-dashboard-hero-mesh"
        viewBox="0 0 1000 200"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
        preserveAspectRatio="none"
      >
        <path
          d="M0 160C200 120 400 200 600 140C800 80 900 130 1000 100V200H0V160Z"
          fill="rgba(255, 184, 0, 0.05)"
        />
        <path
          d="M0 130C300 80 500 180 750 110C900 70 950 120 1000 90V200H0V130Z"
          fill="rgba(255, 255, 255, 0.04)"
        />
      </svg>
    </div>
  );
};
