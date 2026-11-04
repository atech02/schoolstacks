import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { apiFetch } from '../services/api';
import { Badge, Button, Modal } from '../components/ui';
import { BrandLogo } from '../components/BrandLogo';

export interface NavItem {
  id: string;
  label: string;
  icon: string;
  section?: string;
}

export const AppLayout: React.FC<{
  title: string;
  subtitle?: string;
  navItems: NavItem[];
  activeTab: string;
  onSelectTab: (id: string) => void;
  actions?: React.ReactNode;
  children: React.ReactNode;
}> = ({ title, subtitle, navItems, activeTab, onSelectTab, actions, children }) => {
  const { user, school, unreadNotifications, logout, refreshBootstrap } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifications, setNotifications] = useState<
    Array<{ id: number; message: string; type: string; is_read: boolean; created_at: string }>
  >([]);

  const openNotifications = async () => {
    setNotifOpen(true);
    try {
      const res = await apiFetch<{ notifications: any[] }>('/api/notifications');
      setNotifications(res.notifications || []);
    } catch {
      setNotifications([]);
    }
  };

  const markRead = async (id: number) => {
    await apiFetch(`/api/notifications/${id}/read`, { method: 'POST' });
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
    await refreshBootstrap();
  };

  useEffect(() => {
    setSidebarOpen(false);
  }, [activeTab]);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="edu-app-shell">
      <div
        className={`edu-sidebar-backdrop ${sidebarOpen ? 'show' : ''}`}
        onClick={() => setSidebarOpen(false)}
      />

      {/* Strong Blue (#002583) Sidebar */}
      <aside className={`edu-sidebar ${sidebarOpen ? 'open' : ''}`} aria-label="Sidebar Navigation">
        <div className="edu-sidebar-brand">
          <BrandLogo showSlogan={true} theme="light" size="sm" />
          <button
            type="button"
            className="btn btn-sm d-lg-none text-white"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close navigation menu"
          >
            <i className="bi bi-x-lg" />
          </button>
        </div>

        {school && (
          <div className="edu-sidebar-school">
            <div className="fw-semibold text-white text-truncate" style={{ fontSize: 'var(--font-size-sm)' }}>
              {school.name}
            </div>
            <div className="d-flex align-items-center justify-content-between mt-1">
              <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-cool-gray)' }}>
                /s/{school.subdomain}
              </span>
              <span
                className="px-2 py-0 rounded-pill fw-bold text-uppercase"
                style={{
                  fontSize: '11px',
                  background: 'var(--color-mustard)',
                  color: 'var(--color-strong-blue)',
                }}
              >
                {school.plan}
              </span>
            </div>
          </div>
        )}

        <nav className="edu-sidebar-nav">
          <div className="edu-nav-section-label">
            {user?.role ? `${user.role.toUpperCase()} PORTAL` : 'NAVIGATION'}
          </div>
          {navItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`edu-nav-item ${activeTab === item.id ? 'active' : ''}`}
              onClick={() => onSelectTab(item.id)}
            >
              <i className={`bi ${item.icon}`} aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          ))}

          {user?.role === 'admin' && (
            <>
              <div className="edu-nav-section-label mt-2">SUBSCRIPTION &amp; BILLING</div>
              <button
                type="button"
                className="edu-nav-item"
                onClick={() => navigate('/billing/plans')}
              >
                <i className="bi bi-credit-card-2-front" aria-hidden="true" />
                <span>Subscription &amp; Billing</span>
              </button>
            </>
          )}
        </nav>

        <div className="edu-sidebar-footer">
          <button
            type="button"
            className="edu-nav-item"
            onClick={() => navigate('/change-password')}
          >
            <i className="bi bi-shield-lock" aria-hidden="true" />
            <span>Change Password</span>
          </button>
          <button type="button" className="edu-nav-item" onClick={handleLogout}>
            <i className="bi bi-box-arrow-right" aria-hidden="true" />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="edu-main-wrapper">
        <header className="edu-topbar">
          <div className="d-flex align-items-center gap-3">
            <button
              type="button"
              className="edu-btn edu-btn-outline edu-btn-sm d-lg-none"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open navigation menu"
            >
              <i className="bi bi-list fs-5" />
            </button>
            <div>
              <div className="text-muted d-none d-sm-block" style={{ fontSize: 'var(--font-size-xs)' }}>
                {school ? school.name : 'Platform Administration'} &bull;{' '}
                <span className="text-capitalize">{user?.role}</span>
              </div>
              <h1 className="fw-bold mb-0" style={{ color: 'var(--color-strong-blue)', fontSize: 'var(--font-size-2xl)' }}>
                {title}
              </h1>
            </div>
          </div>

          <div className="d-flex align-items-center gap-2 gap-sm-3">
            <button
              type="button"
              className="edu-btn edu-btn-outline edu-btn-sm position-relative"
              onClick={openNotifications}
              aria-label="Notifications"
            >
              <i className="bi bi-bell-fill" />
              {unreadNotifications > 0 && (
                <span
                  className="position-absolute top-0 start-100 translate-middle badge rounded-pill"
                  style={{
                    background: 'var(--color-mustard)',
                    color: 'var(--color-strong-blue)',
                    fontSize: '11px',
                  }}
                >
                  {unreadNotifications}
                </span>
              )}
            </button>

            <div
              className="d-flex align-items-center gap-2 px-3 py-1 rounded-pill"
              style={{
                background: 'var(--color-cool-gray)',
                border: '1px solid var(--color-border)',
              }}
            >
              <span
                className="rounded-circle d-inline-flex align-items-center justify-content-center fw-bold"
                style={{
                  width: 28,
                  height: 28,
                  background: 'var(--color-strong-blue)',
                  color: 'var(--color-mustard)',
                  fontSize: 'var(--font-size-xs)',
                }}
              >
                {user?.username?.slice(0, 2).toUpperCase() || 'U'}
              </span>
              <div className="d-none d-md-block text-start">
                <div
                  className="fw-semibold lh-1"
                  style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-strong-blue)' }}
                >
                  {user?.username}
                </div>
                <div className="text-muted text-capitalize mt-1" style={{ fontSize: 'var(--font-size-xs)' }}>
                  {user?.role}
                </div>
              </div>
            </div>
          </div>
        </header>

        <main className="edu-content">
          {(subtitle || actions) && (
            <div className="d-flex justify-content-between align-items-center flex-wrap gap-3 mb-4">
              {subtitle ? (
                <p className="text-muted mb-0">{subtitle}</p>
              ) : (
                <div />
              )}
              {actions && <div className="d-flex gap-2 flex-wrap">{actions}</div>}
            </div>
          )}
          {children}
        </main>
      </div>

      {/* Mobile Bottom Navigation */}
      <nav className="edu-mobile-bottom-nav" aria-label="Mobile Quick Navigation">
        {navItems.slice(0, 4).map((item) => (
          <button
            key={item.id}
            type="button"
            className={`edu-mobile-tab ${activeTab === item.id ? 'active' : ''}`}
            onClick={() => onSelectTab(item.id)}
          >
            <i className={`bi ${item.icon}`} />
            <span>{item.label.split(' ')[0]}</span>
          </button>
        ))}
        <button
          type="button"
          className="edu-mobile-tab"
          onClick={() => setSidebarOpen(true)}
        >
          <i className="bi bi-grid-fill" />
          <span>More</span>
        </button>
      </nav>

      {/* Notifications Modal */}
      <Modal
        open={notifOpen}
        title="Notifications & Alerts"
        onClose={() => setNotifOpen(false)}
      >
        {notifications.length === 0 ? (
          <div className="text-center py-4 text-muted small">
            You have no notifications yet.
          </div>
        ) : (
          <div className="d-flex flex-column gap-2">
            {notifications.map((n) => (
              <div
                key={n.id}
                className="p-3 rounded-3 d-flex justify-content-between align-items-start gap-2"
                style={{
                  background: n.is_read ? '#F8FAFC' : 'rgba(255, 184, 0, 0.14)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div>
                  <div className="fw-semibold small" style={{ color: 'var(--color-strong-blue)' }}>
                    {n.message}
                  </div>
                  <div className="text-muted" style={{ fontSize: 'var(--font-size-xs)' }}>
                    {n.created_at ? new Date(n.created_at).toLocaleString() : ''}
                  </div>
                </div>
                {!n.is_read ? (
                  <Button size="sm" variant="outline" onClick={() => markRead(n.id)}>
                    Mark Read
                  </Button>
                ) : (
                  <Badge variant="neutral">Read</Badge>
                )}
              </div>
            ))}
          </div>
        )}
      </Modal>
    </div>
  );
};
