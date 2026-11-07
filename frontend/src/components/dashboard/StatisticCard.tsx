import React from 'react';

export type StatVariant = 'blue' | 'emerald' | 'amber' | 'purple' | 'rose' | 'cyan';

export interface StatisticCardProps {
  icon: string;
  label: string;
  value: string | number;
  variant?: StatVariant;
  trend?: {
    text: string;
    positive?: boolean | null; // true = up/good, false = down/bad, null = neutral
  };
  subtitle?: string;
  onClick?: () => void;
  className?: string;
}

export const StatisticCard: React.FC<StatisticCardProps> = ({
  icon,
  label,
  value,
  variant = 'blue',
  trend,
  subtitle,
  onClick,
  className = '',
}) => {
  return (
    <div
      className={`edu-stat-card-modern edu-stat-${variant} ${onClick ? 'clickable' : ''} ${className}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => e.key === 'Enter' && onClick() : undefined}
    >
      <div className="d-flex align-items-start justify-content-between gap-3">
        <div className="edu-stat-info">
          <span className="edu-stat-label-modern">{label}</span>
          <div className="edu-stat-value-modern mt-1">{value}</div>
          {subtitle && <div className="edu-stat-subtext mt-1">{subtitle}</div>}
        </div>

        <div className={`edu-stat-icon-box edu-stat-icon-${variant}`}>
          <i className={`bi ${icon}`} aria-hidden="true" />
        </div>
      </div>

      {trend && (
        <div className="edu-stat-footer mt-3 pt-2 d-flex align-items-center justify-content-between">
          <span
            className={`edu-stat-trend ${
              trend.positive === true
                ? 'trend-up'
                : trend.positive === false
                ? 'trend-down'
                : 'trend-neutral'
            }`}
          >
            {trend.positive === true && <i className="bi bi-arrow-up-right me-1" />}
            {trend.positive === false && <i className="bi bi-arrow-down-right me-1" />}
            {trend.positive === null && <i className="bi bi-dash me-1" />}
            {trend.text}
          </span>
          {onClick && (
            <span className="edu-stat-view-link">
              View <i className="bi bi-chevron-right ms-0.5" />
            </span>
          )}
        </div>
      )}
    </div>
  );
};
