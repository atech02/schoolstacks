import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { apiFetch } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import {
  AlertBanner,
  Badge,
  Button,
  Card,
  FormField,
  LoadingState,
  Modal,
} from '../components/ui';

/* ── 1. SaaS Subscription Plans & Payment Upgrade Page ── */
export const SubscriptionPlansPage: React.FC = () => {
  const { user, refreshBootstrap } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [cycle, setCycle] = useState<'monthly' | 'yearly'>('monthly');
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<'mobile_money' | 'card'>('mobile_money');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/api/billing/plans');
      setData(res);
      setPhoneNumber(res.school?.phone || '0977123456');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPlans();
  }, [loadPlans]);

  const handleCheckout = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPlan) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiFetch('/api/billing/checkout-subscription', {
        method: 'POST',
        body: JSON.stringify({
          plan: selectedPlan,
          cycle,
          payment_method: paymentMethod,
          phone_number: phoneNumber,
        }),
      });
      setSelectedPlan(null);
      await refreshBootstrap();
      navigate(`/billing/status/${res.reference_id}`);
    } catch (err: any) {
      setError(err.message || 'Checkout failed.');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <LoadingState message="Loading subscription plans..." />;

  const prices = data?.prices || {};
  const school = data?.school;

  return (
    <div className="min-vh-100 py-4 px-3" style={{ background: 'var(--color-cool-gray)' }}>
      <div className="container" style={{ maxWidth: 1180 }}>
        <div className="d-flex justify-content-between align-items-center flex-wrap gap-3 mb-4">
          <div>
            <div className="d-flex align-items-center gap-2 mb-1">
              <Badge variant="blue">{school?.name || 'School Billing'}</Badge>
              {data?.simulator_mode && (
                <Badge variant="mustard">
                  <i className="bi bi-cpu" /> Payment Sandbox Simulator Active
                </Badge>
              )}
            </div>
            <h1 className="h3 fw-bold mb-0">School Subscription Plans (ZMW)</h1>
          </div>
          <Button
            variant="outline"
            icon="bi-arrow-left"
            onClick={() => navigate(`/${user?.role || 'admin'}/dashboard`)}
          >
            Back to Portal
          </Button>
        </div>

        <AlertBanner variant="danger" message={error} onDismiss={() => setError(null)} />

        {/* Billing Cycle Toggle */}
        <div className="d-flex justify-content-center mb-4">
          <div
            className="d-inline-flex p-1 rounded-pill"
            style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
          >
            <button
              type="button"
              className={`edu-btn edu-btn-sm rounded-pill ${
                cycle === 'monthly' ? 'edu-btn-primary' : ''
              }`}
              onClick={() => setCycle('monthly')}
            >
              Monthly Billing
            </button>
            <button
              type="button"
              className={`edu-btn edu-btn-sm rounded-pill ${
                cycle === 'yearly' ? 'edu-btn-accent' : ''
              }`}
              onClick={() => setCycle('yearly')}
            >
              Annual Billing (Save 2 Months)
            </button>
          </div>
        </div>

        <div className="row g-4 mb-5">
          {(['free', 'starter', 'growth', 'enterprise'] as const).map((planKey) => {
            const p = prices[planKey];
            if (!p) return null;
            const isCurrent = school?.plan === planKey;
            const amount = cycle === 'yearly' ? p.amount_yearly : p.amount_monthly;
            return (
              <div className="col-md-6 col-lg-3" key={planKey}>
                <div
                  className="edu-card h-100 p-4 d-flex flex-column"
                  style={{
                    borderTop: isCurrent
                      ? '4px solid var(--color-mustard)'
                      : '4px solid var(--color-strong-blue)',
                  }}
                >
                  <div className="d-flex justify-content-between align-items-center mb-2">
                    <span className="fw-bold text-uppercase small">{p.name}</span>
                    {isCurrent && <Badge variant="mustard">Current Plan</Badge>}
                  </div>
                  <div className="my-3">
                    <span
                      className="fw-bold"
                      style={{ fontSize: '24px', color: 'var(--color-strong-blue)' }}
                    >
                      K{amount}
                    </span>
                    <span className="text-muted small">/{cycle === 'yearly' ? 'year' : 'month'}</span>
                  </div>
                  <ul className="list-unstyled small text-muted flex-grow-1 mb-4">
                    {(data?.features?.[planKey] || []).map((f: string, idx: number) => (
                      <li key={idx} className="mb-2 d-flex gap-2">
                        <i
                          className="bi bi-check-circle-fill"
                          style={{ color: 'var(--color-mustard)' }}
                        />
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>
                  {planKey === 'free' ? (
                    <Button variant="outline" disabled className="w-100">
                      14-Day Trial Tier
                    </Button>
                  ) : (
                    <Button
                      variant={planKey === 'growth' ? 'accent' : 'primary'}
                      className="w-100"
                      onClick={() => setSelectedPlan(planKey)}
                    >
                      {isCurrent ? 'Renew Plan' : `Upgrade to ${p.name}`}
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Subscription Payment History */}
        <Card title="Subscription Payment History">
          {!data?.subscriptions?.length ? (
            <div className="text-muted small">No subscription transactions recorded yet.</div>
          ) : (
            <div className="edu-table-wrap">
              <table className="edu-table">
                <thead>
                  <tr>
                    <th>Reference</th>
                    <th>Plan</th>
                    <th>Cycle</th>
                    <th>Amount</th>
                    <th>Method</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {data.subscriptions.map((s: any) => (
                    <tr key={s.id}>
                      <td className="fw-semibold">{s.lipila_reference_id || '—'}</td>
                      <td className="text-capitalize fw-bold">{s.plan}</td>
                      <td className="text-capitalize">{s.billing_cycle}</td>
                      <td>
                        {s.currency} K{Number(s.amount || 0).toFixed(2)}
                      </td>
                      <td className="text-capitalize">{(s.payment_method || '').replace('_', ' ')}</td>
                      <td>
                        <Badge
                          variant={
                            s.status === 'active' || s.status === 'completed'
                              ? 'success'
                              : s.status === 'failed'
                              ? 'danger'
                              : 'mustard'
                          }
                        >
                          {s.status}
                        </Badge>
                      </td>
                      <td>
                        {s.lipila_reference_id && (
                          <Link
                            to={`/billing/status/${s.lipila_reference_id}`}
                            className="edu-btn edu-btn-outline edu-btn-sm"
                          >
                            View Status
                          </Link>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Subscription Checkout Modal */}
        <Modal
          open={Boolean(selectedPlan)}
          title={`Checkout — ${selectedPlan?.toUpperCase()} Plan (${cycle})`}
          onClose={() => setSelectedPlan(null)}
        >
          <form onSubmit={handleCheckout}>
            <FormField label="Payment Method">
              <div className="d-flex gap-2">
                <button
                  type="button"
                  className={`edu-btn flex-fill ${
                    paymentMethod === 'mobile_money' ? 'edu-btn-primary' : 'edu-btn-outline'
                  }`}
                  onClick={() => setPaymentMethod('mobile_money')}
                >
                  <i className="bi bi-phone" /> Mobile Money (MTN/Airtel/Zamtel)
                </button>
                <button
                  type="button"
                  className={`edu-btn flex-fill ${
                    paymentMethod === 'card' ? 'edu-btn-primary' : 'edu-btn-outline'
                  }`}
                  onClick={() => setPaymentMethod('card')}
                >
                  <i className="bi bi-credit-card" /> Bank Card
                </button>
              </div>
            </FormField>

            <FormField
              label="Zambian Mobile Money / Contact Number"
              hint="Format: 0977..., 0966..., 0955... or 260..."
            >
              <input
                type="text"
                className="edu-input"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                required
              />
            </FormField>

            <div className="d-flex justify-content-end gap-2 mt-4">
              <Button type="button" variant="outline" onClick={() => setSelectedPlan(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="accent" disabled={submitting} icon="bi-shield-check">
                {submitting ? 'Processing...' : 'Proceed to Secure Checkout'}
              </Button>
            </div>
          </form>
        </Modal>
      </div>
    </div>
  );
};

/* ── 2. Transaction Status & Built-in Sandbox Simulator Page ── */
export const PaymentStatusAndSimulatorPage: React.FC = () => {
  const { referenceId } = useParams<{ referenceId: string }>();
  const { user, refreshBootstrap } = useAuth();
  const navigate = useNavigate();
  const [tx, setTx] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    if (!referenceId) return;
    setLoading(true);
    try {
      const res = await apiFetch(`/api/billing/status/${referenceId}`);
      setTx(res);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [referenceId]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const triggerSandbox = async (action: 'approve' | 'decline') => {
    if (!referenceId) return;
    setActing(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/billing/sandbox/${referenceId}`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      });
      setTx(res);
      await refreshBootstrap();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActing(false);
    }
  };

  if (loading) return <LoadingState message="Verifying payment transaction status..." />;

  const isSuccess = tx?.status === 'completed' || tx?.status === 'active';
  const isFailed = tx?.status === 'failed';

  return (
    <div className="min-vh-100 py-5 px-3" style={{ background: 'var(--color-cool-gray)' }}>
      <div className="container" style={{ maxWidth: 680 }}>
        <Card
          title="Payment Verification & Status"
          subtitle={`Reference: ${referenceId}`}
          actions={
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate(`/${user?.role || 'admin'}/dashboard`)}
            >
              Dashboard
            </Button>
          }
        >
          <AlertBanner variant="danger" message={error} onDismiss={() => setError(null)} />

          {tx && (
            <>
              <div
                className="p-4 rounded-3 mb-4 text-center"
                style={{
                  background: isSuccess
                    ? '#DCFCE7'
                    : isFailed
                    ? '#FEE2E2'
                    : 'rgba(255, 184, 0, 0.16)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div className="fs-1 mb-2">
                  {isSuccess ? (
                    <i className="bi bi-check-circle-fill text-success" />
                  ) : isFailed ? (
                    <i className="bi bi-x-circle-fill text-danger" />
                  ) : (
                    <i
                      className="bi bi-hourglass-split"
                      style={{ color: 'var(--color-strong-blue)' }}
                    />
                  )}
                </div>
                <h4 className="fw-bold mb-1">
                  {isSuccess
                    ? 'Payment Confirmed!'
                    : isFailed
                    ? 'Payment Declined / Failed'
                    : 'Awaiting Payment Confirmation'}
                </h4>
                <div className="small text-muted">
                  Amount: <strong>K{Number(tx.amount || 0).toFixed(2)} ZMW</strong> &bull; Method:{' '}
                  <strong className="text-capitalize">
                    {(tx.payment_method || '').replace('_', ' ')}
                  </strong>
                </div>
                {tx.receipt_ref && (
                  <div className="mt-2">
                    <Badge variant="mustard">Official Receipt: {tx.receipt_ref}</Badge>
                  </div>
                )}
              </div>

              {/* Built-in Sandbox Simulator Controls when in Test/Simulator mode */}
              {tx.is_sandbox && tx.status === 'pending' && (
                <div
                  className="p-4 rounded-3 mb-4"
                  style={{
                    background: 'var(--color-cool-gray)',
                    border: '2px solid var(--color-mustard)',
                  }}
                >
                  <div className="d-flex align-items-center justify-content-between mb-2">
                    <span className="fw-bold" style={{ color: 'var(--color-strong-blue)' }}>
                      <i className="bi bi-cpu-fill me-2" style={{ color: 'var(--color-mustard)' }} />
                      Payment Sandbox Simulator (Test Mode)
                    </span>
                    <Badge variant="mustard">Development Only</Badge>
                  </div>
                  <p className="small text-muted mb-3">
                    Test Mode: Simulate the mobile money PIN approval or card 3DS authorization
                    below:
                  </p>
                  <div className="d-flex flex-wrap gap-2">
                    <Button
                      variant="accent"
                      icon="bi-check2-circle"
                      disabled={acting}
                      onClick={() => triggerSandbox('approve')}
                    >
                      Simulate Approved Payment
                    </Button>
                    <Button
                      variant="danger"
                      icon="bi-x-circle"
                      disabled={acting}
                      onClick={() => triggerSandbox('decline')}
                    >
                      Simulate Declined Payment
                    </Button>
                    <Button
                      variant="outline"
                      icon="bi-arrow-clockwise"
                      disabled={acting}
                      onClick={fetchStatus}
                    >
                      Refresh Status
                    </Button>
                  </div>
                </div>
              )}

              <div className="d-flex justify-content-between align-items-center flex-wrap gap-2">
                {tx.receipt_id && (
                  <Link
                    to={`/admin/receipt/${tx.receipt_id}`}
                    className="edu-btn edu-btn-accent"
                  >
                    <i className="bi bi-receipt" /> View Official Receipt ({tx.receipt_ref})
                  </Link>
                )}
                <Button
                  variant="primary"
                  onClick={() => navigate(`/${user?.role || 'admin'}/dashboard`)}
                >
                  Return to Portal
                </Button>
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
};

/* ── 3. Official Printable Fee Receipt Page (RCT-xxxxx) ── */
export const ReceiptPage: React.FC = () => {
  const { paymentId } = useParams<{ paymentId: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [rcpt, setRcpt] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch(`/api/billing/receipt/${paymentId}`)
      .then(setRcpt)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [paymentId]);

  if (loading) return <LoadingState message="Loading official receipt..." />;

  return (
    <div className="min-vh-100 py-5 px-3" style={{ background: 'var(--color-cool-gray)' }}>
      <div className="container" style={{ maxWidth: 680 }}>
        <AlertBanner variant="danger" message={error} />
        {rcpt && (
          <div className="edu-card p-4 p-md-5">
            <div className="d-flex justify-content-between align-items-start border-bottom pb-4 mb-4">
              <div>
                <h2 className="h4 fw-bold mb-1">{rcpt.school?.name || 'School Receipt'}</h2>
                <div className="small text-muted">{rcpt.school?.email}</div>
                {rcpt.is_sandbox_simulated && (
                  <div className="mt-2">
                    <Badge variant="mustard">SANDBOX TEST RECEIPT</Badge>
                  </div>
                )}
              </div>
              <div className="text-end">
                <div
                  className="fw-bold"
                  style={{ color: 'var(--color-strong-blue)', fontSize: 'var(--font-size-lg)' }}
                >
                  {rcpt.reference}
                </div>
                <div className="small text-muted">
                  {rcpt.payment_date ? new Date(rcpt.payment_date).toLocaleDateString() : ''}
                </div>
              </div>
            </div>

            <div className="row g-3 mb-4">
              <div className="col-sm-6">
                <div className="small text-muted">Student</div>
                <div className="fw-bold">
                  {rcpt.student?.first_name} {rcpt.student?.last_name} ({rcpt.student?.admission_no})
                </div>
                <div className="small text-muted">Class: {rcpt.student?.class_name}</div>
              </div>
              <div className="col-sm-6 text-sm-end">
                <div className="small text-muted">Academic Term</div>
                <div className="fw-bold">{rcpt.term_name}</div>
                <div className="small text-muted text-capitalize">
                  Method: {(rcpt.payment_method || '').replace('_', ' ')}
                </div>
              </div>
            </div>

            <div
              className="p-4 rounded-3 mb-4 d-flex justify-content-between align-items-center"
              style={{
                background: 'var(--color-cool-gray)',
                borderLeft: '4px solid var(--color-mustard)',
              }}
            >
              <div>
                <div className="small text-muted fw-semibold">Amount Paid (Verified)</div>
                <div
                  className="fw-bold"
                  style={{ color: 'var(--color-strong-blue)', fontSize: '22px' }}
                >
                  {rcpt.currency} K{Number(rcpt.amount_paid || 0).toFixed(2)}
                </div>
              </div>
              <div className="text-end">
                <div className="small text-muted">Remaining Term Balance</div>
                <div className="fw-bold">K{Number(rcpt.remaining_balance || 0).toFixed(2)}</div>
              </div>
            </div>

            <div className="d-flex justify-content-between flex-wrap gap-2">
              <Button
                variant="outline"
                icon="bi-arrow-left"
                onClick={() => navigate(`/${user?.role || 'admin'}/dashboard`)}
              >
                Back to Dashboard
              </Button>
              <Button variant="primary" icon="bi-printer" onClick={() => window.print()}>
                Print Official Receipt
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
