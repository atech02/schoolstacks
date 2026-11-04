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

const STUDENT_NAV: NavItem[] = [
  { id: 'dashboard', label: 'My Dashboard', icon: 'bi-grid-1x2-fill' },
  { id: 'fees', label: 'School Fees & Payments', icon: 'bi-wallet2' },
  { id: 'results', label: 'Exam Results & Report Card', icon: 'bi-award-fill' },
  { id: 'assignments', label: 'Assignments', icon: 'bi-journal-text' },
  { id: 'materials', label: 'Study Materials', icon: 'bi-book-half' },
  { id: 'announcements', label: 'Announcements', icon: 'bi-megaphone-fill' },
];

export const StudentPortal: React.FC = () => {
  const navigate = useNavigate();
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
          <div className="row g-3 mb-4">
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-person-vcard-fill"
                label="Class"
                value={student.class_name || '—'}
                variant="blue"
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-wallet2"
                label="Outstanding Fees (ZMW)"
                value={`K${totalBalance.toFixed(2)}`}
                variant="mustard"
                accentTop
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-award-fill"
                label="Published Results"
                value={results.length}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-journal-text"
                label="Class Assignments"
                value={assignments.length}
              />
            </div>
          </div>

          <div className="row g-4">
            <div className="col-lg-6">
              <Card
                title="Term Fee Balances"
                actions={
                  <Button size="sm" variant="accent" onClick={() => setActiveTab('fees')}>
                    Pay Fees Online
                  </Button>
                }
              >
                <DataTable
                  rows={feeBalances}
                  columns={[
                    { header: 'Term', render: (b) => <span className="fw-bold">{b.term_name}</span> },
                    {
                      header: 'Balance (ZMW)',
                      render: (b) => (
                        <span className="fw-bold">K{Number(b.balance || 0).toFixed(2)}</span>
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
                            Pay Now
                          </Button>
                        ) : (
                          <Badge variant="success">Cleared</Badge>
                        ),
                    },
                  ]}
                />
              </Card>
            </div>
            <div className="col-lg-6">
              <Card title="Recent Exam Results">
                <DataTable
                  rows={results}
                  columns={[
                    { header: 'Subject', render: (r) => <span className="fw-bold">{r.subject}</span> },
                    { header: 'Marks', render: (r) => `${r.marks}%` },
                    { header: 'Grade', render: (r) => <Badge variant="mustard">{r.grade}</Badge> },
                  ]}
                />
              </Card>
            </div>
          </div>
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

      {activeTab === 'results' && (
        <Card
          title="Academic Results & Official Report Card"
          actions={
            feeBalances[0] && (
              <a
                href={`/student/report-card/${student.id}/${feeBalances[0].term_id}`}
                target="_blank"
                rel="noreferrer"
                className="edu-btn edu-btn-accent edu-btn-sm"
              >
                <i className="bi bi-file-earmark-pdf" /> Download Term Report Card
              </a>
            )
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
