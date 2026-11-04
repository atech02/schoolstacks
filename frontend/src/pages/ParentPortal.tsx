import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AppLayout, NavItem } from '../layouts/AppLayout';
import { apiFetch } from '../services/api';
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

const PARENT_NAV: NavItem[] = [
  { id: 'overview', label: 'Children Overview', icon: 'bi-people-fill' },
  { id: 'fees', label: 'Pay School Fees', icon: 'bi-credit-card-2-front-fill' },
  { id: 'results', label: 'Exam Results & Reports', icon: 'bi-award-fill' },
  { id: 'exams', label: 'Examination Schedule', icon: 'bi-calendar-event-fill' },
  { id: 'assignments', label: 'Homework & Assignments', icon: 'bi-clipboard-check-fill' },
  { id: 'materials', label: 'Study Materials', icon: 'bi-folder-symlink-fill' },
  { id: 'attendance', label: 'Attendance History', icon: 'bi-calendar-check-fill' },
  { id: 'announcements', label: 'School Announcements', icon: 'bi-megaphone-fill' },
];

export const ParentPortal: React.FC = () => {
  const navigate = useNavigate();
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
          <div className="row g-3 mb-4">
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-person-badge-fill"
                label="Selected Child"
                value={`${child.first_name} ${child.last_name}`}
                variant="blue"
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-door-open-fill"
                label="Enrolled Class"
                value={child.class_name}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-wallet2"
                label="Outstanding Balance"
                value={`K${Number(child.fee_balances?.[0]?.balance || 0).toFixed(2)}`}
                variant="mustard"
                accentTop
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-calendar2-check-fill"
                label="Attendance Logs"
                value={child.attendance?.length || 0}
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
                child.fee_balances?.[0] && (
                  <a
                    href={`/student/report-card/${child.id}/${child.fee_balances[0].term_id}`}
                    target="_blank"
                    rel="noreferrer"
                    className="edu-btn edu-btn-primary edu-btn-sm"
                  >
                    <i className="bi bi-file-earmark-pdf" /> Download PDF Report Card
                  </a>
                )
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
            <Card title={`Attendance Log — ${child.first_name}`}>
              <DataTable
                rows={child.attendance || []}
                columns={[
                  { header: 'Date', render: (a) => a.date },
                  {
                    header: 'Status',
                    render: (a) => (
                      <Badge variant={a.status === 'Present' ? 'success' : 'danger'}>
                        {a.status}
                      </Badge>
                    ),
                  },
                ]}
              />
            </Card>
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
