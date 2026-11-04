import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { apiFetch } from '../services/api';
import { ShaderGradientHero } from '../components/ShaderGradientHero';
import { AlertBanner, Badge, Button, Card, FormField, PasswordInput } from '../components/ui';
import { BrandLogo } from '../components/BrandLogo';

export const LoginPage: React.FC = () => {
  const { schools, school, refreshBootstrap } = useAuth();
  const navigate = useNavigate();

  const [schoolSubdomain, setSchoolSubdomain] = useState(school?.subdomain || '');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await apiFetch<{ user: { role: string } }>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          username,
          password,
          school_subdomain: schoolSubdomain,
        }),
      });
      await refreshBootstrap();
      const role = res.user.role;
      if (role === 'superadmin') navigate('/superadmin');
      else navigate(`/${role}/dashboard`);
    } catch (err: any) {
      setError(err.message || 'Sign in failed.');
    } finally {
      setSubmitting(false);
    }
  };

  const fillDemo = (demoRole: string, demoUser: string, demoPass: string, sub = 'lusakahigh') => {
    setSchoolSubdomain(sub);
    setUsername(demoUser);
    setPassword(demoPass);
  };

  return (
    <div className="min-vh-100 d-flex flex-column flex-lg-row" style={{ background: 'var(--color-cool-gray)' }}>
      {/* Left Welcome Panel with ShaderGradient (#002583, #FFB800, #E5E8EF) */}
      <div
        className="d-none d-lg-flex flex-column justify-content-between p-5 shadergradient-hero-stage"
        style={{ width: '46%', color: '#FFFFFF' }}
      >
        <ShaderGradientHero
          color1="#002583"
          color2="#FFB800"
          color3="#E5E8EF"
          uSpeed={0.14}
          pixelDensity={1.0}
        />
        <div className="hero-readability-scrim" aria-hidden="true" />

        <div style={{ position: 'relative', zIndex: 2 }}>
          <BrandLogo showSlogan={true} theme="light" />
        </div>

        <div style={{ position: 'relative', zIndex: 2, maxWidth: 440 }}>
          <Badge variant="mustard">MULTI-TENANT SCHOOL PORTAL</Badge>
          <h1 className="text-white fw-bold mt-3 mb-2" style={{ fontSize: 'var(--font-size-2xl)', lineHeight: 1.25 }}>
            Welcome Back to Your Digital Campus
          </h1>
          <p style={{ color: 'var(--color-cool-gray)', lineHeight: 1.7 }}>
            Sign in as a School Administrator, Teacher, Student, Parent, or Platform Superadmin.
          </p>
        </div>

        <div className="small" style={{ position: 'relative', zIndex: 2, color: 'var(--color-cool-gray)' }}>
          Secured with school-level tenant isolation &amp; verified online payments
        </div>
      </div>

      {/* Right Clean Login Form Surface */}
      <div className="flex-grow-1 d-flex align-items-center justify-content-center p-3 p-md-5">
        <div className="edu-card p-4 p-md-5 w-100" style={{ maxWidth: 480 }}>
          <div className="d-flex justify-content-between align-items-center mb-2">
            <h2 className="h4 fw-bold mb-0">Sign In</h2>
            <Link to="/" className="small fw-semibold">
              <i className="bi bi-house-door me-1" /> Home
            </Link>
          </div>
          <p className="text-muted small mb-4">
            Select your school (or leave blank for Platform Superadmin)
          </p>

          <AlertBanner variant="danger" message={error} onDismiss={() => setError(null)} />

          <form onSubmit={handleSubmit}>
            <FormField label="School Workspace">
              <select
                className="edu-select"
                value={schoolSubdomain}
                onChange={(e) => setSchoolSubdomain(e.target.value)}
              >
                <option value="">-- Select School (or Superadmin) --</option>
                {schools.map((s) => (
                  <option key={s.id} value={s.subdomain}>
                    {s.name} ({s.subdomain})
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label="Username / Admission No / Staff No">
              <input
                type="text"
                className="edu-input"
                placeholder="e.g. admin, LH001, ST1001, superadmin"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </FormField>

            <FormField label="Password">
              <PasswordInput
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </FormField>

            <Button
              type="submit"
              variant="primary"
              className="w-100 py-2 mt-2"
              disabled={submitting}
              icon="bi-box-arrow-in-right"
            >
              {submitting ? 'Signing in...' : 'Sign In to Portal'}
            </Button>
          </form>

          {/* One-Click Demo Credentials Helper for Local Testing */}
          <div
            className="mt-4 p-3 rounded-3"
            style={{
              background: 'var(--color-cool-gray)',
              border: '1px solid var(--color-border)',
            }}
          >
            <div
              className="small fw-bold mb-2"
              style={{ color: 'var(--color-strong-blue)', fontSize: '0.75rem' }}
            >
              <i className="bi bi-lightning-charge-fill me-1" style={{ color: 'var(--color-mustard)' }} />
              QUICK FILL DEMO ACCOUNTS (LUSAKA HIGH)
            </div>
            <div className="d-flex flex-wrap gap-1">
              <button
                type="button"
                className="edu-btn edu-btn-outline edu-btn-sm"
                onClick={() => fillDemo('admin', 'admin', 'Admin1234', 'lusakahigh')}
              >
                School Admin
              </button>
              <button
                type="button"
                className="edu-btn edu-btn-outline edu-btn-sm"
                onClick={() => fillDemo('parent', 'parent_chanda', 'Parent1234', 'lusakahigh')}
              >
                Parent
              </button>
              <button
                type="button"
                className="edu-btn edu-btn-outline edu-btn-sm"
                onClick={() => fillDemo('student', 'LH001', 'Student1234', 'lusakahigh')}
              >
                Student
              </button>
              <button
                type="button"
                className="edu-btn edu-btn-outline edu-btn-sm"
                onClick={() => fillDemo('teacher', 'ST1001', 'Teacher1234', 'lusakahigh')}
              >
                Teacher
              </button>
              <button
                type="button"
                className="edu-btn edu-btn-accent edu-btn-sm"
                onClick={() => fillDemo('superadmin', 'superadmin', 'SuperAdmin123!', '')}
              >
                Superadmin
              </button>
            </div>
          </div>

          <div className="text-center mt-4 small text-muted">
            Need a new school workspace?{' '}
            <Link to="/register" className="fw-bold">
              Register School (14-Day Free Trial)
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export const RegisterSchoolPage: React.FC = () => {
  const { refreshBootstrap } = useAuth();
  const navigate = useNavigate();

  const [schoolName, setSchoolName] = useState('');
  const [subdomain, setSubdomain] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await apiFetch('/api/onboarding/register', {
        method: 'POST',
        body: JSON.stringify({
          school_name: schoolName,
          subdomain,
          email,
          phone,
          password,
          confirm_password: confirmPassword,
        }),
      });
      await refreshBootstrap();
      navigate('/admin/dashboard');
    } catch (err: any) {
      setError(err.message || 'Could not register school.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="min-vh-100 d-flex align-items-center justify-content-center py-5 px-3"
      style={{ background: 'var(--color-strong-blue)' }}
    >
      <div className="edu-card p-4 p-md-5 w-100" style={{ maxWidth: 560 }}>
        <div className="mb-4 text-center d-flex justify-content-center">
          <BrandLogo showSlogan={true} theme="dark" size="sm" />
        </div>
        <div className="d-flex justify-content-between align-items-center mb-2">
          <h2 className="h4 fw-bold mb-0">Register Your School</h2>
          <Link to="/" className="small fw-semibold">
            <i className="bi bi-arrow-left me-1" /> Back Home
          </Link>
        </div>
        <p className="text-muted small mb-4">
          Start your 14-day free trial. Instant multi-tenant workspace setup.
        </p>

        <AlertBanner variant="danger" message={error} onDismiss={() => setError(null)} />

        <form onSubmit={handleSubmit}>
          <FormField label="School Name">
            <input
              type="text"
              className="edu-input"
              placeholder="e.g. Copperbelt Secondary School"
              value={schoolName}
              onChange={(e) => {
                setSchoolName(e.target.value);
                if (!subdomain) {
                  setSubdomain(
                    e.target.value
                      .toLowerCase()
                      .replace(/[^a-z0-9]+/g, '')
                      .slice(0, 24)
                  );
                }
              }}
              required
            />
          </FormField>

          <FormField
            label="School Portal Identifier (Slug)"
            hint="Lowercase letters, numbers, and hyphens only (3–50 characters)"
          >
            <div className="input-group">
              <span
                className="input-group-text fw-bold small"
                style={{ background: 'var(--color-cool-gray)', color: 'var(--color-strong-blue)' }}
              >
                /s/
              </span>
              <input
                type="text"
                className="edu-input"
                style={{ borderTopLeftRadius: 0, borderBottomLeftRadius: 0 }}
                placeholder="copperbelt"
                value={subdomain}
                onChange={(e) => setSubdomain(e.target.value.toLowerCase())}
                required
              />
            </div>
          </FormField>

          <div className="row g-3">
            <div className="col-md-6">
              <FormField label="Admin Email">
                <input
                  type="email"
                  className="edu-input"
                  placeholder="admin@school.zm"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </FormField>
            </div>
            <div className="col-md-6">
              <FormField label="Mobile Money Phone (ZMW)">
                <input
                  type="text"
                  className="edu-input"
                  placeholder="0977123456"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                />
              </FormField>
            </div>
          </div>

          <div className="row g-3">
            <div className="col-md-6">
              <FormField label="Admin Password">
                <PasswordInput
                  minLength={8}
                  placeholder="Min 8 characters"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </FormField>
            </div>
            <div className="col-md-6">
              <FormField label="Confirm Password">
                <PasswordInput
                  minLength={8}
                  placeholder="Repeat password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                />
              </FormField>
            </div>
          </div>

          <Button
            type="submit"
            variant="accent"
            className="w-100 py-2 mt-2"
            disabled={submitting}
            icon="bi-building-add"
          >
            {submitting ? 'Creating School Workspace...' : 'Create School Portal'}
          </Button>
        </form>

        <div className="text-center mt-4 small text-muted">
          Already registered?{' '}
          <Link to="/login" className="fw-bold">
            Sign in here
          </Link>
        </div>
      </div>
    </div>
  );
};

export const ChangePasswordPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setSubmitting(true);
    try {
      const res = await apiFetch<{ message: string }>('/api/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      });
      setMessage(res.message);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: any) {
      setError(err.message || 'Password update failed.');
    } finally {
      setSubmitting(false);
    }
  };

  const backHref = user?.role === 'superadmin' ? '/superadmin' : `/${user?.role || 'admin'}/dashboard`;

  return (
    <div className="min-vh-100 d-flex align-items-center justify-content-center p-3" style={{ background: 'var(--color-cool-gray)' }}>
      <Card
        title="Change Account Password"
        subtitle="Update your portal password securely"
        className="w-100"
        actions={
          <Button variant="outline" size="sm" onClick={() => navigate(backHref)}>
            Back to Dashboard
          </Button>
        }
      >
        <div style={{ maxWidth: 460 }}>
          <AlertBanner variant="success" message={message} onDismiss={() => setMessage(null)} />
          <AlertBanner variant="danger" message={error} onDismiss={() => setError(null)} />
          <form onSubmit={handleSubmit}>
            <FormField label="Current Password">
              <PasswordInput
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </FormField>
            <FormField label="New Password (min 8 characters)">
              <PasswordInput
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
            </FormField>
            <FormField label="Confirm New Password">
              <PasswordInput
                minLength={8}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
            </FormField>
            <Button type="submit" variant="primary" disabled={submitting} icon="bi-check2-circle">
              {submitting ? 'Updating...' : 'Update Password'}
            </Button>
          </form>
        </div>
      </Card>
    </div>
  );
};
