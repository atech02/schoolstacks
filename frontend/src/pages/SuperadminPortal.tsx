import React, { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AppLayout, NavItem } from '../layouts/AppLayout';
import { apiFetch } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import {
  AlertBanner,
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  FormField,
  LoadingState,
  Modal,
  StatCard,
} from '../components/ui';
import {
  DashboardHeader,
  StatisticCard as ModernStatCard,
  DonutChart,
  QuickActionGrid,
} from '../components/dashboard';

const NAV_ITEMS: NavItem[] = [
  { id: 'overview', label: 'Platform Command Centre', icon: 'bi-speedometer2', section: 'EXECUTIVE OVERVIEW' },
  { id: 'schools', label: 'Tenant Schools', icon: 'bi-buildings', section: 'MANAGEMENT' },
  { id: 'subscriptions', label: 'SaaS Subscriptions', icon: 'bi-credit-card-2-front', section: 'BILLING & PLANS' },
  { id: 'activity', label: 'Audit & Activity Monitor', icon: 'bi-activity', section: 'SYSTEM AUDIT' },
];

const ACTIVITY_CATEGORIES = [
  { value: 'all', label: 'All Categories' },
  { value: 'auth', label: 'Authentication & Logins' },
  { value: 'school_status', label: 'School Activation / Suspension' },
  { value: 'subscription', label: 'SaaS Subscriptions' },
  { value: 'payment', label: 'School Fee Payments' },
  { value: 'student', label: 'Student Enrolment' },
  { value: 'staff', label: 'Staff & Admin Accounts' },
  { value: 'academic', label: 'Classes, Terms & Assignments' },
  { value: 'attendance', label: 'Attendance Recording' },
  { value: 'exam', label: 'Exams & Results' },
  { value: 'announcement', label: 'Announcements' },
  { value: 'onboarding', label: 'School Onboarding' },
];

const ACTOR_ROLES = [
  { value: 'all', label: 'All Roles' },
  { value: 'superadmin', label: 'Superadmin' },
  { value: 'admin', label: 'School Admin' },
  { value: 'teacher', label: 'Teacher' },
  { value: 'parent', label: 'Parent' },
  { value: 'student', label: 'Student' },
  { value: 'system', label: 'System' },
];

const EVENT_STATUSES = [
  { value: 'all', label: 'All Statuses' },
  { value: 'success', label: 'Success / Confirmed' },
  { value: 'pending', label: 'Pending' },
  { value: 'warning', label: 'Warning / Suspended' },
  { value: 'failed', label: 'Failed / Blocked' },
  { value: 'info', label: 'Info' },
];

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return dt.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function formatDateOnly(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return dt.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
    });
  } catch {
    return iso;
  }
}

function statusBadgeVariant(status: string): 'success' | 'mustard' | 'danger' | 'blue' | 'neutral' {
  const s = (status || '').toLowerCase();
  if (s === 'success' || s === 'active' || s === 'completed' || s === 'active paid') return 'success';
  if (s === 'pending' || s === 'on trial' || s === 'warning') return 'mustard';
  if (s === 'failed' || s === 'suspended' || s === 'expired / overdue' || s === 'past_due') return 'danger';
  if (s === 'info') return 'blue';
  return 'neutral';
}

function categoryIcon(category: string): string {
  switch ((category || '').toLowerCase()) {
    case 'auth':
      return 'bi-shield-lock-fill';
    case 'school_status':
      return 'bi-building-Exclamation';
    case 'subscription':
      return 'bi-stars';
    case 'payment':
      return 'bi-cash-coin';
    case 'student':
      return 'bi-mortarboard-fill';
    case 'staff':
      return 'bi-person-badge-fill';
    case 'attendance':
      return 'bi-calendar2-check-fill';
    case 'exam':
      return 'bi-journal-check';
    case 'announcement':
      return 'bi-megaphone-fill';
    case 'onboarding':
      return 'bi-rocket-takeoff-fill';
    default:
      return 'bi-layers-fill';
  }
}

export const SuperadminPortal: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();

  // Parse current route under /superadmin/*
  const pathParts = location.pathname.replace(/^\/superadmin\/?/, '').split('/').filter(Boolean);
  const schoolDetailId =
    pathParts[0] === 'schools' && pathParts[1] && /^\d+$/.test(pathParts[1])
      ? Number(pathParts[1])
      : null;

  const activeNavTab = schoolDetailId
    ? 'schools'
    : pathParts[0] === 'schools'
    ? 'schools'
    : pathParts[0] === 'activity'
    ? 'activity'
    : pathParts[0] === 'subscriptions'
    ? 'subscriptions'
    : 'overview';

  const handleSelectTab = (tabId: string) => {
    if (tabId === 'overview') navigate('/superadmin');
    else navigate(`/superadmin/${tabId}`);
  };

  // Overview state
  const [overviewData, setOverviewData] = useState<any>(null);
  const [loadingOverview, setLoadingOverview] = useState<boolean>(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // School directory filter state
  const [schoolPlanFilter, setSchoolPlanFilter] = useState<string>('all');
  const [schoolStatusFilter, setSchoolStatusFilter] = useState<string>('all');

  // Dedicated School Detail state
  const [schoolDetail, setSchoolDetail] = useState<any>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [detailSectionTab, setDetailSectionTab] = useState<'profile' | 'usage' | 'billing' | 'timeline'>('profile');
  const [detailTimelineFilter, setDetailTimelineFilter] = useState({
    category: 'all',
    role: 'all',
    status: 'all',
    date_from: '',
    date_to: '',
    q: '',
    page: 1,
  });

  // Platform-wide Activity Monitor state
  const [activityData, setActivityData] = useState<any>(null);
  const [loadingActivity, setLoadingActivity] = useState<boolean>(false);
  const [activityFilter, setActivityFilter] = useState({
    school_id: '',
    category: 'all',
    role: 'all',
    status: 'all',
    date_from: '',
    date_to: '',
    q: '',
    page: 1,
  });

  // Confirmation Modals for Sensitive Superadmin Actions
  const [statusModalSchool, setStatusModalSchool] = useState<any | null>(null);
  const [statusReason, setStatusReason] = useState<string>('');
  const [submittingAction, setSubmittingAction] = useState<boolean>(false);

  const [planModalSchool, setPlanModalSchool] = useState<any | null>(null);
  const [selectedPlan, setSelectedPlan] = useState<string>('free');
  const [planReason, setPlanReason] = useState<string>('');

  const loadOverview = useCallback(async () => {
    setLoadingOverview(true);
    try {
      const res = await apiFetch('/api/superadmin/overview');
      setOverviewData(res);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoadingOverview(false);
    }
  }, []);

  const loadSchoolDetail = useCallback(
    async (sid: number, filters = detailTimelineFilter) => {
      setLoadingDetail(true);
      try {
        const params = new URLSearchParams();
        if (filters.category && filters.category !== 'all') params.set('category', filters.category);
        if (filters.role && filters.role !== 'all') params.set('role', filters.role);
        if (filters.status && filters.status !== 'all') params.set('status', filters.status);
        if (filters.date_from) params.set('date_from', filters.date_from);
        if (filters.date_to) params.set('date_to', filters.date_to);
        if (filters.q.trim()) params.set('q', filters.q.trim());
        params.set('page', String(filters.page || 1));
        params.set('per_page', '15');

        const res = await apiFetch(`/api/superadmin/schools/${sid}?${params.toString()}`);
        setSchoolDetail(res);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoadingDetail(false);
      }
    },
    [detailTimelineFilter]
  );

  const loadPlatformActivity = useCallback(
    async (filters = activityFilter) => {
      setLoadingActivity(true);
      try {
        const params = new URLSearchParams();
        if (filters.school_id) params.set('school_id', filters.school_id);
        if (filters.category && filters.category !== 'all') params.set('category', filters.category);
        if (filters.role && filters.role !== 'all') params.set('role', filters.role);
        if (filters.status && filters.status !== 'all') params.set('status', filters.status);
        if (filters.date_from) params.set('date_from', filters.date_from);
        if (filters.date_to) params.set('date_to', filters.date_to);
        if (filters.q.trim()) params.set('q', filters.q.trim());
        params.set('page', String(filters.page || 1));
        params.set('per_page', '20');

        const res = await apiFetch(`/api/superadmin/activity?${params.toString()}`);
        setActivityData(res);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoadingActivity(false);
      }
    },
    [activityFilter]
  );

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    if (schoolDetailId) {
      loadSchoolDetail(schoolDetailId, detailTimelineFilter);
    }
  }, [schoolDetailId, detailTimelineFilter, loadSchoolDetail]);

  useEffect(() => {
    if (activeNavTab === 'activity') {
      loadPlatformActivity(activityFilter);
    }
  }, [activeNavTab, activityFilter, loadPlatformActivity]);

  const handleConfirmStatusChange = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!statusModalSchool) return;
    if (!statusReason.trim()) {
      setError('Please provide an audit reason for this school status change.');
      return;
    }
    setSubmittingAction(true);
    setError(null);
    try {
      const action = statusModalSchool.is_active ? 'suspend' : 'activate';
      const res = await apiFetch(`/api/superadmin/schools/${statusModalSchool.id}/status`, {
        method: 'POST',
        body: JSON.stringify({ action, reason: statusReason.trim() }),
      });
      setMessage(res.message);
      setStatusModalSchool(null);
      setStatusReason('');
      await loadOverview();
      if (schoolDetailId === statusModalSchool.id) {
        await loadSchoolDetail(statusModalSchool.id);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmittingAction(false);
    }
  };

  const handleConfirmPlanChange = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!planModalSchool) return;
    if (!planReason.trim()) {
      setError('Please enter an audit reason for this subscription plan action.');
      return;
    }
    setSubmittingAction(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/superadmin/schools/${planModalSchool.id}/plan`, {
        method: 'POST',
        body: JSON.stringify({ plan: selectedPlan, reason: planReason.trim() }),
      });
      setMessage(res.message);
      setPlanModalSchool(null);
      setPlanReason('');
      await loadOverview();
      if (schoolDetailId === planModalSchool.id) {
        await loadSchoolDetail(planModalSchool.id);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmittingAction(false);
    }
  };

  if (loadingOverview && !overviewData) {
    return <LoadingState message="Loading Platform Superadmin Console..." />;
  }

  const metrics = overviewData?.metrics || {};
  const schools: any[] = overviewData?.schools || [];
  const recentSubscriptions: any[] = overviewData?.recent_subscriptions || [];
  const recentActivity: any[] = overviewData?.recent_activity || [];

  const filteredSchools = schools.filter((s) => {
    if (schoolPlanFilter !== 'all' && s.plan !== schoolPlanFilter) return false;
    if (schoolStatusFilter === 'active' && !s.is_active) return false;
    if (schoolStatusFilter === 'suspended' && s.is_active) return false;
    if (schoolStatusFilter === 'trial' && !s.on_trial) return false;
    if (schoolStatusFilter === 'expired' && !s.is_expired_or_overdue) return false;
    return true;
  });

  /* ── Render Reusable Activity Timeline List ── */
  const renderActivityTimeline = (items: any[], showSchoolLink = true) => {
    if (!items || items.length === 0) {
      return (
        <EmptyState
          icon="bi-clock-history"
          title="No Matching Activity Recorded"
          description="No recorded database or audit events match your current filters. New logins, academic updates, and subscription events will appear here automatically."
        />
      );
    }
    return (
      <div className="d-flex flex-column gap-3">
        {items.map((ev) => (
          <div
            key={ev.id}
            className="p-3 rounded-3 d-flex align-items-start justify-content-between gap-3 flex-wrap"
            style={{
              background: '#FFFFFF',
              border: '1px solid var(--color-border)',
              borderLeft: `4px solid ${
                ev.status === 'failed'
                  ? '#DC2626'
                  : ev.status === 'warning' || ev.status === 'pending'
                  ? 'var(--color-mustard)'
                  : 'var(--color-strong-blue)'
              }`,
            }}
          >
            <div className="d-flex align-items-start gap-3">
              <div
                className="d-flex align-items-center justify-content-center rounded-3 flex-shrink-0"
                style={{
                  width: 40,
                  height: 40,
                  background: 'var(--color-cool-gray)',
                  color: 'var(--color-strong-blue)',
                  fontSize: '1.1rem',
                }}
              >
                <i className={`bi ${categoryIcon(ev.category)}`} />
              </div>
              <div>
                <div className="d-flex align-items-center gap-2 flex-wrap mb-1">
                  {showSchoolLink && ev.school_id ? (
                    <button
                      type="button"
                      className="btn btn-link p-0 fw-bold text-decoration-none"
                      style={{ color: 'var(--color-strong-blue)', fontSize: 'var(--font-size-sm)' }}
                      onClick={() => {
                        setDetailSectionTab('profile');
                        navigate(`/superadmin/schools/${ev.school_id}`);
                      }}
                    >
                      {ev.school_name}
                    </button>
                  ) : (
                    <span className="fw-bold" style={{ color: 'var(--color-strong-blue)', fontSize: 'var(--font-size-sm)' }}>
                      {ev.school_name || 'Platform'}
                    </span>
                  )}
                  <Badge variant={statusBadgeVariant(ev.status)}>{ev.status}</Badge>
                  <Badge variant="neutral">{ev.category}</Badge>
                  <span className="small text-muted">
                    by <strong>{ev.actor_username || 'system'}</strong> ({ev.actor_role || 'system'})
                  </span>
                </div>
                <div style={{ color: 'var(--color-text)', fontSize: 'var(--font-size-sm)' }}>{ev.description}</div>
              </div>
            </div>
            <div className="text-end small text-muted flex-shrink-0">
              <div className="fw-semibold">{formatDateTime(ev.timestamp)}</div>
              <div style={{ fontSize: 'var(--font-size-xs)' }}>
                {ev.source === 'audit_log' ? 'Audit Trail' : 'Database Record'}
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  };

  /* ── Render Schools Table ── */
  const renderSchoolsDirectoryCard = (title = 'Registered Tenant Schools') => (
    <Card
      title={title}
      subtitle="Click any school name or 'Inspect School' to view its full profile, usage statistics, subscriptions, and activity timeline"
      actions={
        <div className="d-flex align-items-center gap-2 flex-wrap">
          <select
            className="edu-select py-1 px-2"
            style={{ width: 155, fontSize: 'var(--font-size-sm)' }}
            value={schoolStatusFilter}
            onChange={(e) => setSchoolStatusFilter(e.target.value)}
            aria-label="Filter schools by status"
          >
            <option value="all">All Statuses ({schools.length})</option>
            <option value="active">Active ({metrics.active_schools || 0})</option>
            <option value="suspended">Suspended ({metrics.suspended_schools || 0})</option>
            <option value="trial">On Trial ({metrics.trial_schools || 0})</option>
            <option value="expired">Expired / Overdue ({metrics.expired_or_overdue_schools || 0})</option>
          </select>
          <select
            className="edu-select py-1 px-2"
            style={{ width: 145, fontSize: 'var(--font-size-sm)' }}
            value={schoolPlanFilter}
            onChange={(e) => setSchoolPlanFilter(e.target.value)}
            aria-label="Filter schools by plan"
          >
            <option value="all">All Plans</option>
            <option value="free">Free Tier</option>
            <option value="starter">Starter</option>
            <option value="growth">Growth</option>
            <option value="enterprise">Enterprise</option>
          </select>
        </div>
      }
    >
      <DataTable
        rows={filteredSchools}
        searchKeys={['name', 'subdomain', 'email', 'plan', 'status_label']}
        searchPlaceholder="Search schools by name, subdomain slug, admin email, or plan..."
        columns={[
          {
            header: 'School & Identifier',
            render: (s) => (
              <div>
                <button
                  type="button"
                  className="btn btn-link p-0 fw-bold text-start text-decoration-none d-inline-flex align-items-center gap-1"
                  style={{ color: 'var(--color-strong-blue)', fontSize: 'var(--font-size-sm)' }}
                  onClick={() => {
                    setDetailSectionTab('profile');
                    navigate(`/superadmin/schools/${s.id}`);
                  }}
                >
                  <span>{s.name}</span>
                  <i className="bi bi-box-arrow-up-right small" />
                </button>
                <div className="small text-muted">
                  ID #{s.id} &bull; <code>/s/{s.subdomain}</code>
                </div>
              </div>
            ),
          },
          {
            header: 'Primary Administrator',
            render: (s) => (
              <div className="small">
                <div className="fw-semibold">
                  {s.primary_admin ? s.primary_admin.username : 'admin'}
                </div>
                <div className="text-muted">{s.email}</div>
                {s.phone && <div className="text-muted">{s.phone}</div>}
              </div>
            ),
          },
          {
            header: 'Usage (Students / Staff)',
            render: (s) => (
              <div className="small">
                <div>
                  <strong>{s.student_count}</strong> students &bull;{' '}
                  <strong>{s.teacher_count}</strong> teachers
                </div>
                <div className="text-muted">
                  {s.parent_count || 0} parents &bull; {s.admin_count || 1} admin(s)
                </div>
              </div>
            ),
          },
          {
            header: 'Plan & Billing Status',
            render: (s) => (
              <div>
                <div className="d-flex align-items-center gap-1 flex-wrap mb-1">
                  <Badge variant="blue">{(s.plan || 'free').toUpperCase()}</Badge>
                  <Badge variant={statusBadgeVariant(s.status_label)}>{s.status_label}</Badge>
                </div>
                <div className="small text-muted">
                  {s.subscription_ends_at
                    ? `Renews/Ends: ${formatDateOnly(s.subscription_ends_at)}`
                    : s.trial_ends_at
                    ? `Trial Ends: ${formatDateOnly(s.trial_ends_at)}`
                    : 'Free tier'}
                </div>
              </div>
            ),
          },
          {
            header: 'Last Recorded Activity',
            render: (s) => (
              <div className="small">
                <div className="fw-semibold">{formatDateTime(s.last_activity_at)}</div>
                <div className="text-muted">Created: {formatDateOnly(s.created_at)}</div>
              </div>
            ),
          },
          {
            header: 'Actions',
            render: (s) => (
              <div className="d-flex align-items-center gap-2 flex-wrap">
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => {
                    setDetailSectionTab('profile');
                    navigate(`/superadmin/schools/${s.id}`);
                  }}
                >
                  <i className="bi bi-eye" /> Inspect School
                </Button>
                <Button
                  size="sm"
                  variant={s.is_active ? 'danger' : 'accent'}
                  onClick={() => {
                    setStatusModalSchool(s);
                    setStatusReason('');
                  }}
                >
                  {s.is_active ? 'Suspend' : 'Reactivate'}
                </Button>
              </div>
            ),
          },
        ]}
      />
    </Card>
  );

  return (
    <AppLayout
      title={
        schoolDetailId && schoolDetail?.school
          ? `School Inspector: ${schoolDetail.school.name}`
          : 'Platform Superadmin Console'
      }
      subtitle="Multi-tenant SaaS monitoring, school activity inspection, subscription revenue, and audit controls"
      navItems={NAV_ITEMS}
      activeTab={activeNavTab}
      onSelectTab={handleSelectTab}
    >
      <AlertBanner variant="success" message={message} onDismiss={() => setMessage(null)} />
      <AlertBanner variant="danger" message={error} onDismiss={() => setError(null)} />

      {/* ══════════════════════════════════════════════════════════════════
          VIEW 1: DEDICATED SCHOOL DETAIL PAGE (/superadmin/schools/:schoolId)
          ══════════════════════════════════════════════════════════════════ */}
      {schoolDetailId ? (
        loadingDetail && !schoolDetail ? (
          <LoadingState message="Loading school profile, usage metrics, subscriptions, and activity timeline..." />
        ) : !schoolDetail?.school ? (
          <Card title="School Not Found">
            <EmptyState
              icon="bi-building-slash"
              title="School Record Unavailable"
              description="The requested school ID does not exist in the platform database."
              action={
                <Button variant="primary" onClick={() => navigate('/superadmin/schools')}>
                  Back to Schools Directory
                </Button>
              }
            />
          </Card>
        ) : (
          <div>
            {/* Breadcrumb & Top Action Bar */}
            <div className="d-flex justify-content-between align-items-center flex-wrap gap-3 mb-4">
              <div className="d-flex align-items-center gap-2 flex-wrap">
                <Button variant="outline" size="sm" onClick={() => navigate('/superadmin/schools')}>
                  <i className="bi bi-arrow-left" /> All Schools
                </Button>
                <Badge variant="blue">School ID #{schoolDetail.school.id}</Badge>
                <Badge variant={statusBadgeVariant(schoolDetail.school.status_label)}>
                  {schoolDetail.school.status_label}
                </Badge>
                <Badge variant="mustard">
                  Plan: {(schoolDetail.school.plan || 'free').toUpperCase()}
                </Badge>
              </div>

              <div className="d-flex align-items-center gap-2 flex-wrap">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setPlanModalSchool(schoolDetail.school);
                    setSelectedPlan(schoolDetail.school.plan || 'free');
                    setPlanReason('');
                  }}
                >
                  <i className="bi bi-sliders" /> Review / Sync Plan
                </Button>
                <Button
                  size="sm"
                  variant={schoolDetail.school.is_active ? 'danger' : 'accent'}
                  onClick={() => {
                    setStatusModalSchool(schoolDetail.school);
                    setStatusReason('');
                  }}
                >
                  <i className={`bi ${schoolDetail.school.is_active ? 'bi-pause-circle' : 'bi-play-circle'}`} />
                  {schoolDetail.school.is_active ? 'Suspend School' : 'Reactivate School'}
                </Button>
              </div>
            </div>

            {!schoolDetail.school.is_active && (
              <div
                className="p-3 rounded-3 mb-4 d-flex align-items-center justify-content-between flex-wrap gap-2"
                style={{
                  background: '#FEF2F2',
                  border: '1px solid #FECACA',
                  color: '#991B1B',
                }}
              >
                <div>
                  <strong>
                    <i className="bi bi-exclamation-octagon-fill me-2" />
                    This school is currently suspended.
                  </strong>{' '}
                  All school logins and tenant portal requests are blocked while existing school data remains safely preserved.
                  {schoolDetail.school.suspension_reason && (
                    <div className="small mt-1">
                      Recorded Suspension Reason: <em>{schoolDetail.school.suspension_reason}</em> (
                      {formatDateTime(schoolDetail.school.suspended_at)})
                    </div>
                  )}
                </div>
                <Button
                  size="sm"
                  variant="accent"
                  onClick={() => {
                    setStatusModalSchool(schoolDetail.school);
                    setStatusReason('');
                  }}
                >
                  Reactivate Now
                </Button>
              </div>
            )}

            {/* Top Summary Stat Cards for This School */}
            <div className="row g-3 mb-4">
              <div className="col-sm-6 col-xl-3">
                <StatCard
                  icon="bi-mortarboard-fill"
                  label="Enrolled Students"
                  value={`${schoolDetail.usage.students_count} / ${schoolDetail.usage.plan_limits?.students || '∞'}`}
                  variant="blue"
                />
              </div>
              <div className="col-sm-6 col-xl-3">
                <StatCard
                  icon="bi-person-workspace"
                  label="Teachers & Admins"
                  value={`${schoolDetail.usage.teachers_count} Teachers • ${schoolDetail.usage.admins_count} Admins`}
                  variant="mustard"
                  accentTop
                />
              </div>
              <div className="col-sm-6 col-xl-3">
                <StatCard
                  icon="bi-credit-card-2-front-fill"
                  label="SaaS Subscription Paid"
                  value={`K${Number(schoolDetail.billing.totals.paid_zmw || 0).toFixed(2)}`}
                  variant="mustard"
                  accentTop
                />
              </div>
              <div className="col-sm-6 col-xl-3">
                <StatCard
                  icon="bi-clock-history"
                  label="Last School Activity"
                  value={formatDateOnly(schoolDetail.school.last_activity_at)}
                />
              </div>
            </div>

            {/* Section Sub-Navigation Tabs (A. Profile, B. Usage, C. Subscriptions, D. Activity Timeline) */}
            <div className="d-flex gap-2 flex-wrap mb-4">
              {[
                { id: 'profile', label: 'A. School Profile & Admins', icon: 'bi-building' },
                { id: 'usage', label: 'B. Usage & Academic Activity', icon: 'bi-bar-chart-line' },
                { id: 'billing', label: 'C. Subscriptions & Payments', icon: 'bi-receipt' },
                {
                  id: 'timeline',
                  label: `D. Activity Timeline (${schoolDetail.activity?.total || 0})`,
                  icon: 'bi-activity',
                },
              ].map((t) => (
                <Button
                  key={t.id}
                  variant={detailSectionTab === t.id ? 'primary' : 'outline'}
                  size="sm"
                  onClick={() => setDetailSectionTab(t.id as any)}
                >
                  <i className={`bi ${t.icon}`} /> {t.label}
                </Button>
              ))}
            </div>

            {/* SECTION A: SCHOOL PROFILE & ADMINISTRATORS */}
            {detailSectionTab === 'profile' && (
              <div className="row g-4">
                <div className="col-lg-6">
                  <Card title="A. School Profile & Tenancy" subtitle="Verified tenant registration and subscription metadata">
                    <div className="row g-3 small">
                      <div className="col-sm-6">
                        <div className="text-muted">School Name</div>
                        <div className="fw-bold fs-6" style={{ color: 'var(--color-strong-blue)' }}>
                          {schoolDetail.school.name}
                        </div>
                      </div>
                      <div className="col-sm-6">
                        <div className="text-muted">Unique Identifier &amp; Slug</div>
                        <div className="fw-semibold">
                          ID #{schoolDetail.school.id} &bull; <code>/s/{schoolDetail.school.subdomain}</code>
                        </div>
                      </div>
                      <div className="col-sm-6">
                        <div className="text-muted">Official Email</div>
                        <div className="fw-semibold">{schoolDetail.school.email}</div>
                      </div>
                      <div className="col-sm-6">
                        <div className="text-muted">Contact Phone</div>
                        <div className="fw-semibold">{schoolDetail.school.phone || 'Not provided'}</div>
                      </div>
                      <div className="col-12">
                        <div className="text-muted">Physical Address</div>
                        <div className="fw-semibold">{schoolDetail.school.address || 'Not provided'}</div>
                      </div>
                      <div className="col-sm-6">
                        <div className="text-muted">Account Status</div>
                        <div>
                          <Badge variant={schoolDetail.school.is_active ? 'success' : 'danger'}>
                            {schoolDetail.school.is_active ? 'Active' : 'Suspended'}
                          </Badge>{' '}
                          <Badge variant={schoolDetail.school.is_email_verified ? 'blue' : 'neutral'}>
                            {schoolDetail.school.is_email_verified ? 'Email Verified' : 'Unverified'}
                          </Badge>
                        </div>
                      </div>
                      <div className="col-sm-6">
                        <div className="text-muted">Current Subscription Plan</div>
                        <div className="fw-bold" style={{ color: 'var(--color-strong-blue)' }}>
                          {(schoolDetail.school.plan || 'free').toUpperCase()} ({schoolDetail.school.billing_cycle || 'monthly'})
                        </div>
                      </div>
                      <div className="col-sm-6">
                        <div className="text-muted">Registration Date</div>
                        <div className="fw-semibold">{formatDateTime(schoolDetail.school.created_at)}</div>
                      </div>
                      <div className="col-sm-6">
                        <div className="text-muted">Last Recorded Activity</div>
                        <div className="fw-semibold">{formatDateTime(schoolDetail.school.last_activity_at)}</div>
                      </div>
                      <div className="col-sm-6">
                        <div className="text-muted">Trial Expiry Date</div>
                        <div className="fw-semibold">{formatDateTime(schoolDetail.school.trial_ends_at)}</div>
                      </div>
                      <div className="col-sm-6">
                        <div className="text-muted">Subscription Renewal / Expiry</div>
                        <div className="fw-semibold">{formatDateTime(schoolDetail.school.subscription_ends_at)}</div>
                      </div>
                    </div>
                  </Card>
                </div>

                <div className="col-lg-6">
                  <Card
                    title="School Administrators"
                    subtitle="Authorized school administrator accounts for this tenant"
                  >
                    <DataTable
                      rows={schoolDetail.administrators || []}
                      emptyTitle="No school administrators found"
                      columns={[
                        {
                          header: 'Username',
                          render: (a) => <strong style={{ color: 'var(--color-strong-blue)' }}>{a.username}</strong>,
                        },
                        {
                          header: 'Email',
                          render: (a) => <span>{a.email || '—'}</span>,
                        },
                        {
                          header: 'Verified',
                          render: (a) => (
                            <Badge variant={a.is_verified ? 'success' : 'mustard'}>
                              {a.is_verified ? 'Verified' : 'Pending'}
                            </Badge>
                          ),
                        },
                        {
                          header: 'Last Login',
                          render: (a) => <span className="small">{formatDateTime(a.last_login_at)}</span>,
                        },
                      ]}
                    />
                  </Card>
                </div>
              </div>
            )}

            {/* SECTION B: SCHOOL USAGE STATISTICS */}
            {detailSectionTab === 'usage' && (
              <div>
                <div className="row g-3 mb-4">
                  {[
                    { label: 'Students', val: schoolDetail.usage.students_count, icon: 'bi-mortarboard' },
                    { label: 'Teachers', val: schoolDetail.usage.teachers_count, icon: 'bi-person-badge' },
                    { label: 'Parents', val: schoolDetail.usage.parents_count, icon: 'bi-people' },
                    { label: 'School Admins', val: schoolDetail.usage.admins_count, icon: 'bi-shield-check' },
                    { label: 'Classes', val: schoolDetail.usage.classes_count, icon: 'bi-door-open' },
                    { label: 'Subjects', val: schoolDetail.usage.subjects_count, icon: 'bi-book' },
                    { label: 'Academic Terms', val: schoolDetail.usage.terms_count, icon: 'bi-calendar3' },
                    {
                      label: 'Attendance Records',
                      val: `${schoolDetail.usage.attendance_records_count} (${schoolDetail.usage.attendance_present_count} P / ${schoolDetail.usage.attendance_absent_count} A)`,
                      icon: 'bi-calendar2-check',
                    },
                    {
                      label: 'Exams & Results',
                      val: `${schoolDetail.usage.exams_count} Exams • ${schoolDetail.usage.results_count} Results`,
                      icon: 'bi-award',
                    },
                    {
                      label: 'Assignments & Submissions',
                      val: `${schoolDetail.usage.assignments_count} Tasks • ${schoolDetail.usage.submissions_count} Subs`,
                      icon: 'bi-journal-text',
                    },
                    {
                      label: 'Announcements & Alerts',
                      val: `${schoolDetail.usage.announcements_count} Posts • ${schoolDetail.usage.notifications_count} Notifs`,
                      icon: 'bi-megaphone',
                    },
                    {
                      label: 'School Fee Volume (Tenant Funds)',
                      val: `K${Number(schoolDetail.usage.tenant_fee_collections_zmw || 0).toFixed(2)} (${schoolDetail.usage.tenant_fee_payments_count} receipts)`,
                      icon: 'bi-wallet2',
                    },
                  ].map((item, idx) => (
                    <div className="col-sm-6 col-md-4 col-xl-3" key={idx}>
                      <div className="edu-stat-card h-100">
                        <div className="d-flex align-items-center justify-content-between mb-2">
                          <span className="small text-muted fw-semibold">{item.label}</span>
                          <i className={`bi ${item.icon}`} style={{ color: 'var(--color-strong-blue)' }} />
                        </div>
                        <div className="fw-bold fs-5" style={{ color: 'var(--color-strong-blue)' }}>
                          {item.val}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="row g-4">
                  <div className="col-lg-6">
                    <Card title="Classes & Enrolment Capacity" subtitle="Aggregated class utilization for this school">
                      <DataTable
                        rows={schoolDetail.usage.classes_summary || []}
                        emptyTitle="No classes created yet"
                        columns={[
                          { header: 'Class', render: (c) => <strong>{c.name}</strong> },
                          { header: 'Enrolled / Capacity', render: (c) => `${c.student_count} / ${c.capacity || '—'}` },
                          { header: 'Class Teacher', render: (c) => c.class_teacher },
                        ]}
                      />
                    </Card>
                  </div>
                  <div className="col-lg-6">
                    <Card title="Academic Terms & Exams" subtitle={`Active Term: ${schoolDetail.usage.active_term_name}`}>
                      <DataTable
                        rows={schoolDetail.usage.terms_summary || []}
                        emptyTitle="No academic terms created yet"
                        columns={[
                          { header: 'Term', render: (t) => <strong>{t.name}</strong> },
                          { header: 'Dates', render: (t) => <span className="small">{t.start_date} to {t.end_date}</span> },
                          { header: 'Exams', render: (t) => t.exams_count },
                          {
                            header: 'Status',
                            render: (t) => (
                              <Badge variant={t.is_active ? 'success' : 'neutral'}>
                                {t.is_active ? 'Active' : 'Closed'}
                              </Badge>
                            ),
                          },
                        ]}
                      />
                    </Card>
                  </div>
                </div>
              </div>
            )}

            {/* SECTION C: SUBSCRIPTION & PAYMENTS */}
            {detailSectionTab === 'billing' && (
              <div>
                <div className="row g-3 mb-4">
                  <div className="col-md-4">
                    <StatCard
                      icon="bi-check-circle-fill"
                      label="Confirmed Subscription Revenue"
                      value={`K${Number(schoolDetail.billing.totals.paid_zmw || 0).toFixed(2)} (${schoolDetail.billing.totals.completed_count})`}
                      variant="mustard"
                      accentTop
                    />
                  </div>
                  <div className="col-md-4">
                    <StatCard
                      icon="bi-hourglass-split"
                      label="Pending Subscription Payments"
                      value={`K${Number(schoolDetail.billing.totals.pending_zmw || 0).toFixed(2)} (${schoolDetail.billing.totals.pending_count})`}
                    />
                  </div>
                  <div className="col-md-4">
                    <StatCard
                      icon="bi-exclamation-triangle-fill"
                      label="Failed / Overdue Subscriptions"
                      value={`K${Number(schoolDetail.billing.totals.failed_zmw || 0).toFixed(2)} (${schoolDetail.billing.totals.failed_count})`}
                    />
                  </div>
                </div>

                <Card
                  title="C. Subscription Transaction History"
                  subtitle="All subscription payment history for this school"
                  actions={
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setPlanModalSchool(schoolDetail.school);
                        setSelectedPlan(schoolDetail.school.plan || 'free');
                        setPlanReason('');
                      }}
                    >
                      <i className="bi bi-sliders" /> Review Plan Status
                    </Button>
                  }
                >
                  <DataTable
                    rows={schoolDetail.billing.subscriptions || []}
                    searchKeys={['plan', 'status', 'lipila_reference_id', 'payment_method']}
                    emptyTitle="No subscription transactions recorded"
                    emptyDescription="This school has not initiated any paid subscription checkouts yet."
                    columns={[
                      {
                        header: 'Reference',
                        render: (sub) => (
                          <div>
                            <code className="fw-bold">{sub.lipila_reference_id || sub.stripe_subscription_id || `SUB-${sub.id}`}</code>
                            {sub.is_sandbox_simulated && (
                              <span className="ms-2">
                                <Badge variant="mustard">Sandbox</Badge>
                              </span>
                            )}
                          </div>
                        ),
                      },
                      {
                        header: 'Plan & Cycle',
                        render: (sub) => (
                          <span>
                            <strong>{(sub.plan || '—').toUpperCase()}</strong> ({sub.billing_cycle || 'monthly'})
                          </span>
                        ),
                      },
                      {
                        header: 'Amount',
                        render: (sub) => (
                          <strong>
                            K{Number(sub.amount || 0).toFixed(2)} {sub.currency || 'ZMW'}
                          </strong>
                        ),
                      },
                      {
                        header: 'Method',
                        render: (sub) => <span>{sub.payment_method || 'mobile_money'}</span>,
                      },
                      {
                        header: 'Status',
                        render: (sub) => <Badge variant={statusBadgeVariant(sub.status)}>{sub.status}</Badge>,
                      },
                      {
                        header: 'Timestamps',
                        render: (sub) => (
                          <div className="small text-muted">
                            <div>Created: {formatDateTime(sub.created_at)}</div>
                            {sub.reconciled_at && <div>Settled: {formatDateTime(sub.reconciled_at)}</div>}
                          </div>
                        ),
                      },
                    ]}
                  />
                </Card>
              </div>
            )}

            {/* SECTION D: SCHOOL ACTIVITY TIMELINE */}
            {detailSectionTab === 'timeline' && (
              <Card
                title={`D. Chronological Activity Timeline — ${schoolDetail.school.name}`}
                subtitle={schoolDetail.activity?.audit_logging_notice}
              >
                <div className="row g-2 mb-3">
                  <div className="col-md-3">
                    <input
                      type="search"
                      className="edu-input"
                      placeholder="Search events or actors..."
                      value={detailTimelineFilter.q}
                      onChange={(e) =>
                        setDetailTimelineFilter((f) => ({ ...f, q: e.target.value, page: 1 }))
                      }
                    />
                  </div>
                  <div className="col-md-2">
                    <select
                      className="edu-select"
                      value={detailTimelineFilter.category}
                      onChange={(e) =>
                        setDetailTimelineFilter((f) => ({ ...f, category: e.target.value, page: 1 }))
                      }
                    >
                      {ACTIVITY_CATEGORIES.map((c) => (
                        <option key={c.value} value={c.value}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="col-md-2">
                    <select
                      className="edu-select"
                      value={detailTimelineFilter.role}
                      onChange={(e) =>
                        setDetailTimelineFilter((f) => ({ ...f, role: e.target.value, page: 1 }))
                      }
                    >
                      {ACTOR_ROLES.map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="col-md-2">
                    <select
                      className="edu-select"
                      value={detailTimelineFilter.status}
                      onChange={(e) =>
                        setDetailTimelineFilter((f) => ({ ...f, status: e.target.value, page: 1 }))
                      }
                    >
                      {EVENT_STATUSES.map((s) => (
                        <option key={s.value} value={s.value}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="col-md-3 d-flex gap-2">
                    <input
                      type="date"
                      className="edu-input"
                      value={detailTimelineFilter.date_from}
                      onChange={(e) =>
                        setDetailTimelineFilter((f) => ({ ...f, date_from: e.target.value, page: 1 }))
                      }
                      title="From date"
                    />
                    <input
                      type="date"
                      className="edu-input"
                      value={detailTimelineFilter.date_to}
                      onChange={(e) =>
                        setDetailTimelineFilter((f) => ({ ...f, date_to: e.target.value, page: 1 }))
                      }
                      title="To date"
                    />
                  </div>
                </div>

                {renderActivityTimeline(schoolDetail.activity?.items || [], false)}

                {schoolDetail.activity?.total_pages > 1 && (
                  <div className="d-flex justify-content-between align-items-center mt-3">
                    <span className="small text-muted">
                      Page {schoolDetail.activity.page} of {schoolDetail.activity.total_pages} ({schoolDetail.activity.total} events)
                    </span>
                    <div className="d-flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={schoolDetail.activity.page <= 1}
                        onClick={() =>
                          setDetailTimelineFilter((f) => ({ ...f, page: Math.max(1, f.page - 1) }))
                        }
                      >
                        Previous
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={schoolDetail.activity.page >= schoolDetail.activity.total_pages}
                        onClick={() =>
                          setDetailTimelineFilter((f) => ({ ...f, page: f.page + 1 }))
                        }
                      >
                        Next
                      </Button>
                    </div>
                  </div>
                )}
              </Card>
            )}
          </div>
        )
      ) : activeNavTab === 'schools' ? (
        /* ══════════════════════════════════════════════════════════════════
           VIEW 2: TENANT SCHOOLS DIRECTORY (/superadmin/schools)
           ══════════════════════════════════════════════════════════════════ */
        renderSchoolsDirectoryCard('All Registered Tenant Schools')
      ) : activeNavTab === 'activity' ? (
        /* ══════════════════════════════════════════════════════════════════
           VIEW 3: PLATFORM-WIDE ACTIVITY MONITOR (/superadmin/activity)
           ══════════════════════════════════════════════════════════════════ */
        <Card
          title="Platform-Wide School Activity Monitor"
          subtitle="Search and filter recorded events across all tenant schools by school, date range, category, actor role, and status"
        >
          <div className="row g-2 mb-3">
            <div className="col-md-3">
              <input
                type="search"
                className="edu-input"
                placeholder="Search description, actor, or school..."
                value={activityFilter.q}
                onChange={(e) =>
                  setActivityFilter((f) => ({ ...f, q: e.target.value, page: 1 }))
                }
              />
            </div>
            <div className="col-md-2">
              <select
                className="edu-select"
                value={activityFilter.school_id}
                onChange={(e) =>
                  setActivityFilter((f) => ({ ...f, school_id: e.target.value, page: 1 }))
                }
              >
                <option value="">All Schools</option>
                {schools.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-2">
              <select
                className="edu-select"
                value={activityFilter.category}
                onChange={(e) =>
                  setActivityFilter((f) => ({ ...f, category: e.target.value, page: 1 }))
                }
              >
                {ACTIVITY_CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-2">
              <select
                className="edu-select"
                value={activityFilter.role}
                onChange={(e) =>
                  setActivityFilter((f) => ({ ...f, role: e.target.value, page: 1 }))
                }
              >
                {ACTOR_ROLES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-1">
              <select
                className="edu-select"
                value={activityFilter.status}
                onChange={(e) =>
                  setActivityFilter((f) => ({ ...f, status: e.target.value, page: 1 }))
                }
              >
                {EVENT_STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-2 d-flex gap-1">
              <input
                type="date"
                className="edu-input px-2"
                value={activityFilter.date_from}
                onChange={(e) =>
                  setActivityFilter((f) => ({ ...f, date_from: e.target.value, page: 1 }))
                }
                title="From date"
              />
              <input
                type="date"
                className="edu-input px-2"
                value={activityFilter.date_to}
                onChange={(e) =>
                  setActivityFilter((f) => ({ ...f, date_to: e.target.value, page: 1 }))
                }
                title="To date"
              />
            </div>
          </div>

          <div
            className="small p-2 px-3 rounded-3 mb-3"
            style={{ background: 'var(--color-cool-gray)', color: 'var(--color-strong-blue)' }}
          >
            <i className="bi bi-info-circle-fill me-2" />
            {activityData?.audit_logging_notice || overviewData?.audit_logging_notice}
          </div>

          {loadingActivity ? (
            <LoadingState message="Filtering platform activity logs..." />
          ) : (
            <>
              {renderActivityTimeline(activityData?.items || [], true)}
              {activityData?.total_pages > 1 && (
                <div className="d-flex justify-content-between align-items-center mt-3">
                  <span className="small text-muted">
                    Showing page {activityData.page} of {activityData.total_pages} ({activityData.total} matching events)
                  </span>
                  <div className="d-flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={activityData.page <= 1}
                      onClick={() =>
                        setActivityFilter((f) => ({ ...f, page: Math.max(1, f.page - 1) }))
                      }
                    >
                      Previous
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={activityData.page >= activityData.total_pages}
                      onClick={() =>
                        setActivityFilter((f) => ({ ...f, page: f.page + 1 }))
                      }
                    >
                      Next
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </Card>
      ) : activeNavTab === 'subscriptions' ? (
        /* ══════════════════════════════════════════════════════════════════
           VIEW 4: SAAS SUBSCRIPTIONS & REVENUE MONITOR (/superadmin/subscriptions)
           ══════════════════════════════════════════════════════════════════ */
        <div>
          <div className="row g-3 mb-4">
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-cash-stack"
                label="Net Subscription Revenue (ZMW)"
                value={`K${Number(metrics.subscription_revenue_zmw || 0).toFixed(2)}`}
                variant="mustard"
                accentTop
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-graph-up-arrow"
                label="Estimated Monthly Recurring (MRR)"
                value={`K${Number(metrics.estimated_mrr_zmw || 0).toFixed(2)}`}
                variant="blue"
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-exclamation-octagon"
                label="Failed Subscription Payments"
                value={`${metrics.failed_subscriptions_count || 0} (K${Number(metrics.failed_subscriptions_zmw || 0).toFixed(2)})`}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-wallet2"
                label="Tenant School Fee Volume (Separate)"
                value={`K${Number(metrics.school_fee_collections_zmw || 0).toFixed(2)}`}
              />
            </div>
          </div>

          <Card
            title="Recent SaaS Subscription Transactions"
            subtitle="Platform subscription payments only — school tuition fees paid by parents are tracked separately per school and excluded from platform revenue"
          >
            <DataTable
              rows={recentSubscriptions}
              searchKeys={['school_name', 'plan', 'status', 'lipila_reference_id']}
              emptyTitle="No subscription transactions recorded yet"
              columns={[
                {
                  header: 'School',
                  render: (sub) => (
                    <button
                      type="button"
                      className="btn btn-link p-0 fw-bold text-decoration-none"
                      style={{ color: 'var(--color-strong-blue)' }}
                      onClick={() => navigate(`/superadmin/schools/${sub.school_id}`)}
                    >
                      {sub.school_name}
                    </button>
                  ),
                },
                {
                  header: 'Reference',
                  render: (sub) => <code>{sub.lipila_reference_id || `SUB-${sub.id}`}</code>,
                },
                {
                  header: 'Plan & Cycle',
                  render: (sub) => (
                    <span>
                      <strong>{(sub.plan || '—').toUpperCase()}</strong> ({sub.billing_cycle || 'monthly'})
                    </span>
                  ),
                },
                {
                  header: 'Amount',
                  render: (sub) => <strong>K{Number(sub.amount || 0).toFixed(2)}</strong>,
                },
                {
                  header: 'Status',
                  render: (sub) => <Badge variant={statusBadgeVariant(sub.status)}>{sub.status}</Badge>,
                },
                {
                  header: 'Date',
                  render: (sub) => <span className="small">{formatDateTime(sub.created_at)}</span>,
                },
              ]}
            />
          </Card>
        </div>
      ) : (
        /* ══════════════════════════════════════════════════════════════════
           VIEW 5: DEFAULT PLATFORM OVERVIEW DASHBOARD (/superadmin)
           ══════════════════════════════════════════════════════════════════ */
        <div>
          <DashboardHeader
            title="Multi-Tenant SaaS Command Centre"
            userName={user?.username || 'Super Administrator'}
            userRole="Platform Super Administrator"
            schoolName="SchoolStacks Multi-Tenant Cloud Platform"
            academicYear="2026"
            badgeText="Platform Master Access"
            badgeVariant="gold"
            quickStats={[
              {
                label: 'Total Tenants',
                value: metrics.total_schools || 0,
                icon: 'bi-buildings-fill',
              },
              {
                label: 'Active Tenants',
                value: metrics.active_schools || 0,
                icon: 'bi-check2-circle',
              },
              {
                label: 'Est. MRR',
                value: `K${Number(metrics.estimated_mrr_zmw || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`,
                icon: 'bi-cash-coin',
              },
            ]}
            actions={
              <div className="d-flex gap-2">
                <Button
                  size="sm"
                  variant="accent"
                  icon="bi-buildings"
                  onClick={() => navigate('/superadmin/schools')}
                >
                  Manage Schools
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  icon="bi-activity"
                  onClick={() => navigate('/superadmin/activity')}
                >
                  Live Audit
                </Button>
              </div>
            }
          />

          {/* Quick Action Navigation Grid */}
          <div className="mb-4">
            <QuickActionGrid
              columns={4}
              actions={[
                {
                  icon: 'bi-buildings-fill',
                  label: 'Tenant Directory',
                  description: 'All registered schools',
                  color: '#002583',
                  badge: `${metrics.total_schools || 0}`,
                  onClick: () => navigate('/superadmin/schools'),
                },
                {
                  icon: 'bi-credit-card-2-front-fill',
                  label: 'SaaS Subscriptions',
                  description: 'Billing plans & revenue',
                  color: '#D97706',
                  onClick: () => navigate('/superadmin/subscriptions'),
                },
                {
                  icon: 'bi-activity',
                  label: 'Activity Monitor',
                  description: 'Platform audit stream',
                  color: '#059669',
                  badge: `${metrics.active_schools_24h || 0} active`,
                  onClick: () => navigate('/superadmin/activity'),
                },
                {
                  icon: 'bi-person-plus-fill',
                  label: 'Onboard School',
                  description: 'Register new tenant',
                  color: '#7C3AED',
                  onClick: () => navigate('/register'),
                },
              ]}
            />
          </div>

          {/* Primary Row: Core Schools, Activity & Revenue Metrics */}
          <div className="row g-3 mb-4">
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-buildings-fill"
                label="Registered Schools"
                value={metrics.total_schools || 0}
                variant="blue"
                trend={{
                  text: `${metrics.active_schools || 0} Active Platforms`,
                  positive: true,
                }}
                onClick={() => navigate('/superadmin/schools')}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-check2-circle"
                label="Active Tenants"
                value={metrics.active_schools || 0}
                variant="emerald"
                trend={{
                  text: `${metrics.suspended_schools || 0} Suspended`,
                  positive: (metrics.suspended_schools || 0) === 0,
                }}
                onClick={() => navigate('/superadmin/schools')}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-mortarboard-fill"
                label="Platform Students"
                value={Number(metrics.total_students || 0).toLocaleString()}
                variant="purple"
                trend={{
                  text: 'Across All Tenants',
                  positive: true,
                }}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-cash-stack"
                label="Subscription Revenue"
                value={`K${Number(metrics.subscription_revenue_zmw || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                variant="amber"
                trend={{
                  text: `Est. MRR: K${Number(metrics.estimated_mrr_zmw || 0).toFixed(0)}`,
                  positive: true,
                }}
                onClick={() => navigate('/superadmin/subscriptions')}
              />
            </div>

            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-person-badge-fill"
                label="Faculty & Administrators"
                value={`${metrics.total_teachers || 0} Teachers`}
                variant="cyan"
                trend={{
                  text: `${metrics.total_admins || 0} School Admins`,
                  positive: true,
                }}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-lightning-charge-fill"
                label="24h Active Tenants"
                value={metrics.active_schools_24h || 0}
                variant="emerald"
                trend={{
                  text: `${metrics.active_schools_7d || 0} (7-Day Active)`,
                  positive: true,
                }}
                onClick={() => navigate('/superadmin/activity')}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-hourglass-top"
                label="Trial & Overdue"
                value={`${metrics.trial_schools || 0} Trial`}
                variant="amber"
                trend={{
                  text: `${metrics.expired_or_overdue_schools || 0} Expired Subscriptions`,
                  positive: (metrics.expired_or_overdue_schools || 0) === 0,
                }}
                onClick={() => navigate('/superadmin/subscriptions')}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-shield-check"
                label="System Health"
                value="Optimal"
                variant="emerald"
                trend={{
                  text: 'PostgreSQL Pooled',
                  positive: true,
                }}
              />
            </div>
          </div>

          {/* Analytics Row: Subscription Tier Distribution */}
          <div className="row g-4 mb-4">
            <div className="col-lg-6">
              <Card
                title="SaaS Subscription Plan Distribution"
                subtitle="Tenant schools categorized by active subscription tier"
                actions={
                  <Button size="sm" variant="outline" onClick={() => navigate('/superadmin/subscriptions')}>
                    Manage Plans
                  </Button>
                }
              >
                <DonutChart
                  data={[
                    {
                      label: 'Enterprise',
                      value: schools.filter((s: any) => s.plan === 'enterprise').length,
                      color: '#002583',
                    },
                    {
                      label: 'Standard',
                      value: schools.filter((s: any) => s.plan === 'standard').length,
                      color: '#3B82F6',
                    },
                    {
                      label: 'Basic',
                      value: schools.filter((s: any) => s.plan === 'basic').length,
                      color: '#10B981',
                    },
                    {
                      label: 'Trial / Free',
                      value: schools.filter((s: any) => !s.plan || s.plan === 'free' || s.plan === 'trial').length,
                      color: '#F59E0B',
                    },
                  ]}
                  centerValue={metrics.total_schools || schools.length}
                  centerLabel="Tenants"
                />
              </Card>
            </div>

            <div className="col-lg-6">
              <Card
                title="Platform Audit & Compliance"
                subtitle="Separation of platform SaaS funds and tenant school fees"
              >
                <div
                  className="p-3.5 rounded-3 mb-3 d-flex flex-column gap-2 small"
                  style={{
                    background: '#F8FAFC',
                    borderLeft: '4px solid var(--color-strong-blue)',
                    border: '1px solid #E2E8F0',
                  }}
                >
                  <div>
                    <strong style={{ color: 'var(--color-strong-blue)' }}>
                      <i className="bi bi-shield-check me-1" /> Multi-Tenant Financial Isolation:
                    </strong>{' '}
                    Net Subscription Revenue (<strong>K{Number(metrics.subscription_revenue_zmw || 0).toFixed(2)}</strong>, Est. MRR:{' '}
                    <strong>K{Number(metrics.estimated_mrr_zmw || 0).toFixed(2)}</strong>) includes only verified SaaS platform subscriptions.
                  </div>
                  <div className="text-secondary">
                    Total school tuition fees collected by tenants (<strong>K{Number(metrics.school_fee_collections_zmw || 0).toFixed(2)}</strong> across all schools) are strictly isolated per tenant and excluded from platform revenue.
                  </div>
                </div>

                <div className="d-flex justify-content-between align-items-center flex-wrap gap-2 pt-2">
                  <span className="small text-muted">
                    Last audit event recorded: {recentActivity[0] ? formatDateTime(recentActivity[0].created_at) : 'Active'}
                  </span>
                  <Button size="sm" variant="accent" onClick={() => navigate('/superadmin/subscriptions')}>
                    View Subscription Ledger
                  </Button>
                </div>
              </Card>
            </div>
          </div>

          {/* Clickable Tenant Schools Table */}
          <div className="mb-4">{renderSchoolsDirectoryCard('Registered Schools — Click Any School to Inspect')}</div>

          {/* Recent Platform Activity Preview */}
          <Card
            title="Recent Platform Activity"
            subtitle="Latest recorded logins, enrollments, academic updates, and billing events across schools"
            actions={
              <Button size="sm" variant="outline" onClick={() => navigate('/superadmin/activity')}>
                Open Full Activity Monitor <i className="bi bi-arrow-right" />
              </Button>
            }
          >
            {renderActivityTimeline(recentActivity.slice(0, 8), true)}
          </Card>
        </div>
      )}

      {/* ── MODAL 1: CONFIRM SCHOOL SUSPENSION / REACTIVATION ── */}
      <Modal
        open={Boolean(statusModalSchool)}
        title={
          statusModalSchool?.is_active
            ? `Suspend School: ${statusModalSchool?.name}`
            : `Reactivate School: ${statusModalSchool?.name}`
        }
        onClose={() => setStatusModalSchool(null)}
      >
        {statusModalSchool && (
          <form onSubmit={handleConfirmStatusChange}>
            <div
              className="p-3 rounded-3 mb-3 small"
              style={{
                background: statusModalSchool.is_active ? '#FEF2F2' : '#ECFDF5',
                color: statusModalSchool.is_active ? '#991B1B' : '#065F46',
              }}
            >
              {statusModalSchool.is_active ? (
                <>
                  <strong>Effect of Suspension:</strong> Suspending <strong>{statusModalSchool.name}</strong> immediately
                  blocks all school administrators, teachers, students, and parents of this school from signing in or
                  accessing tenant APIs. <strong>No school data is deleted.</strong> Platform superadmins retain full
                  inspection access and can reactivate the school at any time.
                </>
              ) : (
                <>
                  <strong>Effect of Reactivation:</strong> Reactivating <strong>{statusModalSchool.name}</strong> restores
                  login and portal access for all authorized users of this school.
                </>
              )}
            </div>

            <FormField label="Audit Reason (Required)" required>
              <textarea
                className="edu-textarea"
                rows={3}
                required
                placeholder={
                  statusModalSchool.is_active
                    ? 'e.g., Overdue enterprise invoice / Terms of service review...'
                    : 'e.g., Subscription payment verified / Account review completed...'
                }
                value={statusReason}
                onChange={(e) => setStatusReason(e.target.value)}
              />
            </FormField>

            <div className="d-flex justify-content-end gap-2 mt-3">
              <Button type="button" variant="outline" onClick={() => setStatusModalSchool(null)}>
                Cancel
              </Button>
              <Button
                type="submit"
                variant={statusModalSchool.is_active ? 'danger' : 'accent'}
                disabled={submittingAction}
              >
                {submittingAction
                  ? 'Saving Audit Log...'
                  : statusModalSchool.is_active
                  ? 'Confirm Suspension'
                  : 'Confirm Reactivation'}
              </Button>
            </div>
          </form>
        )}
      </Modal>

      {/* ── MODAL 2: REVIEW / SYNC SUBSCRIPTION PLAN ── */}
      <Modal
        open={Boolean(planModalSchool)}
        title={`Subscription Plan Management: ${planModalSchool?.name || ''}`}
        onClose={() => setPlanModalSchool(null)}
      >
        {planModalSchool && (
          <form onSubmit={handleConfirmPlanChange}>
            <div
              className="p-3 rounded-3 mb-3 small"
              style={{ background: 'var(--color-cool-gray)', color: 'var(--color-strong-blue)' }}
            >
              <strong>Payment Integrity Policy:</strong> Superadmins cannot bypass payment processing or falsely mark unpaid
              subscriptions as paid. Upgrading to a paid tier (Starter, Growth, Enterprise) requires a verified{' '}
              <code>active</code> or <code>completed</code> subscription payment record for that school.
            </div>

            <FormField label="Target Subscription Plan" required>
              <select
                className="edu-select"
                value={selectedPlan}
                onChange={(e) => setSelectedPlan(e.target.value)}
              >
                <option value="free">Free Tier</option>
                <option value="starter">Starter (Requires Verified Payment)</option>
                <option value="growth">Growth (Requires Verified Payment)</option>
                <option value="enterprise">Enterprise (Requires Verified Payment)</option>
              </select>
            </FormField>

            <FormField label="Audit Reason (Required)" required>
              <textarea
                className="edu-textarea"
                rows={2}
                required
                placeholder="e.g., Downgrading expired trial to Free tier / Syncing verified subscription..."
                value={planReason}
                onChange={(e) => setPlanReason(e.target.value)}
              />
            </FormField>

            <div className="d-flex justify-content-end gap-2 mt-3">
              <Button type="button" variant="outline" onClick={() => setPlanModalSchool(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={submittingAction}>
                {submittingAction ? 'Applying...' : 'Apply Plan Change'}
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </AppLayout>
  );
};
