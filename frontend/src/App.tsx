import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { LoadingState } from './components/ui';
import { LandingPage } from './pages/LandingPage';
import { LoginPage, RegisterSchoolPage, ChangePasswordPage } from './pages/AuthPages';
import { AdminPortal } from './pages/AdminPortal';
import { TeacherPortal } from './pages/TeacherPortal';
import { StudentPortal } from './pages/StudentPortal';
import { ParentPortal } from './pages/ParentPortal';
import {
  SubscriptionPlansPage,
  PaymentStatusAndSimulatorPage,
  ReceiptPage,
} from './pages/BillingPages';
import { SuperadminPortal } from './pages/SuperadminPortal';

const ProtectedRoute: React.FC<{
  allowedRoles?: string[];
  children: React.ReactElement;
}> = ({ allowedRoles, children }) => {
  const { loading, authenticated, user } = useAuth();
  if (loading) return <LoadingState />;
  if (!authenticated || !user) return <Navigate to="/login" replace />;
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    const fallback = user.role === 'superadmin' ? '/superadmin' : `/${user.role}/dashboard`;
    return <Navigate to={fallback} replace />;
  }
  return children;
};

const PortalRedirect: React.FC = () => {
  const { loading, authenticated, user } = useAuth();
  if (loading) return <LoadingState />;
  if (!authenticated || !user) return <Navigate to="/login" replace />;
  if (user.role === 'superadmin') return <Navigate to="/superadmin" replace />;
  return <Navigate to={`/${user.role}/dashboard`} replace />;
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public & Auth Routes */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/pricing" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterSchoolPage />} />
          <Route path="/portal" element={<PortalRedirect />} />
          <Route
            path="/change-password"
            element={
              <ProtectedRoute>
                <ChangePasswordPage />
              </ProtectedRoute>
            }
          />

          {/* School Admin Portal */}
          <Route
            path="/admin/*"
            element={
              <ProtectedRoute allowedRoles={['admin', 'superadmin']}>
                <AdminPortal />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/receipt/:paymentId"
            element={
              <ProtectedRoute>
                <ReceiptPage />
              </ProtectedRoute>
            }
          />

          {/* Teacher Portal */}
          <Route
            path="/teacher/*"
            element={
              <ProtectedRoute allowedRoles={['teacher', 'admin']}>
                <TeacherPortal />
              </ProtectedRoute>
            }
          />

          {/* Student Portal */}
          <Route
            path="/student/*"
            element={
              <ProtectedRoute allowedRoles={['student', 'admin']}>
                <StudentPortal />
              </ProtectedRoute>
            }
          />

          {/* Parent Portal */}
          <Route
            path="/parent/*"
            element={
              <ProtectedRoute allowedRoles={['parent', 'admin']}>
                <ParentPortal />
              </ProtectedRoute>
            }
          />

          {/* Billing, Checkout Status & Sandbox Simulator */}
          <Route
            path="/billing/plans"
            element={
              <ProtectedRoute>
                <SubscriptionPlansPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/billing/expired"
            element={
              <ProtectedRoute>
                <SubscriptionPlansPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/billing/status/:referenceId"
            element={
              <ProtectedRoute>
                <PaymentStatusAndSimulatorPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/billing/sandbox/:referenceId"
            element={
              <ProtectedRoute>
                <PaymentStatusAndSimulatorPage />
              </ProtectedRoute>
            }
          />

          {/* Superadmin Console */}
          <Route
            path="/superadmin/*"
            element={
              <ProtectedRoute allowedRoles={['superadmin']}>
                <SuperadminPortal />
              </ProtectedRoute>
            }
          />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
};

export default App;
