import React, { useState, useMemo } from 'react';

/* ── StatCard ── */
export const StatCard: React.FC<{
  icon: string;
  label: string;
  value: string | number;
  variant?: 'default' | 'mustard' | 'blue';
  accentTop?: boolean;
}> = ({ icon, label, value, variant = 'default', accentTop = false }) => (
  <div className={`edu-stat-card ${accentTop ? 'accent' : ''}`}>
    <div
      className={`edu-stat-icon ${
        variant === 'mustard' ? 'mustard' : variant === 'blue' ? 'blue' : ''
      }`}
    >
      <i className={`bi ${icon}`} aria-hidden="true" />
    </div>
    <div>
      <div className="edu-stat-value">{value}</div>
      <div className="edu-stat-label">{label}</div>
    </div>
  </div>
);

/* ── Card ── */
export const Card: React.FC<{
  title?: React.ReactNode;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  noPadding?: boolean;
}> = ({ title, subtitle, actions, children, className = '', noPadding = false }) => (
  <div className={`edu-card ${className}`}>
    {(title || actions) && (
      <div className="edu-card-header">
        <div>
          {title && <h3 className="edu-card-title">{title}</h3>}
          {subtitle && (
            <div className="text-muted mt-1" style={{ fontSize: 'var(--font-size-xs)' }}>
              {subtitle}
            </div>
          )}
        </div>
        {actions && <div className="d-flex align-items-center gap-2 flex-wrap">{actions}</div>}
      </div>
    )}
    <div className={noPadding ? '' : 'edu-card-body'}>{children}</div>
  </div>
);

/* ── Button ── */
export const Button: React.FC<
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: 'primary' | 'accent' | 'outline' | 'danger';
    size?: 'sm' | 'md';
    icon?: string;
  }
> = ({ variant = 'primary', size = 'md', icon, children, className = '', ...rest }) => {
  const variantClass =
    variant === 'accent'
      ? 'edu-btn-accent'
      : variant === 'outline'
      ? 'edu-btn-outline'
      : variant === 'danger'
      ? 'edu-btn-danger'
      : 'edu-btn-primary';
  return (
    <button
      className={`edu-btn ${variantClass} ${size === 'sm' ? 'edu-btn-sm' : ''} ${className}`}
      {...rest}
    >
      {icon && <i className={`bi ${icon}`} aria-hidden="true" />}
      {children}
    </button>
  );
};

/* ── FormField ── */
export const FormField: React.FC<{
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
  className?: string;
}> = ({ label, hint, required, children, className = 'mb-3' }) => (
  <div className={className}>
    <label className="edu-label">
      {label}
      {required && <span className="text-danger ms-1">*</span>}
    </label>
    {children}
    {hint && <div className="form-text small text-muted mt-1">{hint}</div>}
  </div>
);

/* ── PasswordInput with Visibility Toggle ── */
export const PasswordInput: React.FC<
  Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> & {
    error?: boolean;
  }
> = ({ className = '', error = false, ...rest }) => {
  const [visible, setVisible] = useState(false);

  return (
    <div className="edu-password-input-wrap position-relative">
      <input
        type={visible ? 'text' : 'password'}
        className={`edu-input pe-5 ${error ? 'is-invalid border-danger' : ''} ${className}`}
        {...rest}
      />
      <button
        type="button"
        className="edu-password-toggle-btn"
        onClick={() => setVisible((prev) => !prev)}
        title={visible ? 'Hide password' : 'Show password'}
        aria-label={visible ? 'Hide password' : 'Show password'}
        tabIndex={0}
      >
        <i
          className={`bi ${visible ? 'bi-eye-slash-fill' : 'bi-eye-fill'}`}
          aria-hidden="true"
        />
      </button>
    </div>
  );
};

/* ── Badge ── */
export const Badge: React.FC<{
  variant?: 'blue' | 'mustard' | 'success' | 'danger' | 'neutral';
  children: React.ReactNode;
}> = ({ variant = 'blue', children }) => (
  <span className={`edu-badge edu-badge-${variant}`}>{children}</span>
);

/* ── Modal ── */
export const Modal: React.FC<{
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  size?: 'md' | 'lg';
}> = ({ open, title, onClose, children, size = 'md' }) => {
  if (!open) return null;
  return (
    <div className="edu-modal-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <div className="edu-modal-dialog" style={size === 'lg' ? { maxWidth: 760 } : undefined}>
        <div className="edu-card-header">
          <h3 className="edu-card-title">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="btn-close"
            aria-label="Close dialog"
          />
        </div>
        <div className="edu-card-body">{children}</div>
      </div>
    </div>
  );
};

/* ── ConfirmDialog ── */
export const ConfirmDialog: React.FC<{
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  confirmVariant?: 'danger' | 'primary' | 'accent';
  onConfirm: () => void;
  onClose: () => void;
  loading?: boolean;
}> = ({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  confirmVariant = 'danger',
  onConfirm,
  onClose,
  loading = false,
}) => {
  if (!open) return null;
  return (
    <Modal open={open} title={title} onClose={onClose}>
      <p className="mb-4" style={{ fontSize: 'var(--font-size-base)', color: 'var(--color-text-muted)' }}>
        {message}
      </p>
      <div className="d-flex justify-content-end gap-2">
        <Button variant="outline" size="sm" onClick={onClose} disabled={loading}>
          Cancel
        </Button>
        <Button variant={confirmVariant} size="sm" onClick={onConfirm} disabled={loading}>
          {loading ? 'Processing...' : confirmLabel}
        </Button>
      </div>
    </Modal>
  );
};

/* ── DataTable with Search & Pagination ── */
export function DataTable<T extends Record<string, any> = any>({
  columns,
  rows,
  searchPlaceholder = 'Search records...',
  searchKeys = [],
  emptyTitle = 'No records found',
  emptyDescription = 'Add a new record or adjust your search filter.',
  pageSize = 8,
}: {
  columns: Array<{
    header: string;
    render: (row: T) => React.ReactNode;
  }>;
  rows: T[];
  searchPlaceholder?: string;
  searchKeys?: string[];
  emptyTitle?: string;
  emptyDescription?: string;
  pageSize?: number;
}) {
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || searchKeys.length === 0) return rows;
    return rows.filter((r) =>
      searchKeys.some((k) => String(r[k] ?? '').toLowerCase().includes(q))
    );
  }, [rows, query, searchKeys]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const slice = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  return (
    <div>
      {searchKeys.length > 0 && (
        <div className="d-flex justify-content-between align-items-center gap-3 mb-3 flex-wrap">
          <div style={{ maxWidth: 340, width: '100%' }} className="position-relative">
            <input
              type="search"
              className="edu-input ps-4"
              placeholder={searchPlaceholder}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <span className="small text-muted fw-semibold">
            Showing {slice.length} of {filtered.length} record{filtered.length === 1 ? '' : 's'}
          </span>
        </div>
      )}

      {filtered.length === 0 ? (
        <EmptyState title={emptyTitle} description={emptyDescription} />
      ) : (
        <>
          <div className="edu-table-wrap">
            <table className="edu-table">
              <thead>
                <tr>
                  {columns.map((c, idx) => (
                    <th key={idx}>{c.header}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {slice.map((row, rIdx) => (
                  <tr key={row.id ?? rIdx}>
                    {columns.map((c, cIdx) => (
                      <td key={cIdx}>{c.render(row)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="d-flex justify-content-between align-items-center mt-3 flex-wrap gap-2">
              <span className="small text-muted">
                Page {safePage} of {totalPages}
              </span>
              <div className="d-flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={safePage <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Previous
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={safePage >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ── LoadingState, EmptyState, ErrorAlert ── */
export const LoadingState: React.FC<{ message?: string }> = ({
  message = 'Loading school data...',
}) => (
  <div className="text-center py-5">
    <div
      className="spinner-border mb-3"
      style={{ color: 'var(--color-strong-blue)', width: '2.4rem', height: '2.4rem' }}
      role="status"
    />
    <div className="fw-semibold" style={{ color: 'var(--color-strong-blue)' }}>
      {message}
    </div>
  </div>
);

export const EmptyState: React.FC<{
  icon?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}> = ({ icon = 'bi-inbox', title, description, action }) => (
  <div
    className="text-center py-5 px-3 rounded-3"
    style={{
      background: 'rgba(229, 232, 239, 0.45)',
      border: '1px dashed var(--color-border)',
    }}
  >
    <div
      className="mx-auto mb-3 d-inline-flex align-items-center justify-content-center rounded-circle"
      style={{
        width: 56,
        height: 56,
        background: 'var(--color-cool-gray)',
        color: 'var(--color-strong-blue)',
        fontSize: '1.5rem',
      }}
    >
      <i className={`bi ${icon}`} aria-hidden="true" />
    </div>
    <h5 className="fw-bold mb-1" style={{ color: 'var(--color-strong-blue)' }}>
      {title}
    </h5>
    {description && <p className="small text-muted mb-3">{description}</p>}
    {action}
  </div>
);

export const AlertBanner: React.FC<{
  variant?: 'success' | 'danger' | 'warning' | 'info';
  message: string | null;
  onDismiss?: () => void;
}> = ({ variant = 'info', message, onDismiss }) => {
  if (!message) return null;
  const styles: Record<string, React.CSSProperties> = {
    success: {
      background: '#DCFCE7',
      border: '1px solid #86EFAC',
      color: '#166534',
    },
    danger: {
      background: '#FEE2E2',
      border: '1px solid #FCA5A5',
      color: '#991B1B',
    },
    warning: {
      background: 'rgba(255, 184, 0, 0.18)',
      border: '1px solid var(--color-mustard)',
      color: 'var(--color-strong-blue)',
    },
    info: {
      background: 'var(--color-cool-gray)',
      border: '1px solid var(--color-strong-blue)',
      color: 'var(--color-strong-blue)',
    },
  };
  return (
    <div
      className="d-flex align-items-center justify-content-between px-3 py-2 rounded-3 mb-3 fw-semibold small"
      style={styles[variant]}
      role="alert"
    >
      <span>{message}</span>
      {onDismiss && (
        <button
          type="button"
          className="btn-close ms-3"
          style={{ fontSize: '0.7rem' }}
          onClick={onDismiss}
          aria-label="Dismiss"
        />
      )}
    </div>
  );
};
