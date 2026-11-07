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
  badge?: string | number;
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
  const [isCollapsed, setIsCollapsed] = useState(() => {
    try {
      return localStorage.getItem('schoolstacks_sidebar_collapsed') === 'true';
    } catch {
      return false;
    }
  });
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifications, setNotifications] = useState<
    Array<{ id: number; message: string; type: string; is_read: boolean; created_at: string }>
  >([]);

  const toggleSidebarCollapse = () => {
    setIsCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('schoolstacks_sidebar_collapsed', String(next));
      } catch {}
      return next;
    });
  };

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

  // Group navigation items by section if present
  const groupedNav = React.useMemo(() => {
    const hasSections = navItems.some((item) => item.section);
    if (!hasSections) {
      return [{ section: user?.role ? `${user.role.toUpperCase()} PORTAL` : 'NAVIGATION', items: navItems }];
    }
    const map = new Map<string, NavItem[]>();
    navItems.forEach((item) => {
      const sec = item.section || 'GENERAL';
      if (!map.has(sec)) map.set(sec, []);
      map.get(sec)!.push(item);
    });
    return Array.from(map.entries()).map(([section, items]) => ({ section, items }));
  }, [navItems, user?.role]);

  const formattedDate = new Date().toLocaleDateString('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });

  return (
    <div className={`edu-app-shell ${isCollapsed ? 'sidebar-collapsed' : ''}`}>
      <div
        className={`edu-sidebar-backdrop ${sidebarOpen ? 'show' : ''}`}
        onClick={() => setSidebarOpen(false)}
      />

      {/* Strong Blue (#002583) Sidebar */}
      <aside
        className={`edu-sidebar ${sidebarOpen ? 'open' : ''} ${isCollapsed ? 'collapsed' : ''}`}
        aria-label="Sidebar Navigation"
      >
        <div className="edu-sidebar-brand">
          <BrandLogo showSlogan={!isCollapsed} theme="light" size="sm" />
          <button
            type="button"
            className="btn btn-sm d-lg-none text-white p-1"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close navigation menu"
          >
            <i className="bi bi-x-lg" />
          </button>
        </div>

        {school && !isCollapsed && (
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
          {groupedNav.map((group, gIdx) => (
            <div key={gIdx} className="edu-sidebar-nav-group">
              <div className="edu-sidebar-nav-group-header">
                {group.section}
              </div>
              {group.items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`edu-nav-item ${activeTab === item.id ? 'active' : ''}`}
                  onClick={() => onSelectTab(item.id)}
                  title={isCollapsed ? item.label : undefined}
                >
                  <i className={`bi ${item.icon}`} aria-hidden="true" />
                  <span>{item.label}</span>
                  {item.badge !== undefined && !isCollapsed && (
                    <span className="edu-nav-badge">{item.badge}</span>
                  )}
                </button>
              ))}
            </div>
          ))}

          {user?.role === 'admin' && (
            <div className="edu-sidebar-nav-group mt-2">
              <div className="edu-sidebar-nav-group-header">SUBSCRIPTION &amp; BILLING</div>
              <button
                type="button"
                className="edu-nav-item"
                onClick={() => navigate('/billing/plans')}
                title={isCollapsed ? 'Subscription & Billing' : undefined}
              >
                <i className="bi bi-credit-card-2-front" aria-hidden="true" />
                <span>Subscription &amp; Billing</span>
              </button>
            </div>
          )}
        </nav>

        <div className="edu-sidebar-footer">
          <button
            type="button"
            className="edu-nav-item"
            onClick={() => navigate('/change-password')}
            title={isCollapsed ? 'Change Password' : undefined}
          >
            <i className="bi bi-shield-lock" aria-hidden="true" />
            <span>Change Password</span>
          </button>
          <button
            type="button"
            className="edu-nav-item"
            onClick={handleLogout}
            title={isCollapsed ? 'Sign Out' : undefined}
          >
            <i className="bi bi-box-arrow-right" aria-hidden="true" />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="edu-main-wrapper">
        <header className="edu-topbar">
          <div className="d-flex align-items-center gap-2 gap-sm-3">
            {/* Mobile menu button */}
            <button
              type="button"
              className="edu-btn edu-btn-outline edu-btn-sm d-lg-none"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open navigation menu"
            >
              <i className="bi bi-list fs-5" />
            </button>

            {/* Desktop collapse toggle */}
            <button
              type="button"
              className="edu-btn edu-btn-outline edu-btn-sm d-none d-lg-inline-flex"
              onClick={toggleSidebarCollapse}
              title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              <i className={`bi ${isCollapsed ? 'bi-layout-sidebar-inset' : 'bi-layout-sidebar'}`} />
            </button>

            <div>
              <div className="text-muted d-none d-sm-flex align-items-center gap-2" style={{ fontSize: 'var(--font-size-xs)' }}>
                <span>{school ? school.name : 'Platform Administration'}</span>
                <span>&bull;</span>
                <span className="badge bg-light text-primary border text-capitalize px-1.5 py-0.5">
                  {user?.role}
                </span>
                <span className="d-none d-md-inline">&bull;</span>
                <span className="d-none d-md-inline text-secondary">
                  <i className="bi bi-calendar-event me-1" />
                  {formattedDate}
                </span>
              </div>
              <h1 className="fw-bold mb-0" style={{ color: 'var(--color-strong-blue)', fontSize: '1.35rem' }}>
                {title}
              </h1>
            </div>
          </div>

          <div className="d-flex align-items-center gap-2 gap-sm-3">
            <button
              type="button"
              className="edu-btn edu-btn-outline edu-btn-sm position-relative shadow-none"
              onClick={openNotifications}
              aria-label="Notifications"
            >
              <i className="bi bi-bell-fill text-secondary" />
              {unreadNotifications > 0 && (
                <span
                  className="position-absolute top-0 start-100 translate-middle badge rounded-pill"
                  style={{
                    background: 'var(--color-mustard)',
                    color: 'var(--color-strong-blue)',
                    fontSize: '11px',
                    fontWeight: 700,
                  }}
                >
                  {unreadNotifications}
                </span>
              )}
            </button>

            <div
              className="d-flex align-items-center gap-2 px-2.5 py-1 rounded-pill"
              style={{
                background: '#FFFFFF',
                border: '1px solid var(--color-border)',
                boxShadow: '0 2px 6px rgba(0,0,0,0.03)',
              }}
            >
              <span
                className="rounded-circle d-inline-flex align-items-center justify-content-center fw-bold"
                style={{
                  width: 32,
                  height: 32,
                  background: 'var(--color-strong-blue)',
                  color: 'var(--color-mustard)',
                  fontSize: 'var(--font-size-xs)',
                  border: '1.5px solid rgba(255, 184, 0, 0.4)',
                }}
              >
                {user?.username?.slice(0, 2).toUpperCase() || 'U'}
              </span>
              <div className="d-none d-md-block text-start pe-1">
                <div
                  className="fw-semibold lh-1"
                  style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-strong-blue)' }}
                >
                  {user?.username}
                </div>
                <div className="text-muted text-capitalize mt-1" style={{ fontSize: '11px' }}>
                  {user?.role}
                </div>
              </div>
            </div>
          </div>
        </header>

        <main className="edu-content">
          {user?.must_change_password && (
            <div
              className="alert alert-warning d-flex align-items-center justify-content-between flex-wrap gap-2 mb-4 p-3 rounded-3"
              role="alert"
              style={{
                border: '1.5px solid var(--color-mustard)',
                background: 'rgba(255, 184, 0, 0.12)',
              }}
            >
              <div className="d-flex align-items-center gap-2">
                <i className="bi bi-shield-exclamation text-warning fs-5" aria-hidden="true" />
                <span className="small text-dark">
                  <strong>Security Notice:</strong> You are currently using a temporary bootstrap password. Please update your password to secure this account.
                </span>
              </div>
              <button
                type="button"
                className="edu-btn edu-btn-accent edu-btn-sm"
                onClick={() => navigate('/change-password')}
              >
                Change Password Now
              </button>
            </div>
          )}
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
