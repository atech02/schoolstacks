import React from 'react';

/* ─────────────────────────────────────────────────────────────────────────────
   1. QUICK ACTION GRID
   ───────────────────────────────────────────────────────────────────────────── */
export interface QuickActionItem {
  icon: string;
  label: string;
  description?: string;
  color?: string; // e.g. '#002583'
  badge?: string;
  onClick: () => void;
}

export const QuickActionGrid: React.FC<{
  actions: QuickActionItem[];
  columns?: 2 | 3 | 4;
}> = ({ actions, columns = 4 }) => {
  const colClass =
    columns === 2
      ? 'col-sm-6'
      : columns === 3
      ? 'col-sm-6 col-md-4'
      : 'col-6 col-md-3';

  return (
    <div className="row g-2.5 g-md-3">
      {actions.map((act, idx) => (
        <div key={idx} className={colClass}>
          <button
            type="button"
            className="edu-quick-action-btn w-100 text-start p-3 rounded-3 d-flex align-items-center gap-3"
            onClick={act.onClick}
          >
            <div
              className="edu-quick-action-icon rounded-3 d-flex align-items-center justify-content-center flex-shrink-0"
              style={{
                width: 42,
                height: 42,
                backgroundColor: act.color ? `${act.color}15` : 'rgba(0, 37, 131, 0.08)',
                color: act.color || '#002583',
              }}
            >
              <i className={`bi ${act.icon} fs-5`} />
            </div>
            <div className="flex-grow-1 text-truncate">
              <div className="fw-semibold text-dark text-truncate small mb-0.5">
                {act.label}
              </div>
              {act.description && (
                <div className="text-muted text-truncate" style={{ fontSize: '11px' }}>
                  {act.description}
                </div>
              )}
            </div>
            {act.badge && (
              <span className="badge rounded-pill bg-danger-subtle text-danger border border-danger-subtle px-1.5 py-0.5" style={{ fontSize: '10px' }}>
                {act.badge}
              </span>
            )}
          </button>
        </div>
      ))}
    </div>
  );
};

/* ─────────────────────────────────────────────────────────────────────────────
   2. RECENT ACTIVITY TIMELINE
   ───────────────────────────────────────────────────────────────────────────── */
export interface ActivityItem {
  id: string | number;
  title: string;
  description?: string;
  time: string;
  icon?: string;
  category?: string;
  role?: string;
  badge?: {
    text: string;
    variant: 'success' | 'warning' | 'danger' | 'info' | 'primary';
  };
}

export const ActivityTimeline: React.FC<{
  activities: ActivityItem[];
  emptyMessage?: string;
  maxItems?: number;
}> = ({ activities, emptyMessage = 'No recent activities recorded.', maxItems = 6 }) => {
  const items = activities.slice(0, maxItems);

  if (items.length === 0) {
    return <div className="text-muted small text-center py-4">{emptyMessage}</div>;
  }

  return (
    <div className="edu-timeline">
      {items.map((act, idx) => (
        <div key={act.id ?? idx} className="edu-timeline-item d-flex gap-3 pb-3 position-relative">
          <div className="edu-timeline-marker flex-shrink-0 position-relative">
            <div
              className="rounded-circle d-flex align-items-center justify-content-center"
              style={{
                width: 32,
                height: 32,
                backgroundColor: 'rgba(0, 37, 131, 0.08)',
                color: '#002583',
                border: '2px solid #FFFFFF',
                boxShadow: '0 2px 6px rgba(0,0,0,0.06)',
              }}
            >
              <i className={`bi ${act.icon || 'bi-dot'} fs-6`} />
            </div>
            {idx < items.length - 1 && (
              <div
                className="position-absolute start-50 top-100 bottom-0 border-start border-2"
                style={{ borderColor: '#E2E8F0', transform: 'translateX(-50%)', height: '100%' }}
              />
            )}
          </div>

          <div className="edu-timeline-content flex-grow-1">
            <div className="d-flex align-items-center justify-content-between gap-2 flex-wrap">
              <span className="fw-semibold text-dark small">{act.title}</span>
              <span className="text-muted" style={{ fontSize: '11px' }}>
                {act.time}
              </span>
            </div>
            {act.description && (
              <p className="text-muted small mb-1 mt-0.5">{act.description}</p>
            )}
            <div className="d-flex align-items-center gap-2 mt-1">
              {act.role && (
                <span className="badge bg-light text-secondary border px-1.5 py-0.5" style={{ fontSize: '10px' }}>
                  {act.role}
                </span>
              )}
              {act.category && (
                <span className="badge bg-primary-subtle text-primary border border-primary-subtle px-1.5 py-0.5" style={{ fontSize: '10px' }}>
                  {act.category}
                </span>
              )}
              {act.badge && (
                <span className={`badge bg-${act.badge.variant}-subtle text-${act.badge.variant} border border-${act.badge.variant}-subtle px-1.5 py-0.5`} style={{ fontSize: '10px' }}>
                  {act.badge.text}
                </span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};
