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

const STUDENT_NAV: NavItem[] = [
  { id: 'dashboard', label: 'My Dashboard', icon: 'bi-grid-1x2-fill', section: 'OVERVIEW' },
  { id: 'results', label: 'Exam Results & Report Card', icon: 'bi-award-fill', section: 'ACADEMICS' },
  { id: 'timetable', label: 'My Timetable', icon: 'bi-calendar3-week', section: 'ACADEMICS' },
  { id: 'attendance', label: 'My Attendance', icon: 'bi-calendar2-check-fill', section: 'ACADEMICS' },
  { id: 'assignments', label: 'Assignments', icon: 'bi-journal-text', section: 'LEARNING' },
  { id: 'materials', label: 'Study Materials', icon: 'bi-book-half', section: 'LEARNING' },
  { id: 'fees', label: 'School Fees & Payments', icon: 'bi-wallet2', section: 'FINANCE' },
  { id: 'announcements', label: 'Announcements', icon: 'bi-megaphone-fill', section: 'COMMUNICATION' },
];

export const StudentPortal: React.FC = () => {
  const navigate = useNavigate();
  const { user, school } = useAuth();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fee checkout modal
  const [checkoutTerm, setCheckoutTerm] = useState<any>(null);
  const [payAmount, setPayAmount] = useState('');
  const [payMethod, setPayMethod] = useState<'mobile_money' | 'card'>('mobile_money');
  const [payPhone, setPayPhone] = useState('0977123456');
  const [submittingPay, setSubmittingPay] = useState(false);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/api/student/overview');
      setData(res);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const handleFeeCheckout = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!checkoutTerm || !data?.student) return;
    setSubmittingPay(true);
    setError(null);
    try {
      const res = await apiFetch('/api/billing/checkout-fee', {
        method: 'POST',
        body: JSON.stringify({
          student_id: data.student.id,
          term_id: checkoutTerm.term_id,
          amount: payAmount,
          payment_method: payMethod,
          phone_number: payPhone,
        }),
      });
      setCheckoutTerm(null);
      navigate(`/billing/status/${res.reference_id}`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmittingPay(false);
    }
  };

  if (loading) return <LoadingState message="Loading Student Portal..." />;

  const student = data?.student || {};
  const feeBalances = data?.fee_balances || [];
  const payments = data?.payments || [];
  const results = data?.results || [];
  const assignments = data?.assignments || [];
  const materials = data?.materials || [];
  const announcements = data?.announcements || [];
  const timetable = data?.timetable || [];
  const attendance = data?.attendance || { present: 0, absent: 0, total: 0, rate: 100, records: [] };
  const terms = data?.terms || [];
  const [selectedReportTerm, setSelectedReportTerm] = useState('');

  const totalBalance = feeBalances.reduce(
    (acc: number, b: any) => acc + Number(b.balance || 0),
    0
  );

  return (
    <AppLayout
      title={`Student Portal — ${student.first_name || ''} ${student.last_name || ''}`}
      subtitle={`Admission No: ${student.admission_no || ''} • Class: ${student.class_name || ''}`}
      navItems={STUDENT_NAV}
      activeTab={activeTab}
      onSelectTab={setActiveTab}
    >
      <AlertBanner variant="success" message={message} onDismiss={() => setMessage(null)} />
      <AlertBanner variant="danger" message={error} onDismiss={() => setError(null)} />

      {activeTab === 'dashboard' && (
        <>
          <DashboardHeader
            title="Student Learning Space"
            userName={student.first_name ? `${student.first_name} ${student.last_name}` : user?.username || 'Student'}
            userRole="Student Portal"
            schoolName={school?.name || student.school_name || 'SchoolStacks Academy'}
            academicTerm={data?.active_term?.name || 'Term 1'}
            academicYear={data?.active_term?.academic_year || '2026'}
            badgeText={`Admission: ${student.admission_no || '-'}`}
            badgeVariant="blue"
            quickStats={[
              {
                label: 'Class',
                value: student.class_name || '—',
                icon: 'bi-person-vcard',
              },
              {
                label: 'Attendance',
                value: `${attendance.length > 0 ? Math.round((attendance.filter((a: any) => a.status === 'Present' || a.status === 'Late').length / attendance.length) * 100) : 100}%`,
                icon: 'bi-calendar2-check',
              },
              {
                label: 'Fee Balance',
                value: `K${totalBalance.toFixed(0)}`,
                icon: 'bi-wallet2',
              },
            ]}
            actions={
              totalBalance > 0 ? (
                <Button
                  size="sm"
                  variant="accent"
                  icon="bi-cash-coin"
                  onClick={() => setActiveTab('fees')}
                >
                  Pay Tuition
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  icon="bi-award"
                  onClick={() => setActiveTab('results')}
                >
                  View Grades
                </Button>
              )
            }
          />

          {/* Quick Actions */}
          <div className="mb-4">
            <QuickActionGrid
              columns={4}
              actions={[
                {
                  icon: 'bi-award-fill',
                  label: 'Exam Results',
                  description: 'Published marks & grades',
                  color: '#002583',
                  onClick: () => setActiveTab('results'),
                },
                {
                  icon: 'bi-calendar3-week',
                  label: 'Class Timetable',
                  description: 'Weekly schedule & periods',
                  color: '#7C3AED',
                  onClick: () => setActiveTab('timetable'),
                },
                {
                  icon: 'bi-calendar2-check-fill',
                  label: 'My Attendance',
                  description: 'Daily roll call history',
                  color: '#059669',
                  onClick: () => setActiveTab('attendance'),
                },
                {
                  icon: 'bi-wallet2',
                  label: 'Tuition Fees',
                  description: 'Online payments & receipts',
                  color: '#D97706',
                  badge: totalBalance > 0 ? `K${totalBalance.toFixed(0)}` : undefined,
                  onClick: () => setActiveTab('fees'),
                },
              ]}
            />
          </div>

          {/* Modern Statistic Cards */}
          <div className="row g-3 mb-4">
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-person-vcard-fill"
                label="Enrolled Class"
                value={student.class_name || '—'}
                variant="blue"
                trend={{
                  text: student.class_teacher_name ? `Teacher: ${student.class_teacher_name}` : 'Enrolled',
                  positive: true,
                }}
                onClick={() => setActiveTab('timetable')}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-calendar2-check-fill"
                label="Term Attendance"
                value={`${attendance.length > 0 ? Math.round((attendance.filter((a: any) => a.status === 'Present' || a.status === 'Late').length / attendance.length) * 100) : 100}%`}
                variant="emerald"
                trend={{
                  text: `${attendance.filter((a: any) => a.status === 'Present').length} Present of ${attendance.length} Days`,
                  positive: true,
                }}
                onClick={() => setActiveTab('attendance')}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-award-fill"
                label="Published Results"
                value={results.length}
                variant="purple"
                trend={{
                  text: results.length > 0 ? `${results.filter((r: any) => (r.marks || 0) >= 50).length} Subjects Passed` : 'Pending Term Exams',
                  positive: results.length > 0,
                }}
                onClick={() => setActiveTab('results')}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-wallet2"
                label="Tuition Balance"
                value={`K${totalBalance.toFixed(2)}`}
                variant={totalBalance > 0 ? 'rose' : 'emerald'}
                trend={{
                  text: totalBalance > 0 ? 'Payment Outstanding' : 'Fees Cleared in Full',
                  positive: totalBalance <= 0,
                }}
                onClick={() => setActiveTab('fees')}
              />
            </div>
          </div>

          {/* Results & Attendance Breakdown Row */}
          <div className="row g-4 mb-4">
            <div className="col-lg-7">
              <Card
                title="Recent Academic Results"
                subtitle="Approved term assessment and examination marks"
                actions={
                  <div className="d-flex gap-2">
                    {data?.terms?.[0]?.id && (
                      <a
                        href={`/student/report-card/${student.id}/${data.terms[0].id}`}
                        target="_blank"
                        rel="noreferrer"
                        className="edu-btn edu-btn-outline edu-btn-sm text-decoration-none"
                      >
                        <i className="bi bi-file-earmark-pdf-fill me-1" /> PDF Report Card
                      </a>
                    )}
                    <Button size="sm" variant="accent" onClick={() => setActiveTab('results')}>
                      All Results
                    </Button>
                  </div>
                }
              >
                {results.length === 0 ? (
                  <div className="text-muted small py-4 text-center">
                    No examination results have been published for this term yet.
                  </div>
                ) : (
                  <DataTable
                    rows={results}
                    columns={[
                      { header: 'Subject', render: (r) => <span className="fw-bold text-dark">{r.subject}</span> },
                      {
                        header: 'Score',
                        render: (r) => (
                          <span className={`fw-bold ${r.marks >= 50 ? 'text-success' : 'text-danger'}`}>
                            {r.marks}%
                          </span>
                        ),
                      },
                      {
                        header: 'Grade',
                        render: (r) => (
                          <Badge variant={r.marks >= 50 ? 'success' : 'danger'}>
                            {r.grade || (r.marks >= 75 ? 'Distinction' : r.marks >= 50 ? 'Credit' : 'Fail')}
                          </Badge>
                        ),
                      },
                    ]}
                  />
                )}
              </Card>
            </div>

            <div className="col-lg-5">
              <Card title="Attendance Summary" subtitle="Term record">
                <DonutChart
                  data={[
                    {
                      label: 'Present',
                      value: attendance.filter((a: any) => a.status === 'Present').length,
                      color: '#10B981',
                    },
                    {
                      label: 'Late',
                      value: attendance.filter((a: any) => a.status === 'Late').length,
                      color: '#F59E0B',
                    },
                    {
                      label: 'Absent',
                      value: attendance.filter((a: any) => a.status === 'Absent').length,
                      color: '#EF4444',
                    },
                    {
                      label: 'Excused',
                      value: attendance.filter((a: any) => a.status === 'Excused' || a.status === 'Sick').length,
                      color: '#3B82F6',
                    },
                  ]}
                  centerValue={`${attendance.length > 0 ? Math.round((attendance.filter((a: any) => a.status === 'Present' || a.status === 'Late').length / attendance.length) * 100) : 100}%`}
                  centerLabel="Present"
                  unit="%"
                />
              </Card>
            </div>
          </div>

          {/* Term Fee Balances Card */}
          <Card
            title="School Fee Statements & Online Checkout"
            subtitle="Secure payment via MTN, Airtel, and Zamtel mobile money"
            actions={
              <Button size="sm" variant="accent" onClick={() => setActiveTab('fees')}>
                Manage Fees
              </Button>
            }
          >
            <DataTable
              rows={feeBalances}
              columns={[
                { header: 'Term', render: (b) => <span className="fw-bold">{b.term_name}</span> },
                {
                  header: 'Balance Due (ZMW)',
                  render: (b) => (
                    <span className="fw-bold" style={{ color: b.balance > 0 ? '#DC2626' : '#059669' }}>
                      K{Number(b.balance || 0).toFixed(2)}
                    </span>
                  ),
                },
                {
                  header: 'Action',
                  render: (b) =>
                    b.balance > 0 ? (
                      <Button
                        size="sm"
                        variant="accent"
                        onClick={() => {
                          setCheckoutTerm(b);
                          setPayAmount(String(b.balance));
                        }}
                      >
                        <i className="bi bi-credit-card-2-front me-1" /> Pay Now
                      </Button>
                    ) : (
                      <Badge variant="success">Cleared</Badge>
                    ),
                },
              ]}
            />
          </Card>
        </>
      )}

      {activeTab === 'fees' && (
        <div className="row g-4">
          <div className="col-lg-5">
            <Card title="Pay School Fees Online (ZMW)">
              <DataTable
                rows={feeBalances}
                columns={[
                  { header: 'Term', render: (b) => <span className="fw-bold">{b.term_name}</span> },
                  { header: 'Balance', render: (b) => `K${Number(b.balance || 0).toFixed(2)}` },
                  {
                    header: 'Checkout',
                    render: (b) =>
                      b.balance > 0 ? (
                        <Button
                          size="sm"
                          variant="accent"
                          onClick={() => {
                            setCheckoutTerm(b);
                            setPayAmount(String(b.balance));
                          }}
                        >
                          Pay Online
                        </Button>
                      ) : (
                        <Badge variant="success">Paid</Badge>
                      ),
                  },
                ]}
              />
            </Card>
          </div>
          <div className="col-lg-7">
            <Card title="My Payment History & Receipts">
              <DataTable
                rows={payments}
                columns={[
                  { header: 'Term', render: (p) => p.term_name },
                  { header: 'Amount', render: (p) => `K${Number(p.amount_paid || 0).toFixed(2)}` },
                  {
                    header: 'Status',
                    render: (p) => (
                      <Badge variant={p.status === 'completed' ? 'success' : 'mustard'}>
                        {p.status}
                      </Badge>
                    ),
                  },
                  {
                    header: 'Receipt',
                    render: (p) =>
                      p.status === 'completed' ? (
                        <Link
                          to={`/admin/receipt/${p.id}`}
                          className="edu-btn edu-btn-outline edu-btn-sm"
                        >
                          {p.reference || 'View Receipt'}
                        </Link>
                      ) : p.lipila_reference_id ? (
                        <Link
                          to={`/billing/status/${p.lipila_reference_id}`}
                          className="edu-btn edu-btn-accent edu-btn-sm"
                        >
                          Simulate / Status
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

      {activeTab === 'timetable' && (
        <Card
          title="My Weekly Class Timetable"
          subtitle={`Class schedule for ${student.class_name || 'Enrolled Class'}`}
        >
          {timetable.length === 0 ? (
            <div className="text-center py-4 text-muted">
              <i className="bi bi-calendar3-week fs-1 mb-2 d-block" />
              <div className="fw-bold">No Scheduled Lessons Found</div>
              <div className="small">Your school timetable for this class has not been published yet.</div>
            </div>
          ) : (
            <div className="d-flex flex-column gap-3">
              {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'].map((day) => {
                const daySlots = timetable.filter((t: any) => t.day.toLowerCase() === day.toLowerCase());
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
                              <div className="small text-secondary">
                                <i className="bi bi-person me-1" /> Teacher: <strong>{slot.teacher_name || 'Assigned Staff'}</strong>
                              </div>
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

      {activeTab === 'attendance' && (
        <>
          <div className="row g-3 mb-4">
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-pie-chart-fill"
                label="Attendance Rate"
                value={`${attendance.rate || 0}%`}
                variant="blue"
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-check-circle-fill"
                label="Days Present"
                value={attendance.present || 0}
                variant="blue"
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-x-circle-fill"
                label="Days Absent"
                value={attendance.absent || 0}
                variant="mustard"
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-calendar-check"
                label="Total Recorded Days"
                value={attendance.total || 0}
              />
            </div>
          </div>

          <Card title="My Attendance History">
            <DataTable
              rows={attendance.records || []}
              columns={[
                { header: 'Date', render: (a: any) => <span className="fw-bold">{a.date}</span> },
                {
                  header: 'Status',
                  render: (a: any) => {
                    let badgeVar: any = 'neutral';
                    if (a.status === 'Present') badgeVar = 'success';
                    else if (a.status === 'Late') badgeVar = 'mustard';
                    else if (a.status === 'Absent') badgeVar = 'danger';
                    else if (a.status === 'Sick') badgeVar = 'mustard';
                    else if (a.status === 'Excused') badgeVar = 'blue';
                    return <Badge variant={badgeVar}>{a.status}</Badge>;
                  },
                },
                { header: 'Remarks', render: (a: any) => a.remarks || '—' },
              ]}
            />
          </Card>
        </>
      )}

      {activeTab === 'results' && (
        <Card
          title="Academic Results & Official Report Card"
          subtitle="View approved marks and download official term report card"
          actions={
            <div className="d-flex align-items-center gap-2">
              <select
                className="edu-select py-1"
                style={{ width: 'auto' }}
                value={selectedReportTerm || (feeBalances[0]?.term_id ? String(feeBalances[0].term_id) : terms[0]?.id ? String(terms[0].id) : '')}
                onChange={(e) => setSelectedReportTerm(e.target.value)}
              >
                {(terms.length > 0 ? terms : feeBalances).map((t: any) => (
                  <option key={t.id || t.term_id} value={t.id || t.term_id}>
                    {t.name || t.term_name}
                  </option>
                ))}
              </select>
              <a
                href={`/student/report-card/${student.id}/${selectedReportTerm || feeBalances[0]?.term_id || terms[0]?.id || 1}`}
                target="_blank"
                rel="noreferrer"
                className="edu-btn edu-btn-accent edu-btn-sm text-decoration-none"
              >
                <i className="bi bi-file-earmark-pdf-fill me-1" /> Download PDF Report Card
              </a>
            </div>
          }
        >
          <DataTable
            rows={results}
            columns={[
              { header: 'Subject', render: (r) => <span className="fw-bold">{r.subject}</span> },
              { header: 'Exam', render: (r) => r.exam },
              { header: 'Score', render: (r) => `${r.marks}%` },
              { header: 'ECZ Grade', render: (r) => <Badge variant="mustard">{r.grade}</Badge> },
            ]}
          />
        </Card>
      )}

      {activeTab === 'assignments' && (
        <Card title="Class Assignments">
          <DataTable
            rows={assignments}
            columns={[
              { header: 'Title', render: (a) => <span className="fw-bold">{a.title}</span> },
              { header: 'Subject', render: (a) => a.subject_name },
              {
                header: 'Status',
                render: (a) => (
                  <Badge variant={a.submitted ? 'success' : 'mustard'}>
                    {a.submitted ? 'Submitted' : 'Pending'}
                  </Badge>
                ),
              },
              {
                header: 'Marks / Feedback',
                render: (a) => (a.marks !== null ? `${a.marks} — ${a.feedback || ''}` : '—'),
              },
            ]}
          />
        </Card>
      )}

      {activeTab === 'materials' && (
        <Card title="Study Materials">
          <DataTable
            rows={materials}
            columns={[
              { header: 'Title', render: (m) => <span className="fw-bold">{m.title}</span> },
              { header: 'Subject', render: (m) => m.subject_name },
              { header: 'Description', render: (m) => m.description },
              {
                header: 'Download',
                render: (m) => (
                  <a
                    href={`/admin/download/${m.filename}`}
                    className="edu-btn edu-btn-primary edu-btn-sm"
                  >
                    <i className="bi bi-download" /> Download
                  </a>
                ),
              },
            ]}
          />
        </Card>
      )}

      {activeTab === 'announcements' && (
        <Card title="School Announcements">
          <DataTable
            rows={announcements}
            columns={[
              {
                header: 'Notice',
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

      {/* Fee Checkout Modal */}
      <Modal
        open={Boolean(checkoutTerm)}
        title={`Pay School Fees — ${checkoutTerm?.term_name || ''}`}
        onClose={() => setCheckoutTerm(null)}
      >
        <form onSubmit={handleFeeCheckout}>
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
              <option value="card">Visa / Mastercard</option>
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
            <Button type="button" variant="outline" onClick={() => setCheckoutTerm(null)}>
              Cancel
            </Button>
            <Button type="submit" variant="accent" disabled={submittingPay}>
              {submittingPay ? 'Initiating...' : 'Proceed to Secure Payment'}
            </Button>
          </div>
        </form>
      </Modal>
    </AppLayout>
  );
};
