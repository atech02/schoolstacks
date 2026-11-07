import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AppLayout, NavItem } from '../layouts/AppLayout';
import { apiFetch } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import {
  AlertBanner,
  Badge,
  Button,
  Card,
  DataTable,
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

const PARENT_NAV: NavItem[] = [
  { id: 'overview', label: 'Children Overview', icon: 'bi-people-fill', section: 'FAMILY PORTAL' },
  { id: 'results', label: 'Exam Results & Reports', icon: 'bi-award-fill', section: 'STUDENT PROGRESS' },
  { id: 'attendance', label: 'Attendance History', icon: 'bi-calendar-check-fill', section: 'STUDENT PROGRESS' },
  { id: 'timetable', label: 'Child Timetable', icon: 'bi-calendar3-week', section: 'STUDENT PROGRESS' },
  { id: 'exams', label: 'Examination Schedule', icon: 'bi-calendar-event-fill', section: 'STUDENT PROGRESS' },
  { id: 'assignments', label: 'Homework & Assignments', icon: 'bi-clipboard-check-fill', section: 'STUDENT PROGRESS' },
  { id: 'materials', label: 'Study Materials', icon: 'bi-folder-symlink-fill', section: 'STUDENT PROGRESS' },
  { id: 'fees', label: 'Pay School Fees', icon: 'bi-credit-card-2-front-fill', section: 'FINANCE' },
  { id: 'announcements', label: 'School Announcements', icon: 'bi-megaphone-fill', section: 'COMMUNICATION' },
];

export const ParentPortal: React.FC = () => {
  const navigate = useNavigate();
  const { user, school } = useAuth();
  const [activeTab, setActiveTab] = useState('overview');
  const [data, setData] = useState<any>(null);
  const [selectedChildId, setSelectedChildId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fee Checkout Modal
  const [checkoutItem, setCheckoutItem] = useState<{
    studentId: number;
    studentName: string;
    termId: number;
    termName: string;
    balance: number;
  } | null>(null);
  const [payAmount, setPayAmount] = useState('');
  const [payMethod, setPayMethod] = useState<'mobile_money' | 'card'>('mobile_money');
  const [payPhone, setPayPhone] = useState('0977111222');
  const [submitting, setSubmitting] = useState(false);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/api/parent/overview');
      setData(res);
      if (res.parent?.phone) setPayPhone(res.parent.phone);
      if (res.children?.[0] && !selectedChildId) {
        setSelectedChildId(res.children[0].id);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [selectedChildId]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const handleCheckout = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!checkoutItem) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiFetch('/api/billing/checkout-fee', {
        method: 'POST',
        body: JSON.stringify({
          student_id: checkoutItem.studentId,
          term_id: checkoutItem.termId,
          amount: payAmount,
          payment_method: payMethod,
          phone_number: payPhone,
        }),
      });
      setCheckoutItem(null);
      navigate(`/billing/status/${res.reference_id}`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <LoadingState message="Loading Parent Portal..." />;

  const children = data?.children || [];
  const child = children.find((c: any) => c.id === selectedChildId) || children[0];
  const announcements = data?.announcements || [];

  return (
    <AppLayout
      title={`Parent Portal — ${data?.parent?.first_name || ''} ${data?.parent?.last_name || ''}`}
      subtitle="Monitor your child's attendance, assignments, exam schedule, academic grades, and pay fees online"
      navItems={PARENT_NAV}
      activeTab={activeTab}
      onSelectTab={setActiveTab}
      actions={
        children.length > 1 ? (
          <div className="d-flex align-items-center gap-2">
            <label className="text-white small fw-bold mb-0 d-none d-sm-inline">Switch Child:</label>
            <select
              className="edu-select py-1"
              style={{ minWidth: 200 }}
              value={child?.id || ''}
              onChange={(e) => setSelectedChildId(Number(e.target.value))}
            >
              {children.map((c: any) => (
                <option key={c.id} value={c.id}>
                  {c.first_name} {c.last_name} ({c.class_name})
                </option>
              ))}
            </select>
          </div>
        ) : undefined
      }
    >
      <AlertBanner variant="danger" message={error} onDismiss={() => setError(null)} />

      {!child ? (
        <Card title="No Linked Student Found">
          <div className="p-4 text-center">
            <i className="bi bi-people text-muted fs-1 mb-3 d-block" />
            <h5 className="fw-bold text-primary">No Student Profile Linked</h5>
            <p className="text-muted small mx-auto" style={{ maxWidth: 500 }}>
              Your parent account is registered with username <strong>{data?.parent?.username || 'parent'}</strong> and phone <strong>{data?.parent?.phone || 'on file'}</strong>.
              Please ask your child&apos;s school administrator to link your account to your child&apos;s admission number in the school admin portal.
            </p>
          </div>
        </Card>
      ) : (
        <>
          <DashboardHeader
            title="Guardian & Family Portal"
            userName={data?.parent?.first_name ? `${data.parent.first_name} ${data.parent.last_name}` : user?.username || 'Parent'}
            userRole="Guardian Portal"
            schoolName={school?.name || child.school_name || 'SchoolStacks Academy'}
            academicTerm={child.terms?.[0]?.name || 'Term 1'}
            academicYear="2026"
            badgeText={`Viewing: ${child.first_name} ${child.last_name}`}
            badgeVariant="gold"
            quickStats={[
              {
                label: 'Class',
                value: child.class_name,
                icon: 'bi-door-open',
              },
              {
                label: 'Tuition Balance',
                value: `K${Number(child.fee_balances?.[0]?.balance || 0).toFixed(0)}`,
                icon: 'bi-wallet2',
              },
              {
                label: 'Enrolled Children',
                value: children.length,
                icon: 'bi-people',
              },
            ]}
            actions={
              Number(child.fee_balances?.[0]?.balance || 0) > 0 ? (
                <Button
                  size="sm"
                  variant="accent"
                  icon="bi-phone"
                  onClick={() => {
                    const b = child.fee_balances?.[0];
                    if (b) {
                      setCheckoutItem({
                        studentId: child.id,
                        studentName: `${child.first_name} ${child.last_name}`,
                        termId: b.term_id,
                        termName: b.term_name,
                        balance: b.balance,
                      });
                      setPayAmount(String(b.balance));
                    }
                  }}
                >
                  Pay Child Fees
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  icon="bi-award"
                  onClick={() => setActiveTab('results')}
                >
                  View Reports
                </Button>
              )
            }
          />

          {/* Child Switcher Pills (If multiple children linked) */}
          {children.length > 1 && (
            <div className="card border-0 mb-4 bg-white shadow-sm p-2 rounded-3">
              <div className="d-flex align-items-center gap-2 flex-wrap">
                <span className="small fw-bold text-muted ps-2">Select Student:</span>
                {children.map((c: any) => (
                  <button
                    key={c.id}
                    type="button"
                    className={`btn btn-sm rounded-pill fw-semibold ${
                      child.id === c.id
                        ? 'btn-primary px-3 shadow-sm'
                        : 'btn-outline-secondary px-3 border-0'
                    }`}
                    onClick={() => setSelectedChildId(c.id)}
                  >
                    <i className="bi bi-person-fill me-1" />
                    {c.first_name} ({c.class_name})
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Quick Actions Grid */}
          <div className="mb-4">
            <QuickActionGrid
              columns={4}
              actions={[
                {
                  icon: 'bi-credit-card-2-front-fill',
                  label: 'Pay School Fees',
                  description: 'Mobile money online checkout',
                  color: '#D97706',
                  badge: Number(child.fee_balances?.[0]?.balance || 0) > 0 ? `K${Number(child.fee_balances?.[0]?.balance || 0).toFixed(0)}` : undefined,
                  onClick: () => setActiveTab('fees'),
                },
                {
                  icon: 'bi-award-fill',
                  label: 'Academic Results',
                  description: 'Term marks & PDF report card',
                  color: '#002583',
                  onClick: () => setActiveTab('results'),
                },
                {
                  icon: 'bi-calendar3-week',
                  label: 'Child Timetable',
                  description: 'Weekly subjects & periods',
                  color: '#7C3AED',
                  onClick: () => setActiveTab('timetable'),
                },
                {
                  icon: 'bi-calendar-check-fill',
                  label: 'Attendance History',
                  description: 'Daily presence & absences',
                  color: '#059669',
                  onClick: () => setActiveTab('attendance'),
                },
              ]}
            />
          </div>

          {/* Modern Statistic Cards */}
          <div className="row g-3 mb-4">
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-person-badge-fill"
                label="Active Student"
                value={`${child.first_name} ${child.last_name}`}
                variant="blue"
                trend={{
                  text: `Admission: ${child.admission_no || '-'}`,
                  positive: true,
                }}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-door-open-fill"
                label="Enrolled Class"
                value={child.class_name}
                variant="purple"
                trend={{
                  text: child.class_teacher_name ? `Class Teacher: ${child.class_teacher_name}` : 'Enrolled',
                  positive: true,
                }}
                onClick={() => setActiveTab('timetable')}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-wallet2"
                label="Outstanding Fees"
                value={`K${Number(child.fee_balances?.[0]?.balance || 0).toFixed(2)}`}
                variant={Number(child.fee_balances?.[0]?.balance || 0) > 0 ? 'rose' : 'emerald'}
                trend={{
                  text: Number(child.fee_balances?.[0]?.balance || 0) > 0 ? 'Payment Outstanding' : 'Fees Cleared',
                  positive: Number(child.fee_balances?.[0]?.balance || 0) <= 0,
                }}
                onClick={() => setActiveTab('fees')}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-calendar2-check-fill"
                label="Attendance Logs"
                value={child.attendance?.length || 0}
                variant="emerald"
                trend={{
                  text: `${child.attendance?.filter((a: any) => a.status === 'Present').length || 0} Present Days`,
                  positive: true,
                }}
                onClick={() => setActiveTab('attendance')}
              />
            </div>
          </div>

          {/* ── OVERVIEW OR FEES TAB ── */}
          {(activeTab === 'overview' || activeTab === 'fees') && (
            <div className="row g-4 mb-4">
              <div className="col-lg-5">
                <Card title={`School Fee Balances — ${child.first_name}`}>
                  <DataTable
                    rows={child.fee_balances || []}
                    columns={[
                      { header: 'Term', render: (b) => <span className="fw-bold">{b.term_name}</span> },
                      {
                        header: 'Balance (ZMW)',
                        render: (b) => (
                          <span className="fw-bold">K{Number(b.balance || 0).toFixed(2)}</span>
                        ),
                      },
                      {
                        header: 'Pay Online',
                        render: (b) =>
                          b.balance > 0 ? (
                            <Button
                              size="sm"
                              variant="accent"
                              icon="bi-phone"
                              onClick={() => {
                                setCheckoutItem({
                                  studentId: child.id,
                                  studentName: `${child.first_name} ${child.last_name}`,
                                  termId: b.term_id,
                                  termName: b.term_name,
                                  balance: b.balance,
                                });
                                setPayAmount(String(b.balance));
                              }}
                            >
                              Pay Online
                            </Button>
                          ) : (
                            <Badge variant="success">Cleared</Badge>
                          ),
                      },
                    ]}
                  />
                </Card>
              </div>

              <div className="col-lg-7">
                <Card title="Payment History & Digital Receipts (RCT-xxxxx)">
                  <DataTable
                    rows={child.payments || []}
                    columns={[
                      { header: 'Term', render: (p) => p.term_name },
                      {
                        header: 'Amount',
                        render: (p) => (
                          <span className="fw-bold">K{Number(p.amount_paid || 0).toFixed(2)}</span>
                        ),
                      },
                      {
                        header: 'Status',
                        render: (p) => (
                          <Badge variant={p.status === 'completed' ? 'success' : 'mustard'}>
                            {p.status}
                          </Badge>
                        ),
                      },
                      {
                        header: 'Receipt / Action',
                        render: (p) =>
                          p.status === 'completed' ? (
                            <Link
                              to={`/admin/receipt/${p.id}`}
                              className="edu-btn edu-btn-outline edu-btn-sm"
                            >
                              <i className="bi bi-receipt" /> {p.reference || 'Receipt'}
                            </Link>
                          ) : p.lipila_reference_id ? (
                            <Link
                              to={`/billing/status/${p.lipila_reference_id}`}
                              className="edu-btn edu-btn-accent edu-btn-sm"
                            >
                              Complete / Simulate
                            </Link>
                          ) : (
                            '—'
                          ),
                      },
                    ]}
                  />
                </Card>
              </div>
            </div>
          )}

          {/* ── ACADEMIC RESULTS ── */}
          {(activeTab === 'overview' || activeTab === 'results') && (
            <Card
              title={`Academic Results — ${child.first_name}`}
              className="mb-4"
              actions={
                <a
                  href={`/student/report-card/${child.id}/${child.terms?.[0]?.id || child.fee_balances?.[0]?.term_id || 1}`}
                  target="_blank"
                  rel="noreferrer"
                  className="edu-btn edu-btn-primary edu-btn-sm text-decoration-none"
                >
                  <i className="bi bi-file-earmark-pdf-fill me-1" /> Download Official Report Card (PDF)
                </a>
              }
            >
              <DataTable
                rows={child.results || []}
                columns={[
                  { header: 'Subject', render: (r) => <span className="fw-bold">{r.subject}</span> },
                  { header: 'Exam', render: (r) => r.exam },
                  { header: 'Marks', render: (r) => `${r.marks}%` },
                  { header: 'Grade', render: (r) => <Badge variant="mustard">{r.grade}</Badge> },
                ]}
              />
            </Card>
          )}

          {/* ── CHILD TIMETABLE ── */}
          {activeTab === 'timetable' && (
            <Card
              title={`Weekly Class Timetable — ${child.first_name} (${child.class_name})`}
              subtitle="Daily lesson periods, subjects, and classroom venues"
              className="mb-4"
            >
              {!child.timetable || child.timetable.length === 0 ? (
                <div className="text-center py-4 text-muted">
                  <i className="bi bi-calendar3-week fs-1 mb-2 d-block" />
                  <div className="fw-bold">No Timetable Published</div>
                  <div className="small">The school administrator has not published a timetable for {child.class_name} yet.</div>
                </div>
              ) : (
                <div className="d-flex flex-column gap-3">
                  {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'].map((day) => {
                    const daySlots = child.timetable.filter((t: any) => t.day.toLowerCase() === day.toLowerCase());
                    return (
                      <div key={day} className="border rounded p-3 bg-light">
                        <div className="d-flex justify-content-between align-items-center mb-2">
                          <h6 className="fw-bold text-primary mb-0">{day}</h6>
                          <Badge variant={daySlots.length > 0 ? 'blue' : 'neutral'}>
                            {daySlots.length} Lesson{daySlots.length === 1 ? '' : 's'}
                          </Badge>
                        </div>
                        {daySlots.length === 0 ? (
                          <div className="text-muted small fst-italic">No classes scheduled on {day}.</div>
                        ) : (
                          <div className="row g-2">
                            {daySlots.map((slot: any) => (
                              <div key={slot.id} className="col-md-6 col-lg-4">
                                <div className="card p-2 shadow-sm border h-100 bg-white">
                                  <div className="d-flex justify-content-between align-items-center mb-1">
                                    <span className="badge bg-primary-subtle text-primary fw-bold">
                                      {slot.start_time} - {slot.end_time}
                                    </span>
                                    <span className="small text-muted">
                                      <i className="bi bi-geo-alt me-1" /> {slot.room || 'Main Class'}
                                    </span>
                                  </div>
                                  <div className="fw-bold fs-6 text-dark">{slot.subject_name}</div>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </Card>
          )}

          {/* ── EXAMINATION SCHEDULE & PERIODS ── */}
          {activeTab === 'exams' && (
            <Card
              title={`Examination Timetable & Periods — ${child.class_name}`}
              subtitle="Official examination schedule and venues scheduled by school administration"
            >
              <DataTable
                rows={child.exams || []}
                columns={[
                  {
                    header: 'Examination',
                    render: (ex) => (
                      <div>
                        <span className="fw-bold">{ex.name}</span>
                        <div className="small text-muted">{ex.term_name}</div>
                      </div>
                    ),
                  },
                  {
                    header: 'Exam Period',
                    render: (ex) => (
                      <div className="small fw-semibold">
                        {ex.start_date && ex.end_date && ex.start_date !== ex.end_date
                          ? `${ex.start_date} to ${ex.end_date}`
                          : ex.start_date || ex.date || 'TBD'}
                      </div>
                    ),
                  },
                  {
                    header: 'Timing',
                    render: (ex) => (
                      <div className="small text-muted">
                        {ex.start_time ? `${ex.start_time} - ${ex.end_time || ''}` : 'Schedule TBD'}
                      </div>
                    ),
                  },
                  {
                    header: 'Venue',
                    render: (ex) => ex.venue || 'Main Hall / Class',
                  },
                ]}
              />
            </Card>
          )}

          {/* ── HOMEWORK & ASSIGNMENTS ── */}
          {activeTab === 'assignments' && (
            <Card
              title={`Class Assignments & Coursework — ${child.class_name}`}
              subtitle="Assignments issued by subject teachers with deadlines and download attachments"
            >
              <DataTable
                rows={child.assignments || []}
                columns={[
                  {
                    header: 'Title & Instructions',
                    render: (a) => (
                      <div>
                        <span className="fw-bold">{a.title}</span>
                        <div className="small text-muted">{a.description}</div>
                      </div>
                    ),
                  },
                  { header: 'Subject', render: (a) => a.subject_name },
                  {
                    header: 'Assigned Date',
                    render: (a) => a.assignment_date || '—',
                  },
                  {
                    header: 'Due Date',
                    render: (a) => (
                      <span className="fw-semibold text-danger">
                        {a.deadline ? a.deadline.slice(0, 10) : '—'}
                      </span>
                    ),
                  },
                  {
                    header: 'Attachment',
                    render: (a) =>
                      a.has_attachment ? (
                        <a
                          href={`/api/assignments/${a.id}/attachment`}
                          download
                          className="edu-btn edu-btn-outline edu-btn-sm"
                        >
                          <i className="bi bi-paperclip" /> {a.attachment_name || 'Download'}
                        </a>
                      ) : (
                        <span className="text-muted small">None</span>
                      ),
                  },
                ]}
              />
            </Card>
          )}

          {/* ── STUDY MATERIALS ── */}
          {activeTab === 'materials' && (
            <Card
              title={`Study Materials & Syllabus Documents — ${child.class_name}`}
              subtitle="Teaching notes, revision resources, and past papers uploaded by teachers"
            >
              <DataTable
                rows={child.materials || []}
                columns={[
                  {
                    header: 'Title & Details',
                    render: (m) => (
                      <div>
                        <span className="fw-bold">{m.title}</span>
                        <div className="small text-muted">{m.description}</div>
                      </div>
                    ),
                  },
                  { header: 'Subject', render: (m) => m.subject_name },
                  {
                    header: 'Download Resource',
                    render: (m) => (
                      <a
                        href={`/api/materials/${m.id}/download`}
                        className="edu-btn edu-btn-outline edu-btn-sm"
                        download
                      >
                        <i className="bi bi-download" /> Download Document
                      </a>
                    ),
                  },
                ]}
              />
            </Card>
          )}

          {/* ── ATTENDANCE TAB ── */}
          {activeTab === 'attendance' && (
            <>
              <div className="row g-3 mb-4">
                <div className="col-sm-6 col-xl-3">
                  <StatCard
                    icon="bi-pie-chart-fill"
                    label="Attendance Rate"
                    value={`${child.attendance_stats?.rate ?? 100}%`}
                    variant="blue"
                  />
                </div>
                <div className="col-sm-6 col-xl-3">
                  <StatCard
                    icon="bi-check-circle-fill"
                    label="Days Present"
                    value={child.attendance_stats?.present ?? 0}
                    variant="blue"
                  />
                </div>
                <div className="col-sm-6 col-xl-3">
                  <StatCard
                    icon="bi-x-circle-fill"
                    label="Days Absent"
                    value={child.attendance_stats?.absent ?? 0}
                    variant="mustard"
                  />
                </div>
                <div className="col-sm-6 col-xl-3">
                  <StatCard
                    icon="bi-calendar-check"
                    label="Recorded Sessions"
                    value={child.attendance_stats?.total ?? (child.attendance?.length || 0)}
                  />
                </div>
              </div>

              <Card
                title={`Attendance Register — ${child.first_name} ${child.last_name}`}
                subtitle={`Showing last 30 recorded roll calls for class ${child.class_name}`}
              >
                <DataTable
                  rows={child.attendance || []}
                  columns={[
                    {
                      header: 'Date',
                      render: (a) => <span className="fw-bold">{a.date}</span>,
                    },
                    {
                      header: 'Status',
                      render: (a) => {
                        let badgeVar: any = 'neutral';
                        if (a.status === 'Present') badgeVar = 'success';
                        else if (a.status === 'Late') badgeVar = 'mustard';
                        else if (a.status === 'Absent') badgeVar = 'danger';
                        else if (a.status === 'Sick') badgeVar = 'mustard';
                        else if (a.status === 'Excused') badgeVar = 'blue';
                        return <Badge variant={badgeVar}>{a.status}</Badge>;
                      },
                    },
                    {
                      header: 'Remarks',
                      render: (a) => a.remarks || '—',
                    },
                  ]}
                />
              </Card>
            </>
          )}

          {/* ── ANNOUNCEMENTS TAB ── */}
          {activeTab === 'announcements' && (
            <Card title="School Announcements">
              <DataTable
                rows={announcements}
                columns={[
                  {
                    header: 'Announcement',
                    render: (a) => (
                      <div>
                        <div className="fw-bold">{a.title}</div>
                        <div className="small text-muted">{a.message}</div>
                      </div>
                    ),
                  },
                ]}
              />
            </Card>
          )}
        </>
      )}

      {/* Online Fee Checkout Modal */}
      <Modal
        open={Boolean(checkoutItem)}
        title={`School Fee Checkout — ${checkoutItem?.studentName || ''}`}
        onClose={() => setCheckoutItem(null)}
      >
        <form onSubmit={handleCheckout}>
          <div
            className="p-3 rounded-3 mb-3 small"
            style={{ background: 'var(--color-cool-gray)' }}
          >
            Term: <strong>{checkoutItem?.termName}</strong> &bull; Outstanding Balance:{' '}
            <strong>K{Number(checkoutItem?.balance || 0).toFixed(2)} ZMW</strong>
          </div>
          <FormField label="Amount to Pay (ZMW)">
            <input
              type="number"
              step="0.01"
              className="edu-input"
              value={payAmount}
              onChange={(e) => setPayAmount(e.target.value)}
              required
            />
          </FormField>
          <FormField label="Payment Method">
            <select
              className="edu-select"
              value={payMethod}
              onChange={(e) => setPayMethod(e.target.value as 'mobile_money' | 'card')}
            >
              <option value="mobile_money">Mobile Money (MTN / Airtel / Zamtel)</option>
              <option value="card">Bank Card (Visa / Mastercard)</option>
            </select>
          </FormField>
          <FormField label="Mobile Money Phone Number">
            <input
              className="edu-input"
              value={payPhone}
              onChange={(e) => setPayPhone(e.target.value)}
              required
            />
          </FormField>
          <div className="d-flex justify-content-end gap-2 mt-3">
            <Button type="button" variant="outline" onClick={() => setCheckoutItem(null)}>
              Cancel
            </Button>
            <Button type="submit" variant="accent" disabled={submitting} icon="bi-shield-check">
              {submitting ? 'Processing...' : 'Pay Now Securely'}
            </Button>
          </div>
        </form>
      </Modal>
    </AppLayout>
  );
};
