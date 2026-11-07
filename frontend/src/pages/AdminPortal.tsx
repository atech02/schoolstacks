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
  ConfirmDialog,
  DataTable,
  FormField,
  LoadingState,
  Modal,
  PasswordInput,
  StatCard,
} from '../components/ui';
import {
  DashboardHeader,
  StatisticCard as ModernStatCard,
  DonutChart,
  HorizontalBarChart,
  QuickActionGrid,
} from '../components/dashboard';

const ADMIN_NAV: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard & Analytics', icon: 'bi-grid-1x2-fill', section: 'CORE MANAGEMENT' },
  { id: 'students', label: 'Students', icon: 'bi-mortarboard-fill', section: 'CORE MANAGEMENT' },
  { id: 'teachers', label: 'Teachers', icon: 'bi-person-badge-fill', section: 'CORE MANAGEMENT' },
  { id: 'class-teachers', label: 'Class Teacher Allocation', icon: 'bi-person-check-fill', section: 'CORE MANAGEMENT' },
  { id: 'parents', label: 'Parents', icon: 'bi-people-fill', section: 'CORE MANAGEMENT' },
  { id: 'academics', label: 'Classes, Subjects & Terms', icon: 'bi-layers-fill', section: 'ACADEMIC ENGINE' },
  { id: 'attendance', label: 'Attendance', icon: 'bi-calendar2-check-fill', section: 'ACADEMIC ENGINE' },
  { id: 'approvals', label: 'Results & Approvals', icon: 'bi-check2-circle', section: 'ACADEMIC ENGINE' },
  { id: 'report-cards', label: 'Report Cards', icon: 'bi-file-earmark-pdf-fill', section: 'ACADEMIC ENGINE' },
  { id: 'timetable', label: 'Timetable', icon: 'bi-calendar3-week', section: 'ACADEMIC ENGINE' },
  { id: 'sms', label: 'SMS & Parent Communication', icon: 'bi-chat-dots-fill', section: 'COMMUNICATION & FINANCE' },
  { id: 'fees', label: 'Fees & Online Payments', icon: 'bi-cash-coin', section: 'COMMUNICATION & FINANCE' },
  { id: 'announcements', label: 'Announcements', icon: 'bi-megaphone-fill', section: 'COMMUNICATION & FINANCE' },
  { id: 'settings', label: 'School Settings', icon: 'bi-gear-fill', section: 'SYSTEM' },
];

/**
 * Validates Zambian phone numbers. Strips spaces, dashes, dots and parentheses.
 * Validates format ^(\+?260|0)[79]\d{8}$
 */
export function validateZambianPhone(
  phone: string,
  required: boolean = true
): { valid: boolean; error?: string; normalized: string } {
  if (!phone || !phone.trim()) {
    if (required) {
      return { valid: false, error: 'Phone number is required.', normalized: '' };
    }
    return { valid: true, normalized: '' };
  }
  const cleaned = phone.replace(/[\s\-\.\(\)]/g, '');
  const zambiaRegex = /^(\+?260|0)[79]\d{8}$/;
  if (zambiaRegex.test(cleaned)) {
    const normalized = cleaned.startsWith('+260') ? '0' + cleaned.slice(4) : cleaned;
    return { valid: true, normalized };
  }
  if (/^260[79]\d{8}$/.test(cleaned)) {
    return { valid: true, normalized: '0' + cleaned.slice(3) };
  }
  if (/^[79]\d{8}$/.test(cleaned)) {
    return { valid: true, normalized: '0' + cleaned };
  }
  return {
    valid: false,
    error: 'Invalid phone number. Please enter the number without spaces, for example 0977123456.',
    normalized: cleaned,
  };
}

export const AdminPortal: React.FC = () => {
  const navigate = useNavigate();
  const { user, school } = useAuth();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ── Register Modals & States ──
  const [studentModalOpen, setStudentModalOpen] = useState(false);
  const [teacherModalOpen, setTeacherModalOpen] = useState(false);
  const [payModalStudent, setPayModalStudent] = useState<any>(null);

  // ── Form Input Errors (Inline Feedback) ──
  const [teacherPhoneError, setTeacherPhoneError] = useState<string | null>(null);
  const [studentPhoneError, setStudentPhoneError] = useState<string | null>(null);
  const [parentPhoneError, setParentPhoneError] = useState<string | null>(null);
  const [editTeacherPhoneError, setEditTeacherPhoneError] = useState<string | null>(null);
  const [editStudentPhoneError, setEditStudentPhoneError] = useState<string | null>(null);
  const [editParentPhoneError, setEditParentPhoneError] = useState<string | null>(null);

  // ── Student Forms ──
  const [stuForm, setStuForm] = useState({
    first_name: '',
    last_name: '',
    admission_no: '',
    gender: 'Female',
    class_id: '',
    phone: '',
    parent_username: '',
    parent_phone: '',
  });

  const [studentToEdit, setStudentToEdit] = useState<any | null>(null);
  const [studentToDelete, setStudentToDelete] = useState<any | null>(null);
  const [studentFilterClass, setStudentFilterClass] = useState<string>('');
  const [studentFilterStatus, setStudentFilterStatus] = useState<string>('');

  // ── Teacher Forms ──
  const [teaForm, setTeaForm] = useState({
    first_name: '',
    last_name: '',
    phone: '',
    email: '',
    subject_specialization: '',
  });

  const [teacherToEdit, setTeacherToEdit] = useState<any | null>(null);
  const [teacherToToggle, setTeacherToToggle] = useState<any | null>(null);
  const [teacherToDelete, setTeacherToDelete] = useState<any | null>(null);

  // ── Academics Forms (Classes, Subjects, Terms, Exams) ──
  const [classForm, setClassForm] = useState({
    name: '',
    capacity: '40',
    grade_level: '',
    academic_year: new Date().getFullYear().toString(),
    class_teacher_id: '',
  });
  const [classToEdit, setClassToEdit] = useState<any | null>(null);
  const [classToDelete, setClassToDelete] = useState<any | null>(null);

  const [subjForm, setSubjForm] = useState({ name: '', code: '', description: '' });
  const [subjectToEdit, setSubjectToEdit] = useState<any | null>(null);
  const [subjectToDelete, setSubjectToDelete] = useState<any | null>(null);

  const [termForm, setTermForm] = useState({ name: '', start_date: '', end_date: '' });
  const [termToEdit, setTermToEdit] = useState<any | null>(null);
  const [termToDelete, setTermToDelete] = useState<any | null>(null);

  const [examForm, setExamForm] = useState({
    name: '',
    term_id: '',
    class_id: '',
    subject_id: '',
    date: '',
    start_date: '',
    end_date: '',
    start_time: '09:00',
    end_time: '11:00',
    venue: '',
    exam_type: 'Main',
  });
  const [examToEdit, setExamToEdit] = useState<any | null>(null);
  const [examToDelete, setExamToDelete] = useState<any | null>(null);

  // ── Parent Management ──
  const [parentModalOpen, setParentModalOpen] = useState(false);
  const [parentForm, setParentForm] = useState({
    first_name: '',
    last_name: '',
    phone: '',
    email: '',
    username: '',
    password: 'parent123',
    student_id: '',
  });
  const [linkModalParent, setLinkModalParent] = useState<any | null>(null);
  const [linkStudentId, setLinkStudentId] = useState('');
  const [resetPassParent, setResetPassParent] = useState<any | null>(null);
  const [newParentPass, setNewParentPass] = useState('parent123');

  // ── Fees & Payments ──
  const [feeForm, setFeeForm] = useState({ class_id: '', term_id: '', amount: '' });
  const [manualPayForm, setManualPayForm] = useState({
    term_id: '',
    amount: '',
    bank_reference: '',
    payment_date: new Date().toISOString().slice(0, 10),
  });

  // ── Timetable ──
  const [ttForm, setTtForm] = useState({
    class_id: '',
    subject_id: '',
    teacher_id: '',
    day: 'Monday',
    start_time: '08:00',
    end_time: '09:00',
    room: '',
    term_id: '',
  });
  const [timetableToEdit, setTimetableToEdit] = useState<any | null>(null);
  const [timetableToDelete, setTimetableToDelete] = useState<any | null>(null);
  const [timetableClashError, setTimetableClashError] = useState<string | null>(null);

  // ── Announcements ──
  const [annForm, setAnnForm] = useState({ title: '', content: '', class_id: '' });

  // ── Attendance Tab State ──
  const [attDate, setAttDate] = useState(new Date().toISOString().slice(0, 10));
  const [attClassId, setAttClassId] = useState('');
  const [attOverview, setAttOverview] = useState<any | null>(null);
  const [attLoading, setAttLoading] = useState(false);
  const [attCorrectStudent, setAttCorrectStudent] = useState<any | null>(null);
  const [attCorrectStatus, setAttCorrectStatus] = useState('Present');
  const [attCorrectRemarks, setAttCorrectRemarks] = useState('');
  const [attCorrectReason, setAttCorrectReason] = useState('');

  // ── Class Teacher Allocation Tab State ──
  const [ctData, setCtData] = useState<any>(null);
  const [ctLoading, setCtLoading] = useState(false);
  const [assignCtModal, setAssignCtModal] = useState<any>(null);
  const [subsData, setSubsData] = useState<any[]>([]);
  const [assignSubModal, setAssignSubModal] = useState<any>(null);

  // ── SMS & Parent Communication Tab State ──
  const [smsSettings, setSmsSettings] = useState<any>(null);
  const [smsHistory, setSmsHistory] = useState<any>(null);
  const [smsBalance, setSmsBalance] = useState<any>(null);
  const [smsLoading, setSmsLoading] = useState(false);
  const [smsSubTab, setSmsSubTab] = useState<'settings' | 'reminders' | 'absenteeism' | 'history'>('settings');
  const [testSmsModal, setTestSmsModal] = useState<any>(null);
  const [feeRemindersPreview, setFeeRemindersPreview] = useState<any>(null);
  const [feeRemindersLoading, setFeeRemindersLoading] = useState(false);
  const [absenteeismPreview, setAbsenteeismPreview] = useState<any>(null);
  const [absenteeismLoading, setAbsenteeismLoading] = useState(false);

  // ── Call Parent Modal State ──
  const [callModal, setCallModal] = useState<{
    studentId?: number;
    studentName?: string;
    className?: string;
    parentId?: number;
    parentName?: string;
    phone?: string;
    reason?: string;
    outcome?: string;
    remarks?: string;
    calls?: any[];
    loading?: boolean;
  } | null>(null);

  // ── Results & Approvals Tab State ──
  const [pendingApprovals, setPendingApprovals] = useState<any[]>([]);
  const [resOverview, setResOverview] = useState<any | null>(null);
  const [resExamFilter, setResExamFilter] = useState('');
  const [resClassFilter, setResClassFilter] = useState('');
  const [resSubjFilter, setResSubjFilter] = useState('');
  const [approvalsLoading, setApprovalsLoading] = useState(false);

  // ── Report Cards Tab State ──
  const [rcClassId, setRcClassId] = useState('');
  const [rcTermId, setRcTermId] = useState('');
  const [rcData, setRcData] = useState<any | null>(null);
  const [rcLoading, setRcLoading] = useState(false);

  // ── School Settings Tab State ──
  const [settingsForm, setSettingsForm] = useState({
    name: '',
    phone: '',
    address: '',
    logo_url: '',
    currency: 'ZMW',
  });
  const [settingsLoading, setSettingsLoading] = useState(false);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/api/admin/overview');
      setData(res);
    } catch (err: any) {
      if (err.subscriptionExpired) {
        navigate('/billing/plans');
        return;
      }
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const handleAction = async (
    path: string,
    body: any,
    onDone?: () => void,
    method: 'POST' | 'PUT' | 'DELETE' = 'POST'
  ) => {
    setError(null);
    setMessage(null);
    setTimetableClashError(null);
    try {
      const res = await apiFetch(path, {
        method,
        body: method === 'DELETE' ? undefined : JSON.stringify(body),
      });
      setMessage(res.message || 'Action completed successfully.');
      if (onDone) onDone();
      await loadOverview();
    } catch (err: any) {
      setError(err.message);
      if (path.includes('/timetable')) {
        setTimetableClashError(err.message);
      }
    }
  };

  const loadClassTeachers = useCallback(async () => {
    setCtLoading(true);
    try {
      const res = await apiFetch('/api/admin/class-teachers');
      setCtData(res);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setCtLoading(false);
    }
  }, []);

  const loadSubstitutes = useCallback(async () => {
    try {
      const res = await apiFetch('/api/admin/substitutes');
      setSubsData(res.substitutes || []);
    } catch (err: any) {
      console.error('Error loading substitutes:', err);
    }
  }, []);

  const loadSmsSettings = useCallback(async () => {
    setSmsLoading(true);
    try {
      const res = await apiFetch('/api/admin/sms/settings');
      setSmsSettings(res);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSmsLoading(false);
    }
  }, []);

  const loadSmsHistory = useCallback(async () => {
    try {
      const res = await apiFetch('/api/admin/sms/history');
      setSmsHistory(res);
    } catch (err: any) {
      console.error('Error loading SMS history:', err);
    }
  }, []);

  const loadSmsBalance = useCallback(async (refresh = false) => {
    try {
      const res = await apiFetch(`/api/admin/sms/balance${refresh ? '?refresh=true' : ''}`);
      setSmsBalance(res);
    } catch (err: any) {
      console.error('Error loading SMS balance:', err);
    }
  }, []);

  const loadFeeReminders = async () => {
    setFeeRemindersLoading(true);
    try {
      const res = await apiFetch('/api/admin/sms/fee-reminders/preview');
      setFeeRemindersPreview(res);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setFeeRemindersLoading(false);
    }
  };

  const loadAbsenteeism = async () => {
    setAbsenteeismLoading(true);
    try {
      const res = await apiFetch('/api/admin/sms/absenteeism/preview');
      setAbsenteeismPreview(res);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setAbsenteeismLoading(false);
    }
  };

  const openCallParent = async (student: any) => {
    const parentPhone = student.guardian_phone || student.parent_phone || '';
    setCallModal({
      studentId: student.id || student.student_id,
      studentName: student.name || student.student_name,
      className: student.class_name,
      parentId: student.parent_id,
      parentName: student.parent_name || 'Primary Guardian',
      phone: parentPhone,
      reason: 'Absenteeism Follow-up',
      outcome: 'Answered',
      remarks: '',
      calls: [],
      loading: true,
    });
    try {
      const sId = student.id || student.student_id;
      const res = await apiFetch(`/api/admin/calls?student_id=${sId}`);
      setCallModal((prev) => (prev ? { ...prev, calls: res.calls || [], loading: false } : null));
    } catch {
      setCallModal((prev) => (prev ? { ...prev, loading: false } : null));
    }
  };

  const handleLogCall = async () => {
    if (!callModal) return;
    try {
      await apiFetch('/api/admin/calls', {
        method: 'POST',
        body: JSON.stringify({
          student_id: callModal.studentId,
          parent_id: callModal.parentId,
          phone_called: callModal.phone,
          reason: callModal.reason,
          outcome: callModal.outcome,
          remarks: callModal.remarks,
        }),
      });
      setMessage('Parent call logged successfully.');
      setCallModal(null);
    } catch (err: any) {
      setError(err.message);
    }
  };

  // ── Extended Loaders for SMS Role Workflows ──
  const loadAttendance = useCallback(async (date?: string, classId?: string) => {
    setAttLoading(true);
    try {
      const qDate = date || attDate;
      const qClass = classId !== undefined ? classId : attClassId;
      const url = `/api/admin/attendance/overview?date=${encodeURIComponent(qDate)}${qClass ? `&class_id=${qClass}` : ''}`;
      const res = await apiFetch(url);
      setAttOverview(res);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setAttLoading(false);
    }
  }, [attDate, attClassId]);

  const loadApprovals = useCallback(async () => {
    setApprovalsLoading(true);
    try {
      const res = await apiFetch('/api/admin/results/pending');
      setPendingApprovals(res.pending_batches || []);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setApprovalsLoading(false);
    }
  }, []);

  const loadResultsOverview = useCallback(async (examId?: string, classId?: string, subjId?: string) => {
    try {
      let url = '/api/admin/results/overview?';
      if (examId) url += `exam_id=${examId}&`;
      if (classId) url += `class_id=${classId}&`;
      if (subjId) url += `subject_id=${subjId}&`;
      const res = await apiFetch(url);
      setResOverview(res);
    } catch (err: any) {
      setError(err.message);
    }
  }, []);

  const loadReportCards = useCallback(async (cId?: string, tId?: string) => {
    setRcLoading(true);
    try {
      let url = '/api/admin/report-cards?';
      if (cId) url += `class_id=${cId}&`;
      if (tId) url += `term_id=${tId}&`;
      const res = await apiFetch(url);
      setRcData(res);
      if (res.class_id && !rcClassId) setRcClassId(String(res.class_id));
      if (res.term_id && !rcTermId) setRcTermId(String(res.term_id));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setRcLoading(false);
    }
  }, [rcClassId, rcTermId]);

  const loadSettings = useCallback(async () => {
    setSettingsLoading(true);
    try {
      const res = await apiFetch('/api/admin/settings');
      setSettingsForm({
        name: res.name || '',
        phone: res.phone || '',
        address: res.address || '',
        logo_url: res.logo_url || '',
        currency: res.currency || 'ZMW',
      });
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSettingsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'attendance') {
      loadAttendance();
    } else if (activeTab === 'class-teachers') {
      loadClassTeachers();
      loadSubstitutes();
    } else if (activeTab === 'sms') {
      loadSmsSettings();
      loadSmsHistory();
      loadSmsBalance();
    } else if (activeTab === 'approvals') {
      loadApprovals();
      loadResultsOverview(resExamFilter, resClassFilter, resSubjFilter);
    } else if (activeTab === 'report-cards') {
      loadReportCards(rcClassId, rcTermId);
    } else if (activeTab === 'settings') {
      loadSettings();
    }
  }, [activeTab]);

  if (loading) return <LoadingState message="Loading School Administration Portal..." />;

  const metrics = data?.metrics || {};
  const classes = data?.classes || [];
  const subjects = data?.subjects || [];
  const terms = data?.terms || [];
  const exams = data?.exams || [];
  const students = data?.students || [];
  const teachers = data?.teachers || [];
  const parents = data?.parents || [];
  const fees = data?.fees || [];
  const payments = data?.payments || [];
  const announcements = data?.announcements || [];
  const timetable = data?.timetable || [];
  const activeTerm = terms.find((t: any) => t.is_active) || terms[0];

  // Filtered students
  const filteredStudents = students.filter((s: any) => {
    if (studentFilterClass && String(s.class_id) !== String(studentFilterClass)) return false;
    if (studentFilterStatus && (s.status || 'active').toLowerCase() !== studentFilterStatus.toLowerCase())
      return false;
    return true;
  });

  return (
    <AppLayout
      title="School Administration"
      subtitle="Manage students, staff, academics, timetables, and school fee collections"
      navItems={ADMIN_NAV}
      activeTab={activeTab}
      onSelectTab={setActiveTab}
      actions={
        <>
          <Button
            variant="primary"
            size="sm"
            icon="bi-person-plus-fill"
            onClick={() => setStudentModalOpen(true)}
          >
            Register Student
          </Button>
          <Button
            variant="accent"
            size="sm"
            icon="bi-person-badge-fill"
            onClick={() => setTeacherModalOpen(true)}
          >
            Register Teacher
          </Button>
          <Button
            variant="outline"
            size="sm"
            icon="bi-credit-card-2-front"
            onClick={() => navigate('/billing/plans')}
          >
            Upgrade Plan
          </Button>
        </>
      }
    >
      <AlertBanner variant="success" message={message} onDismiss={() => setMessage(null)} />
      <AlertBanner variant="danger" message={error} onDismiss={() => setError(null)} />

      {/* ══════════════════════════════════════════════════════════════════
          1. DASHBOARD & ANALYTICS (MODERN REDESIGNED VIEW)
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'dashboard' && (
        <>
          <DashboardHeader
            title="School Executive Overview"
            userName={user?.username || 'Administrator'}
            userRole="School Administrator"
            schoolName={school?.name || data?.school?.name || 'SchoolStacks Academy'}
            academicTerm={data?.active_term?.name || 'Term 1'}
            academicYear={data?.active_term?.academic_year || '2026'}
            badgeText="Live Session"
            badgeVariant="green"
            quickStats={[
              {
                label: 'Attendance',
                value: `${metrics.today_rate || 96}%`,
                icon: 'bi-check2-circle',
              },
              {
                label: 'Term Fees',
                value: `K${Number(metrics.total_collected_zmw || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`,
                icon: 'bi-cash-coin',
              },
            ]}
            actions={
              <div className="d-flex gap-2">
                <Button
                  size="sm"
                  variant="accent"
                  icon="bi-calendar2-check-fill"
                  onClick={() => setActiveTab('attendance')}
                >
                  Mark Attendance
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  icon="bi-chat-dots-fill"
                  onClick={() => setActiveTab('sms')}
                >
                  SMS Alerts
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
                  icon: 'bi-person-plus-fill',
                  label: 'Register Student',
                  description: 'Add new admission record',
                  color: '#002583',
                  onClick: () => setStudentModalOpen(true),
                },
                {
                  icon: 'bi-person-badge-fill',
                  label: 'Add Faculty',
                  description: 'Enrol teaching staff',
                  color: '#7C3AED',
                  onClick: () => setTeacherModalOpen(true),
                },
                {
                  icon: 'bi-cash-stack',
                  label: 'Collect Fees',
                  description: 'Record student tuition',
                  color: '#D97706',
                  onClick: () => setActiveTab('fees'),
                },
                {
                  icon: 'bi-check2-all',
                  label: 'Exam Approvals',
                  description: 'Publish verified marks',
                  color: '#059669',
                  badge: metrics.pending_results_count > 0 ? `${metrics.pending_results_count}` : undefined,
                  onClick: () => setActiveTab('approvals'),
                },
              ]}
            />
          </div>

          {/* Colorful Modern Statistic Cards */}
          <div className="row g-3 mb-4">
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-mortarboard-fill"
                label="Enrolled Students"
                value={metrics.total_students || 0}
                variant="blue"
                trend={{
                  text: `${metrics.total_classes || 0} Active Classes`,
                  positive: true,
                }}
                onClick={() => setActiveTab('students')}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-person-workspace"
                label="Teaching Staff"
                value={metrics.total_teachers || 0}
                variant="purple"
                trend={{
                  text: 'Verified Faculty',
                  positive: null,
                }}
                onClick={() => setActiveTab('teachers')}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-calendar2-check-fill"
                label="Today's Attendance"
                value={`${metrics.today_rate || (metrics.present_count ? Math.round((metrics.present_count / (metrics.present_count + metrics.absent_count)) * 100) : 0)}%`}
                variant="emerald"
                trend={{
                  text: `${metrics.today_present || metrics.present_count || 0} Present / ${metrics.today_absent || metrics.absent_count || 0} Absent`,
                  positive: (metrics.today_rate || 0) >= 80,
                }}
                onClick={() => setActiveTab('attendance')}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-cash-coin"
                label="Fees Collected (ZMW)"
                value={`K${Number(metrics.total_collected_zmw || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                variant="amber"
                trend={{
                  text: `Due: K${Number(metrics.total_outstanding_zmw || 0).toFixed(0)}`,
                  positive: (metrics.total_outstanding_zmw || 0) <= 0,
                }}
                onClick={() => setActiveTab('fees')}
              />
            </div>

            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-door-open-fill"
                label="Active Classrooms"
                value={metrics.total_classes || 0}
                variant="cyan"
                trend={{
                  text: 'Allocations Active',
                  positive: true,
                }}
                onClick={() => setActiveTab('academics')}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-journal-check"
                label="Results For Review"
                value={metrics.pending_results_count || 0}
                variant="amber"
                trend={{
                  text: metrics.pending_results_count > 0 ? 'Action Needed' : 'All Published',
                  positive: metrics.pending_results_count === 0,
                }}
                onClick={() => setActiveTab('approvals')}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-exclamation-triangle-fill"
                label="Absenteeism Alerts"
                value={metrics.today_absent || metrics.absent_count || 0}
                variant="rose"
                trend={{
                  text: `${(data?.absent_today_students || []).length} Today Notice`,
                  positive: (data?.absent_today_students || []).length === 0,
                }}
                onClick={() => setActiveTab('sms')}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <ModernStatCard
                icon="bi-wallet2"
                label="SMS Credit Balance"
                value={`${smsBalance?.currency || 'EUR'} ${Number(smsBalance?.balance || 0).toFixed(2)}`}
                variant="blue"
                trend={{
                  text: 'EasySendSMS Live',
                  positive: true,
                }}
                onClick={() => setActiveTab('sms')}
              />
            </div>
          </div>

          {/* Analytics & Charts Row */}
          <div className="row g-4 mb-4">
            <div className="col-lg-7">
              <Card
                title="Academic Performance by Subject"
                subtitle="Mean examination score averages with 50% passing threshold"
                actions={
                  <Button size="sm" variant="outline" onClick={() => setActiveTab('approvals')}>
                    View Approvals
                  </Button>
                }
              >
                <HorizontalBarChart
                  data={subjects.map((s: any) => ({
                    id: s.id,
                    label: s.name,
                    code: s.code,
                    value: Number(s.average || 0),
                    count: s.count,
                  }))}
                  benchmark={50}
                  benchmarkLabel="50% Pass Benchmark"
                />
              </Card>
            </div>

            <div className="col-lg-5">
              <Card
                title="Attendance Distribution"
                subtitle="Daily school attendance status breakdown"
                actions={
                  <Button size="sm" variant="outline" onClick={() => setActiveTab('attendance')}>
                    Roll Call
                  </Button>
                }
              >
                <DonutChart
                  data={[
                    {
                      label: 'Present',
                      value: metrics.today_present || metrics.present_count || 0,
                      color: '#10B981',
                    },
                    {
                      label: 'Absent',
                      value: metrics.today_absent || metrics.absent_count || 0,
                      color: '#EF4444',
                    },
                    {
                      label: 'Late',
                      value: metrics.late_count || 0,
                      color: '#F59E0B',
                    },
                    {
                      label: 'Excused',
                      value: metrics.excused_count || 0,
                      color: '#3B82F6',
                    },
                  ]}
                  centerValue={metrics.today_rate || (metrics.present_count ? Math.round((metrics.present_count / (metrics.present_count + metrics.absent_count)) * 100) : 0)}
                  centerLabel="Rate %"
                  unit="%"
                />
              </Card>
            </div>
          </div>

          {/* Absent Students Follow-up Banner */}
          {(data?.absent_today_students || []).length > 0 && (
            <div
              className="card border-0 mb-4 overflow-hidden"
              style={{
                borderRadius: '1rem',
                borderLeft: '5px solid #EF4444',
                background: '#FFFFFF',
                boxShadow: '0 4px 18px rgba(239, 68, 68, 0.08)',
              }}
            >
              <div className="card-body p-3.5">
                <div className="d-flex flex-wrap align-items-center justify-content-between gap-3">
                  <div className="d-flex align-items-center gap-3">
                    <div
                      className="rounded-circle d-flex align-items-center justify-content-center"
                      style={{ width: 44, height: 44, background: '#FEE2E2', color: '#B91C1C' }}
                    >
                      <i className="bi bi-bell-fill fs-5" />
                    </div>
                    <div>
                      <div className="fw-bold text-dark">
                        Today's Absenteeism Notices: {(data?.absent_today_students || []).length} Students Absent
                      </div>
                      <div className="text-muted small">
                        Automated parent SMS alerts and administrator follow-up logs are available.
                      </div>
                    </div>
                  </div>
                  <div className="d-flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => setActiveTab('attendance')}>
                      Review Attendance
                    </Button>
                    <Button size="sm" variant="accent" onClick={() => setActiveTab('sms')}>
                      SMS Parent Follow-Up
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}

          <Card
            title="Recent Fee Payments & Receipts"
            actions={
              <Button size="sm" variant="outline" onClick={() => setActiveTab('fees')}>
                Manage All Fees
              </Button>
            }
          >
            <DataTable
              rows={payments.slice(0, 6)}
              columns={[
                { header: 'Student', render: (p) => <span className="fw-bold">{p.student_name}</span> },
                { header: 'Term', render: (p) => p.term_name },
                {
                  header: 'Amount',
                  render: (p) => (
                    <span className="fw-bold" style={{ color: 'var(--color-strong-blue)' }}>
                      K{Number(p.amount_paid || 0).toFixed(2)}
                    </span>
                  ),
                },
                {
                  header: 'Method',
                  render: (p) => (
                    <span className="text-capitalize">
                      {(p.payment_method || 'manual').replace('_', ' ')}
                    </span>
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
                  header: 'Receipt',
                  render: (p) =>
                    p.status === 'completed' ? (
                      <Link
                        to={`/admin/receipt/${p.id}`}
                        className="edu-btn edu-btn-outline edu-btn-sm"
                      >
                        <i className="bi bi-receipt" /> {p.reference || 'Receipt'}
                      </Link>
                    ) : (
                      '—'
                    ),
                },
              ]}
            />
          </Card>
        </>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          2. STUDENTS MANAGEMENT
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'students' && (
        <Card
          title="Student Directory"
          subtitle="Manage student enrollment, class placement/transfers, status, contact details, and fee accounts"
          actions={
            <div className="d-flex gap-2 flex-wrap align-items-center">
              <select
                className="edu-select"
                style={{ width: 'auto', minWidth: 150 }}
                value={studentFilterClass}
                onChange={(e) => setStudentFilterClass(e.target.value)}
              >
                <option value="">All Classes</option>
                {classes.map((c: any) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <select
                className="edu-select"
                style={{ width: 'auto', minWidth: 140 }}
                value={studentFilterStatus}
                onChange={(e) => setStudentFilterStatus(e.target.value)}
              >
                <option value="">All Statuses</option>
                <option value="active">Active</option>
                <option value="transferred">Transferred</option>
                <option value="graduated">Graduated</option>
                <option value="archived">Archived</option>
              </select>
              <Button
                variant="accent"
                size="sm"
                icon="bi-person-plus-fill"
                onClick={() => setStudentModalOpen(true)}
              >
                Register Student
              </Button>
            </div>
          }
        >
          <DataTable
            rows={filteredStudents}
            searchKeys={['first_name', 'last_name', 'admission_no', 'class_name', 'phone', 'parent_phone']}
            searchPlaceholder="Search by name, admission no, class, or phone..."
            columns={[
              {
                header: 'Admission No',
                render: (s) => <Badge variant="blue">{s.admission_no}</Badge>,
              },
              {
                header: 'Full Name',
                render: (s) => (
                  <div>
                    <span className="fw-bold">
                      {s.first_name} {s.last_name}
                    </span>
                    <div className="small text-muted">{s.gender}</div>
                  </div>
                ),
              },
              { header: 'Class', render: (s) => s.class_name },
              {
                header: 'Phone Numbers',
                render: (s) => (
                  <div className="small">
                    {s.phone && (
                      <div>
                        <i className="bi bi-phone me-1" />
                        {s.phone}
                      </div>
                    )}
                    {s.parent_phone && (
                      <div className="text-muted">
                        <i className="bi bi-person-heart me-1" />
                        Parent: {s.parent_phone}
                      </div>
                    )}
                    {!s.phone && !s.parent_phone && <span className="text-muted">—</span>}
                  </div>
                ),
              },
              {
                header: 'Status',
                render: (s) => {
                  const st = (s.status || 'active').toLowerCase();
                  const badgeVariant =
                    st === 'active'
                      ? 'success'
                      : st === 'transferred'
                      ? 'mustard'
                      : st === 'graduated'
                      ? 'blue'
                      : 'neutral';
                  return <Badge variant={badgeVariant}>{st}</Badge>;
                },
              },
              {
                header: 'Term Balance',
                render: (s) => (
                  <span
                    className="fw-bold"
                    style={{
                      color: s.balance > 0 ? '#B91C1C' : '#166534',
                    }}
                  >
                    K{Number(s.balance || 0).toFixed(2)}
                  </span>
                ),
              },
              {
                header: 'Actions',
                render: (s) => (
                  <div className="d-flex gap-1 flex-wrap">
                    <Button
                      size="sm"
                      variant="outline"
                      title="Edit student and class transfer"
                      onClick={() => {
                        setStudentToEdit({
                          ...s,
                          parent_phone: s.parent_phone || '',
                        });
                        setEditStudentPhoneError(null);
                        setEditParentPhoneError(null);
                      }}
                    >
                      <i className="bi bi-pencil-square" /> Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="primary"
                      title="Record fee payment"
                      onClick={() => {
                        setPayModalStudent(s);
                        setManualPayForm((f) => ({
                          ...f,
                          term_id: activeTerm?.id ? String(activeTerm.id) : '',
                        }));
                      }}
                    >
                      <i className="bi bi-cash" /> Fee
                    </Button>
                    {activeTerm && (
                      <a
                        href={`/student/report-card/${s.id}/${activeTerm.id}`}
                        target="_blank"
                        rel="noreferrer"
                        className="edu-btn edu-btn-outline edu-btn-sm"
                        title="Download report card"
                      >
                        <i className="bi bi-file-earmark-pdf" />
                      </a>
                    )}
                    <Button
                      size="sm"
                      variant="danger"
                      title="Delete / Archive student"
                      onClick={() => setStudentToDelete(s)}
                    >
                      <i className="bi bi-trash" />
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        </Card>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          3. TEACHERS MANAGEMENT
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'teachers' && (
        <Card
          title="Teaching Staff"
          subtitle="Manage teachers, phone contacts, email, subject specializations, and active status"
          actions={
            <Button
              variant="accent"
              size="sm"
              icon="bi-person-plus-fill"
              onClick={() => {
                setTeacherPhoneError(null);
                setTeacherModalOpen(true);
              }}
            >
              Register Teacher
            </Button>
          }
        >
          <DataTable
            rows={teachers}
            searchKeys={['first_name', 'last_name', 'staff_no', 'subject_specialization', 'phone', 'email']}
            searchPlaceholder="Search teachers by name, staff no, subject, or phone..."
            columns={[
              { header: 'Staff No', render: (t) => <Badge variant="mustard">{t.staff_no}</Badge> },
              {
                header: 'Name',
                render: (t) => (
                  <div>
                    <span className="fw-bold">
                      {t.first_name} {t.last_name}
                    </span>
                    {t.email && <div className="small text-muted">{t.email}</div>}
                  </div>
                ),
              },
              { header: 'Specialization', render: (t) => t.subject_specialization || 'General' },
              { header: 'Phone Number', render: (t) => t.phone || '—' },
              {
                header: 'Status',
                render: (t) => (
                  <Badge variant={t.is_active ? 'success' : 'neutral'}>
                    {t.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                ),
              },
              {
                header: 'Actions',
                render: (t) => (
                  <div className="d-flex gap-1 flex-wrap">
                    <Button
                      size="sm"
                      variant="outline"
                      title="Edit teacher"
                      onClick={() => {
                        setTeacherToEdit({ ...t });
                        setEditTeacherPhoneError(null);
                      }}
                    >
                      <i className="bi bi-pencil-square" /> Edit
                    </Button>
                    <Button
                      size="sm"
                      variant={t.is_active ? 'outline' : 'primary'}
                      title={t.is_active ? 'Deactivate teacher' : 'Reactivate teacher'}
                      onClick={() => setTeacherToToggle(t)}
                    >
                      <i className={`bi ${t.is_active ? 'bi-person-x' : 'bi-person-check'}`} />{' '}
                      {t.is_active ? 'Deactivate' : 'Activate'}
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      title="Delete teacher"
                      onClick={() => setTeacherToDelete(t)}
                    >
                      <i className="bi bi-trash" />
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        </Card>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          3B. PARENT ACCOUNTS & STUDENT LINKS
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'parents' && (
        <Card
          title="Parent Accounts & Student Links"
          subtitle="Provision parent access, monitor mobile credentials, and link children to guardian profiles"
          actions={
            <Button
              variant="accent"
              size="sm"
              icon="bi-person-plus-fill"
              onClick={() => {
                setParentForm({
                  first_name: '',
                  last_name: '',
                  phone: '',
                  email: '',
                  username: '',
                  password: 'parent123',
                  student_id: '',
                });
                setParentModalOpen(true);
              }}
            >
              Provision Parent Account
            </Button>
          }
        >
          <div className="row g-3 mb-4">
            <div className="col-sm-6 col-md-4">
              <StatCard
                icon="bi-people-fill"
                label="Registered Parents"
                value={parents.length}
                variant="blue"
              />
            </div>
            <div className="col-sm-6 col-md-4">
              <StatCard
                icon="bi-link-45deg"
                label="Active Child Links"
                value={parents.reduce((acc: number, p: any) => acc + (p.linked_students?.length || 0), 0)}
                variant="mustard"
              />
            </div>
            <div className="col-sm-6 col-md-4">
              <StatCard
                icon="bi-shield-lock-fill"
                label="Parent Auth Mode"
                value="Phone / Username"
              />
            </div>
          </div>

          <DataTable
            rows={parents}
            searchKeys={['first_name', 'last_name', 'phone', 'email', 'username']}
            searchPlaceholder="Search parents by name, phone, email, or username..."
            columns={[
              {
                header: 'Parent Name',
                render: (p) => (
                  <div>
                    <span className="fw-bold">{p.first_name} {p.last_name}</span>
                    {p.email && <div className="small text-muted">{p.email}</div>}
                  </div>
                ),
              },
              {
                header: 'Username / Phone',
                render: (p) => (
                  <div className="small">
                    <Badge variant="blue">{p.username || '—'}</Badge>
                    <div className="text-muted mt-1">{p.phone || 'No phone'}</div>
                  </div>
                ),
              },
              {
                header: 'Linked Student(s)',
                render: (p) => (
                  <div className="d-flex flex-wrap gap-1">
                    {(p.linked_students || []).length > 0 ? (
                      p.linked_students.map((st: any) => (
                        <span key={st.id} className="badge bg-light text-dark border">
                          <i className="bi bi-mortarboard me-1" />
                          {st.name || `${st.first_name} ${st.last_name}`} ({st.class_name || 'Class'})
                        </span>
                      ))
                    ) : (
                      <span className="text-muted small">No child linked</span>
                    )}
                  </div>
                ),
              },
              {
                header: 'Actions',
                render: (p) => (
                  <div className="d-flex gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      title="Link or Unlink Child"
                      icon="bi-link-45deg"
                      onClick={() => {
                        setLinkModalParent(p);
                        setLinkStudentId(students[0]?.id ? String(students[0].id) : '');
                      }}
                    >
                      Link Child
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      title="Reset Password"
                      icon="bi-key"
                      onClick={() => {
                        setResetPassParent(p);
                        setNewParentPass('parent123');
                      }}
                    >
                      Reset Pass
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        </Card>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          4. CLASSES, SUBJECTS, TERMS & EXAMS
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'academics' && (
        <div className="row g-4">
          {/* Classes */}
          <div className="col-lg-6">
            <Card title="School Classes" subtitle="Manage class tiers, capacity, and assigned class teachers">
              <form
                className="row g-2 mb-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  handleAction('/api/admin/classes', classForm, () =>
                    setClassForm({
                      name: '',
                      capacity: '40',
                      grade_level: '',
                      academic_year: new Date().getFullYear().toString(),
                      class_teacher_id: '',
                    })
                  );
                }}
              >
                <div className="col-sm-5">
                  <input
                    className="edu-input"
                    placeholder="Class Name (e.g. Grade 11A)"
                    value={classForm.name}
                    onChange={(e) => setClassForm({ ...classForm, name: e.target.value })}
                    required
                  />
                </div>
                <div className="col-sm-3">
                  <input
                    type="number"
                    className="edu-input"
                    placeholder="Capacity"
                    value={classForm.capacity}
                    onChange={(e) => setClassForm({ ...classForm, capacity: e.target.value })}
                    required
                  />
                </div>
                <div className="col-sm-4">
                  <select
                    className="edu-select"
                    value={classForm.class_teacher_id}
                    onChange={(e) => setClassForm({ ...classForm, class_teacher_id: e.target.value })}
                  >
                    <option value="">-- Class Teacher --</option>
                    {teachers
                      .filter((t: any) => t.is_active)
                      .map((t: any) => (
                        <option key={t.id} value={t.id}>
                          {t.first_name} {t.last_name}
                        </option>
                      ))}
                  </select>
                </div>
                <div className="col-12 text-end">
                  <Button type="submit" variant="primary" size="sm" icon="bi-plus-circle">
                    Add Class
                  </Button>
                </div>
              </form>
              <DataTable
                rows={classes}
                pageSize={5}
                columns={[
                  { header: 'Class', render: (c) => <span className="fw-bold">{c.name}</span> },
                  { header: 'Enrolled', render: (c) => `${c.student_count} / ${c.capacity}` },
                  { header: 'Teacher', render: (c) => c.class_teacher_name || '—' },
                  {
                    header: 'Actions',
                    render: (c) => (
                      <div className="d-flex gap-1">
                        <Button
                          size="sm"
                          variant="outline"
                          title="Edit Class"
                          onClick={() => setClassToEdit({ ...c })}
                        >
                          <i className="bi bi-pencil" />
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          title="Delete Class"
                          onClick={() => setClassToDelete(c)}
                        >
                          <i className="bi bi-trash" />
                        </Button>
                      </div>
                    ),
                  },
                ]}
              />
            </Card>
          </div>

          {/* Subjects */}
          <div className="col-lg-6">
            <Card title="School Subjects" subtitle="Curriculum subjects, codes, and syllabus overview">
              <form
                className="row g-2 mb-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  handleAction('/api/admin/subjects', subjForm, () =>
                    setSubjForm({ name: '', code: '', description: '' })
                  );
                }}
              >
                <div className="col-sm-5">
                  <input
                    className="edu-input"
                    placeholder="Subject Name (e.g. Science)"
                    value={subjForm.name}
                    onChange={(e) => setSubjForm({ ...subjForm, name: e.target.value })}
                    required
                  />
                </div>
                <div className="col-sm-3">
                  <input
                    className="edu-input"
                    placeholder="Code (SCI10)"
                    value={subjForm.code}
                    onChange={(e) => setSubjForm({ ...subjForm, code: e.target.value })}
                    required
                  />
                </div>
                <div className="col-sm-4 text-end">
                  <Button type="submit" variant="primary" size="sm" icon="bi-plus-circle">
                    Add Subject
                  </Button>
                </div>
              </form>
              <DataTable
                rows={subjects}
                pageSize={5}
                columns={[
                  { header: 'Code', render: (s) => <Badge variant="blue">{s.code}</Badge> },
                  { header: 'Subject', render: (s) => <span className="fw-bold">{s.name}</span> },
                  { header: 'Mean', render: (s) => `${s.average}%` },
                  {
                    header: 'Status',
                    render: (s) => (
                      <Badge variant={s.is_active ? 'success' : 'neutral'}>
                        {s.is_active ? 'Active' : 'Archived'}
                      </Badge>
                    ),
                  },
                  {
                    header: 'Actions',
                    render: (s) => (
                      <div className="d-flex gap-1">
                        <Button
                          size="sm"
                          variant="outline"
                          title="Edit Subject"
                          onClick={() => setSubjectToEdit({ ...s })}
                        >
                          <i className="bi bi-pencil" />
                        </Button>
                        <Button
                          size="sm"
                          variant={s.is_active ? 'outline' : 'primary'}
                          title={s.is_active ? 'Archive Subject' : 'Restore Subject'}
                          onClick={() =>
                            handleAction(`/api/admin/subjects/${s.id}/toggle-status`, {})
                          }
                        >
                          <i className={`bi ${s.is_active ? 'bi-archive' : 'bi-arrow-clockwise'}`} />
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          title="Delete Subject"
                          onClick={() => setSubjectToDelete(s)}
                        >
                          <i className="bi bi-trash" />
                        </Button>
                      </div>
                    ),
                  },
                ]}
              />
            </Card>
          </div>

          {/* Terms */}
          <div className="col-lg-6">
            <Card title="Academic Terms" subtitle="Term calendar dates, active periods, and schedules">
              <form
                className="row g-2 mb-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (termForm.end_date <= termForm.start_date) {
                    setError('Term end date must be after the start date.');
                    return;
                  }
                  handleAction('/api/admin/terms', termForm, () =>
                    setTermForm({ name: '', start_date: '', end_date: '' })
                  );
                }}
              >
                <div className="col-sm-4">
                  <input
                    className="edu-input"
                    placeholder="Term 2 2026"
                    value={termForm.name}
                    onChange={(e) => setTermForm({ ...termForm, name: e.target.value })}
                    required
                  />
                </div>
                <div className="col-sm-3">
                  <input
                    type="date"
                    className="edu-input"
                    title="Term Start Date"
                    value={termForm.start_date}
                    onChange={(e) => setTermForm({ ...termForm, start_date: e.target.value })}
                    required
                  />
                </div>
                <div className="col-sm-3">
                  <input
                    type="date"
                    className="edu-input"
                    title="Term End Date"
                    value={termForm.end_date}
                    onChange={(e) => setTermForm({ ...termForm, end_date: e.target.value })}
                    required
                  />
                </div>
                <div className="col-sm-2">
                  <Button type="submit" variant="primary" className="w-100" size="sm">
                    Add
                  </Button>
                </div>
              </form>
              <DataTable
                rows={terms}
                pageSize={5}
                columns={[
                  { header: 'Term', render: (t) => <span className="fw-bold">{t.name}</span> },
                  { header: 'Dates', render: (t) => `${t.start_date} to ${t.end_date}` },
                  {
                    header: 'Status',
                    render: (t) => (
                      <Badge variant={t.is_active ? 'success' : 'neutral'}>
                        {t.is_active ? 'Active' : 'Closed'}
                      </Badge>
                    ),
                  },
                  {
                    header: 'Actions',
                    render: (t) => (
                      <div className="d-flex gap-1">
                        <Button
                          size="sm"
                          variant="outline"
                          title="Edit Term Dates"
                          onClick={() => setTermToEdit({ ...t })}
                        >
                          <i className="bi bi-pencil" />
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          title="Delete Term"
                          onClick={() => setTermToDelete(t)}
                        >
                          <i className="bi bi-trash" />
                        </Button>
                      </div>
                    ),
                  },
                ]}
              />
            </Card>
          </div>

          {/* Exams */}
          <div className="col-lg-6">
            <Card title="Examinations" subtitle="Schedule examinations, assign dates, times, and venues">
              <form
                className="row g-2 mb-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  const sDate = examForm.start_date || examForm.date;
                  const eDate = examForm.end_date || sDate;
                  if (sDate && eDate && eDate < sDate) {
                    setError('Exam end date cannot be earlier than start date.');
                    return;
                  }
                  handleAction('/api/admin/exams', { ...examForm, start_date: sDate, end_date: eDate, date: sDate }, () =>
                    setExamForm({
                      name: '',
                      term_id: '',
                      class_id: '',
                      subject_id: '',
                      date: '',
                      start_date: '',
                      end_date: '',
                      start_time: '09:00',
                      end_time: '11:00',
                      venue: '',
                      exam_type: 'Main',
                    })
                  );
                }}
              >
                <div className="col-sm-6">
                  <input
                    className="edu-input"
                    placeholder="Exam (e.g. Mid-Term)"
                    value={examForm.name}
                    onChange={(e) => setExamForm({ ...examForm, name: e.target.value })}
                    required
                  />
                </div>
                <div className="col-sm-6">
                  <select
                    className="edu-select"
                    value={examForm.term_id}
                    onChange={(e) => setExamForm({ ...examForm, term_id: e.target.value })}
                    required
                  >
                    <option value="">-- Term --</option>
                    {terms.map((t: any) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-sm-6">
                  <select
                    className="edu-select"
                    value={examForm.class_id}
                    onChange={(e) => setExamForm({ ...examForm, class_id: e.target.value })}
                  >
                    <option value="">-- All Classes --</option>
                    {classes.map((c: any) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-sm-6">
                  <select
                    className="edu-select"
                    value={examForm.subject_id}
                    onChange={(e) => setExamForm({ ...examForm, subject_id: e.target.value })}
                  >
                    <option value="">-- All Subjects --</option>
                    {subjects.map((s: any) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-sm-6">
                  <label className="edu-label small mb-1">Start Date</label>
                  <input
                    type="date"
                    className="edu-input"
                    value={examForm.start_date || examForm.date}
                    onChange={(e) => setExamForm({ ...examForm, start_date: e.target.value, date: e.target.value })}
                    required
                  />
                </div>
                <div className="col-sm-6">
                  <label className="edu-label small mb-1">End Date</label>
                  <input
                    type="date"
                    className="edu-input"
                    value={examForm.end_date}
                    onChange={(e) => setExamForm({ ...examForm, end_date: e.target.value })}
                    placeholder="Same as start date if 1-day"
                  />
                </div>
                <div className="col-12 text-end">
                  <Button type="submit" variant="primary" size="sm" icon="bi-plus-circle">
                    Schedule Exam Period
                  </Button>
                </div>
              </form>
              <DataTable
                rows={exams}
                pageSize={5}
                columns={[
                  {
                    header: 'Exam',
                    render: (ex) => (
                      <div>
                        <span className="fw-bold">{ex.name}</span>
                        <div className="small text-muted">{ex.term_name}</div>
                      </div>
                    ),
                  },
                  {
                    header: 'Scope',
                    render: (ex) => (
                      <div className="small">
                        <div>{ex.class_name}</div>
                        <div className="text-muted">{ex.subject_name}</div>
                      </div>
                    ),
                  },
                  {
                    header: 'Period & Timing',
                    render: (ex) => (
                      <div className="small">
                        <div className="fw-semibold">
                          {ex.start_date && ex.end_date && ex.start_date !== ex.end_date
                            ? `${ex.start_date} to ${ex.end_date}`
                            : ex.start_date || ex.date || 'Date TBD'}
                        </div>
                        {ex.start_time && (
                          <div className="text-muted">
                            {ex.start_time} – {ex.end_time || ''} {ex.venue ? `(${ex.venue})` : ''}
                          </div>
                        )}
                      </div>
                    ),
                  },
                  {
                    header: 'Status',
                    render: (ex) => (
                      <Badge
                        variant={
                          ex.status === 'completed'
                            ? 'success'
                            : ex.status === 'cancelled'
                            ? 'danger'
                            : 'mustard'
                        }
                      >
                        {ex.status}
                      </Badge>
                    ),
                  },
                  {
                    header: 'Actions',
                    render: (ex) => (
                      <div className="d-flex gap-1">
                        <Button
                          size="sm"
                          variant="outline"
                          title="Edit / Reschedule Exam"
                          onClick={() => setExamToEdit({ ...ex })}
                        >
                          <i className="bi bi-pencil" />
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          title="Cancel / Delete Exam"
                          onClick={() => setExamToDelete(ex)}
                        >
                          <i className="bi bi-trash" />
                        </Button>
                      </div>
                    ),
                  },
                ]}
              />
            </Card>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          5. FEES & ONLINE PAYMENTS
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'fees' && (
        <div className="row g-4">
          <div className="col-lg-5">
            <Card title="Configure Term Fee Structure (ZMW)">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleAction('/api/admin/fees', feeForm, () =>
                    setFeeForm({ class_id: '', term_id: '', amount: '' })
                  );
                }}
              >
                <FormField label="Class">
                  <select
                    className="edu-select"
                    value={feeForm.class_id}
                    onChange={(e) => setFeeForm({ ...feeForm, class_id: e.target.value })}
                    required
                  >
                    <option value="">-- Select Class --</option>
                    {classes.map((c: any) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </FormField>
                <FormField label="Academic Term">
                  <select
                    className="edu-select"
                    value={feeForm.term_id}
                    onChange={(e) => setFeeForm({ ...feeForm, term_id: e.target.value })}
                    required
                  >
                    <option value="">-- Select Term --</option>
                    {terms.map((t: any) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </FormField>
                <FormField label="Fee Amount (ZMW)">
                  <input
                    type="number"
                    step="0.01"
                    className="edu-input"
                    placeholder="e.g. 2500.00"
                    value={feeForm.amount}
                    onChange={(e) => setFeeForm({ ...feeForm, amount: e.target.value })}
                    required
                  />
                </FormField>
                <Button type="submit" variant="accent" className="w-100" icon="bi-check2-circle">
                  Save Fee Structure
                </Button>
              </form>

              <hr className="my-4" />
              <h6 className="fw-bold mb-2">Active Fee Structures</h6>
              <DataTable
                rows={fees}
                pageSize={5}
                columns={[
                  { header: 'Class', render: (f) => f.class_name },
                  { header: 'Term', render: (f) => f.term_name },
                  {
                    header: 'Amount',
                    render: (f) => (
                      <span className="fw-bold">K{Number(f.amount || 0).toFixed(2)}</span>
                    ),
                  },
                ]}
              />
            </Card>
          </div>

          <div className="col-lg-7">
            <Card title="School Fee Payment Ledger">
              <DataTable
                rows={payments}
                searchKeys={['student_name', 'reference', 'payment_method', 'status']}
                columns={[
                  { header: 'Student', render: (p) => <span className="fw-bold">{p.student_name}</span> },
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
                          {p.reference || 'Receipt'}
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

      {/* ══════════════════════════════════════════════════════════════════
          6. TIMETABLE MANAGEMENT
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'timetable' && (
        <div className="row g-4">
          <div className="col-lg-4">
            <Card title="Add Timetable Slot" subtitle="Schedule teacher & class sessions with clash prevention">
              {timetableClashError && (
                <div className="alert alert-danger p-2 small mb-3">
                  <i className="bi bi-exclamation-triangle-fill me-1" />
                  {timetableClashError}
                </div>
              )}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (ttForm.end_time <= ttForm.start_time) {
                    setError('End time must be after start time.');
                    return;
                  }
                  handleAction('/api/admin/timetable', ttForm, () => {
                    setTtForm({
                      class_id: '',
                      subject_id: '',
                      teacher_id: '',
                      day: 'Monday',
                      start_time: '08:00',
                      end_time: '09:00',
                      room: '',
                      term_id: '',
                    });
                  });
                }}
              >
                <FormField label="Class" required>
                  <select
                    className="edu-select"
                    value={ttForm.class_id}
                    onChange={(e) => setTtForm({ ...ttForm, class_id: e.target.value })}
                    required
                  >
                    <option value="">-- Select Class --</option>
                    {classes.map((c: any) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </FormField>

                <FormField label="Subject" required>
                  <select
                    className="edu-select"
                    value={ttForm.subject_id}
                    onChange={(e) => setTtForm({ ...ttForm, subject_id: e.target.value })}
                    required
                  >
                    <option value="">-- Select Subject --</option>
                    {subjects
                      .filter((s: any) => s.is_active)
                      .map((s: any) => (
                        <option key={s.id} value={s.id}>
                          {s.name} ({s.code})
                        </option>
                      ))}
                  </select>
                </FormField>

                <FormField label="Teacher" required>
                  <select
                    className="edu-select"
                    value={ttForm.teacher_id}
                    onChange={(e) => setTtForm({ ...ttForm, teacher_id: e.target.value })}
                    required
                  >
                    <option value="">-- Select Teacher --</option>
                    {teachers
                      .filter((t: any) => t.is_active)
                      .map((t: any) => (
                        <option key={t.id} value={t.id}>
                          {t.first_name} {t.last_name} ({t.subject_specialization || 'General'})
                        </option>
                      ))}
                  </select>
                </FormField>

                <div className="row g-2 mb-3">
                  <div className="col-sm-6">
                    <label className="edu-label">Day of Week</label>
                    <select
                      className="edu-select"
                      value={ttForm.day}
                      onChange={(e) => setTtForm({ ...ttForm, day: e.target.value })}
                    >
                      {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'].map((d) => (
                        <option key={d} value={d}>
                          {d}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="col-sm-6">
                    <label className="edu-label">Room / Venue</label>
                    <input
                      className="edu-input"
                      placeholder="e.g. Lab 2"
                      value={ttForm.room}
                      onChange={(e) => setTtForm({ ...ttForm, room: e.target.value })}
                    />
                  </div>
                </div>

                <div className="row g-2 mb-3">
                  <div className="col-6">
                    <label className="edu-label">Start Time</label>
                    <input
                      type="time"
                      className="edu-input"
                      value={ttForm.start_time}
                      onChange={(e) => setTtForm({ ...ttForm, start_time: e.target.value })}
                      required
                    />
                  </div>
                  <div className="col-6">
                    <label className="edu-label">End Time</label>
                    <input
                      type="time"
                      className="edu-input"
                      value={ttForm.end_time}
                      onChange={(e) => setTtForm({ ...ttForm, end_time: e.target.value })}
                      required
                    />
                  </div>
                </div>

                <Button type="submit" variant="primary" className="w-100" icon="bi-calendar-plus">
                  Save Timetable Slot
                </Button>
              </form>
            </Card>
          </div>

          <div className="col-lg-8">
            <Card title="Master School Timetable" subtitle="Real-time weekly class & teacher schedules">
              <DataTable
                rows={timetable}
                searchKeys={['class_name', 'subject_name', 'teacher_name', 'day', 'room']}
                columns={[
                  { header: 'Day', render: (tt) => <Badge variant="blue">{tt.day}</Badge> },
                  { header: 'Time', render: (tt) => `${tt.start_time} – ${tt.end_time}` },
                  { header: 'Class', render: (tt) => <span className="fw-bold">{tt.class_name}</span> },
                  { header: 'Subject', render: (tt) => tt.subject_name },
                  { header: 'Teacher', render: (tt) => tt.teacher_name },
                  { header: 'Room', render: (tt) => tt.room || '—' },
                  {
                    header: 'Actions',
                    render: (tt) => (
                      <div className="d-flex gap-1">
                        <Button
                          size="sm"
                          variant="outline"
                          title="Edit slot"
                          onClick={() => setTimetableToEdit({ ...tt })}
                        >
                          <i className="bi bi-pencil" />
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          title="Delete slot"
                          onClick={() => setTimetableToDelete(tt)}
                        >
                          <i className="bi bi-trash" />
                        </Button>
                      </div>
                    ),
                  },
                ]}
              />
            </Card>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          7. ANNOUNCEMENTS
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'announcements' && (
        <div className="row g-4">
          <div className="col-lg-5">
            <Card title="Publish School Announcement">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleAction('/api/admin/announcements', annForm, () =>
                    setAnnForm({ title: '', content: '', class_id: '' })
                  );
                }}
              >
                <FormField label="Headline / Title">
                  <input
                    className="edu-input"
                    value={annForm.title}
                    onChange={(e) => setAnnForm({ ...annForm, title: e.target.value })}
                    required
                  />
                </FormField>
                <FormField label="Target Audience">
                  <select
                    className="edu-select"
                    value={annForm.class_id}
                    onChange={(e) => setAnnForm({ ...annForm, class_id: e.target.value })}
                  >
                    <option value="">All Classes (Whole School)</option>
                    {classes.map((c: any) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </FormField>
                <FormField label="Message Content">
                  <textarea
                    rows={4}
                    className="edu-textarea"
                    value={annForm.content}
                    onChange={(e) => setAnnForm({ ...annForm, content: e.target.value })}
                    required
                  />
                </FormField>
                <Button type="submit" variant="accent" className="w-100" icon="bi-send-fill">
                  Publish Announcement
                </Button>
              </form>
            </Card>
          </div>
          <div className="col-lg-7">
            <Card title="Published Announcements">
              <DataTable
                rows={announcements}
                columns={[
                  {
                    header: 'Announcement',
                    render: (a) => (
                      <div>
                        <div className="fw-bold" style={{ color: 'var(--color-strong-blue)' }}>
                          {a.title}
                        </div>
                        <div className="small text-muted">{a.message}</div>
                      </div>
                    ),
                  },
                  {
                    header: 'Audience',
                    render: (a) => <Badge variant="mustard">{a.class_name}</Badge>,
                  },
                  {
                    header: 'Action',
                    render: (a) => (
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={async () => {
                          await apiFetch(`/api/admin/announcements/${a.id}`, { method: 'DELETE' });
                          await loadOverview();
                        }}
                      >
                        Delete
                      </Button>
                    ),
                  },
                ]}
              />
            </Card>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          8. ATTENDANCE MANAGEMENT
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'attendance' && (
        <>
          <div className="card p-3 mb-4 shadow-sm border-0">
            <div className="row g-3 align-items-center">
              <div className="col-md-4">
                <label className="form-label small fw-bold">Select Date</label>
                <input
                  type="date"
                  className="edu-input"
                  value={attDate}
                  onChange={(e) => {
                    setAttDate(e.target.value);
                    loadAttendance(e.target.value, attClassId);
                  }}
                />
              </div>
              <div className="col-md-5">
                <label className="form-label small fw-bold">Filter by Class</label>
                <select
                  className="edu-select"
                  value={attClassId}
                  onChange={(e) => {
                    setAttClassId(e.target.value);
                    loadAttendance(attDate, e.target.value);
                  }}
                >
                  <option value="">All Classes (School-Wide)</option>
                  {classes.map((c: any) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-md-3 d-flex align-items-end">
                <Button
                  variant="outline"
                  icon="bi-arrow-clockwise"
                  className="w-100"
                  onClick={() => loadAttendance(attDate, attClassId)}
                >
                  Refresh Register
                </Button>
              </div>
            </div>
          </div>

          {attOverview?.summary && (
            <>
              <div className="row g-3 mb-4">
                <div className="col-sm-6 col-xl-3">
                  <StatCard
                    icon="bi-building-check"
                    label="Active Classes"
                    value={`${attOverview.summary.classes_with_teachers || 0} / ${attOverview.summary.total_classes || 0} Assigned`}
                    variant="blue"
                  />
                </div>
                <div className="col-sm-6 col-xl-3">
                  <StatCard
                    icon="bi-clipboard2-check-fill"
                    label="Registers Submitted Today"
                    value={`${attOverview.summary.submitted_classes_count || 0} Submitted`}
                    variant="blue"
                  />
                </div>
                <div className="col-sm-6 col-xl-3">
                  <StatCard
                    icon="bi-hourglass-split"
                    label="Pending Class Registers"
                    value={`${attOverview.summary.pending_classes_count || 0} Pending`}
                    variant="mustard"
                    accentTop
                  />
                </div>
                <div className="col-sm-6 col-xl-3">
                  <StatCard
                    icon="bi-pie-chart-fill"
                    label="Overall Attendance"
                    value={`${attOverview.summary.attendance_rate || 0}%`}
                    variant="blue"
                  />
                </div>
              </div>

              {attOverview.teachers_not_submitted && attOverview.teachers_not_submitted.length > 0 && (
                <div className="card mb-4 border-0 shadow-sm" style={{ borderLeft: '5px solid #FFB800', borderRadius: '0.75rem' }}>
                  <div className="card-body p-3">
                    <div className="d-flex align-items-center justify-content-between mb-2">
                      <div className="fw-bold text-dark">
                        <i className="bi bi-exclamation-circle-fill text-warning me-2" />
                        Pending Attendance from {attOverview.teachers_not_submitted.length} Class Teachers ({attDate})
                      </div>
                      <span className="badge bg-warning-subtle text-dark">Action Required</span>
                    </div>
                    <div className="table-responsive">
                      <table className="table table-sm align-middle mb-0">
                        <thead className="table-light">
                          <tr className="small text-muted">
                            <th>Class</th>
                            <th>Class Teacher</th>
                            <th>Phone</th>
                            <th>Status</th>
                            <th className="text-end">Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {attOverview.teachers_not_submitted.map((t: any, idx: number) => (
                            <tr key={idx}>
                              <td className="fw-bold text-dark">{t.class_name}</td>
                              <td>{t.teacher_name}</td>
                              <td className="small text-muted">{t.teacher_phone || 'No phone on file'}</td>
                              <td>
                                <span className="badge bg-warning-subtle text-warning-emphasis">Not Submitted</span>
                              </td>
                              <td className="text-end">
                                <button
                                  type="button"
                                  className="btn btn-sm btn-outline-primary"
                                  onClick={() => {
                                    setTestSmsModal({
                                      phone: t.teacher_phone,
                                      message: `Dear ${t.teacher_name}, this is a reminder from School Administration to submit today's attendance register for ${t.class_name}.`,
                                    });
                                    setActiveTab('sms');
                                    setSmsSubTab('settings');
                                  }}
                                >
                                  <i className="bi bi-chat-text-fill me-1" /> Send Reminder
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}

          {attOverview?.summary && (
            <div className="row g-3 mb-4">
              <div className="col-sm-6 col-xl-3">
                <StatCard
                  icon="bi-people-fill"
                  label="Total Enrolled"
                  value={attOverview.summary.total_students || 0}
                  variant="blue"
                />
              </div>
              <div className="col-sm-6 col-xl-3">
                <StatCard
                  icon="bi-check-circle-fill"
                  label="Present & Late"
                  value={`${attOverview.summary.present_count || 0} (${attOverview.summary.attendance_rate || 0}%)`}
                  variant="blue"
                />
              </div>
              <div className="col-sm-6 col-xl-3">
                <StatCard
                  icon="bi-x-circle-fill"
                  label="Absent / Sick"
                  value={attOverview.summary.absent_count + (attOverview.summary.sick_count || 0)}
                  variant="mustard"
                />
              </div>
              <div className="col-sm-6 col-xl-3">
                <StatCard
                  icon="bi-clock-history"
                  label="Late / Excused"
                  value={`${attOverview.summary.late_count || 0} / ${attOverview.summary.excused_count || 0}`}
                />
              </div>
            </div>
          )}

          {attOverview?.absent_today && attOverview.absent_today.length > 0 && (
            <Card
              title={`Students Absent on ${attDate}`}
              subtitle="Requires follow-up with parent / guardian"
              className="mb-4 border-warning"
            >
              <DataTable
                rows={attOverview.absent_today}
                columns={[
                  { header: 'Admission No', render: (s) => <span className="fw-bold">{s.admission_no}</span> },
                  { header: 'Student Name', render: (s) => <span className="fw-bold">{s.name}</span> },
                  { header: 'Class', render: (s) => <Badge variant="blue">{s.class_name}</Badge> },
                  { header: 'Status', render: (s) => <Badge variant="danger">{s.status}</Badge> },
                  { header: 'Guardian Phone', render: (s) => <span className="fw-bold text-primary">{s.guardian_phone}</span> },
                  { header: 'Remarks', render: (s) => s.remarks || '—' },
                  {
                    header: 'Actions',
                    render: (s) => (
                      <div className="d-flex gap-2">
                        <Button
                          size="sm"
                          variant="accent"
                          icon="bi-telephone-outbound-fill"
                          onClick={() => openCallParent(s)}
                        >
                          Call Parent
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setAttCorrectStudent(s);
                            setAttCorrectStatus(s.status);
                            setAttCorrectRemarks(s.remarks || '');
                            setAttCorrectReason('');
                          }}
                        >
                          Correct
                        </Button>
                      </div>
                    ),
                  },
                ]}
              />
            </Card>
          )}

          <Card
            title={`Attendance Register (${attDate})`}
            subtitle="Full school-wide attendance log"
            actions={
              <Button size="sm" variant="outline" onClick={() => loadAttendance(attDate, attClassId)}>
                <i className="bi bi-arrow-clockwise me-1" /> Reload
              </Button>
            }
          >
            {attLoading ? (
              <LoadingState message="Loading attendance register..." />
            ) : (
              <DataTable
                rows={attOverview?.students || []}
                columns={[
                  { header: 'Admission No', render: (s) => <span className="fw-bold">{s.admission_no}</span> },
                  { header: 'Student Name', render: (s) => <span className="fw-bold">{s.name}</span> },
                  { header: 'Class', render: (s) => <Badge variant="blue">{s.class_name}</Badge> },
                  {
                    header: 'Status',
                    render: (s) => {
                      let badgeVar: any = 'neutral';
                      if (s.status === 'Present') badgeVar = 'success';
                      else if (s.status === 'Late') badgeVar = 'mustard';
                      else if (s.status === 'Absent') badgeVar = 'danger';
                      else if (s.status === 'Sick') badgeVar = 'mustard';
                      else if (s.status === 'Excused') badgeVar = 'blue';
                      return <Badge variant={badgeVar}>{s.status}</Badge>;
                    },
                  },
                  { header: 'Remarks', render: (s) => s.remarks || '—' },
                  {
                    header: 'Action',
                    render: (s) => (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setAttCorrectStudent(s);
                          setAttCorrectStatus(s.status === 'Unmarked' ? 'Present' : s.status);
                          setAttCorrectRemarks(s.remarks || '');
                          setAttCorrectReason('');
                        }}
                      >
                        <i className="bi bi-pencil-square me-1" /> Correct
                      </Button>
                    ),
                  },
                ]}
              />
            )}
          </Card>
        </>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          9. RESULTS & APPROVALS WORKFLOW
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'approvals' && (
        <>
          <Card
            title="Examination Results Awaiting Administrator Approval"
            subtitle="Teachers enter drafts and submit for review before grades become visible to students and parents"
            className="mb-4"
          >
            {approvalsLoading ? (
              <LoadingState message="Checking pending result submissions..." />
            ) : pendingApprovals.length === 0 ? (
              <div className="text-center py-4 text-muted">
                <i className="bi bi-check-circle-fill text-success fs-1 mb-2 d-block" />
                <div className="fw-bold">No Examination Batches Awaiting Approval</div>
                <div className="small">All submitted teacher marks have been approved and published.</div>
              </div>
            ) : (
              <DataTable
                rows={pendingApprovals}
                columns={[
                  { header: 'Exam', render: (b) => <span className="fw-bold">{b.exam_name}</span> },
                  { header: 'Class', render: (b) => <Badge variant="blue">{b.class_name}</Badge> },
                  { header: 'Subject', render: (b) => <span className="fw-bold">{b.subject_name}</span> },
                  { header: 'Students', render: (b) => b.student_count },
                  {
                    header: 'Class Mean',
                    render: (b) => (
                      <span className={`fw-bold ${b.average_score >= 50 ? 'text-success' : 'text-danger'}`}>
                        {b.average_score}%
                      </span>
                    ),
                  },
                  {
                    header: 'Actions',
                    render: (b) => (
                      <div className="d-flex gap-2">
                        <Button
                          size="sm"
                          variant="accent"
                          icon="bi-check2-circle"
                          onClick={() => {
                            handleAction(
                              '/api/admin/results/approve',
                              {
                                exam_id: b.exam_id,
                                class_id: b.class_id,
                                subject_id: b.subject_id,
                                action: 'approve_publish',
                              },
                              () => {
                                loadApprovals();
                                loadResultsOverview(resExamFilter, resClassFilter, resSubjFilter);
                              }
                            );
                          }}
                        >
                          Approve & Publish
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            handleAction(
                              '/api/admin/results/approve',
                              {
                                exam_id: b.exam_id,
                                class_id: b.class_id,
                                subject_id: b.subject_id,
                                action: 'reject_to_draft',
                              },
                              () => {
                                loadApprovals();
                                loadResultsOverview(resExamFilter, resClassFilter, resSubjFilter);
                              }
                            );
                          }}
                        >
                          Return to Draft
                        </Button>
                      </div>
                    ),
                  },
                ]}
              />
            )}
          </Card>

          <Card title="Published Examination Results Explorer">
            <div className="row g-3 mb-3">
              <div className="col-md-4">
                <select
                  className="edu-select"
                  value={resExamFilter}
                  onChange={(e) => {
                    setResExamFilter(e.target.value);
                    loadResultsOverview(e.target.value, resClassFilter, resSubjFilter);
                  }}
                >
                  <option value="">All Examinations</option>
                  {exams.map((ex: any) => (
                    <option key={ex.id} value={ex.id}>
                      {ex.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-md-4">
                <select
                  className="edu-select"
                  value={resClassFilter}
                  onChange={(e) => {
                    setResClassFilter(e.target.value);
                    loadResultsOverview(resExamFilter, e.target.value, resSubjFilter);
                  }}
                >
                  <option value="">All Classes</option>
                  {classes.map((c: any) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-md-4">
                <select
                  className="edu-select"
                  value={resSubjFilter}
                  onChange={(e) => {
                    setResSubjFilter(e.target.value);
                    loadResultsOverview(resExamFilter, resClassFilter, e.target.value);
                  }}
                >
                  <option value="">All Subjects</option>
                  {subjects.map((s: any) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.code})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {resOverview && (
              <div className="row g-2 mb-3">
                <div className="col-md-3">
                  <div className="p-2 border rounded bg-light text-center">
                    <span className="small text-muted">Total Marks:</span>{' '}
                    <strong>{resOverview.count || 0}</strong>
                  </div>
                </div>
                <div className="col-md-3">
                  <div className="p-2 border rounded bg-light text-center">
                    <span className="small text-muted">Average Score:</span>{' '}
                    <strong>{resOverview.average || 0}%</strong>
                  </div>
                </div>
                <div className="col-md-3">
                  <div className="p-2 border rounded bg-light text-center text-success">
                    <span className="small text-muted">Passed:</span>{' '}
                    <strong>{resOverview.pass_count || 0}</strong>
                  </div>
                </div>
                <div className="col-md-3">
                  <div className="p-2 border rounded bg-light text-center text-danger">
                    <span className="small text-muted">Failed:</span>{' '}
                    <strong>{resOverview.fail_count || 0}</strong>
                  </div>
                </div>
              </div>
            )}

            <DataTable
              rows={resOverview?.results || []}
              columns={[
                { header: 'Admission No', render: (r) => <span className="fw-bold">{r.admission_no}</span> },
                { header: 'Student', render: (r) => <span className="fw-bold">{r.student_name}</span> },
                { header: 'Class', render: (r) => r.class_name },
                { header: 'Subject', render: (r) => r.subject_name },
                { header: 'Exam', render: (r) => r.exam_name },
                {
                  header: 'Score',
                  render: (r) => (
                    <span className={`fw-bold ${r.marks >= 50 ? 'text-success' : 'text-danger'}`}>
                      {r.marks}
                    </span>
                  ),
                },
                {
                  header: 'Grade',
                  render: (r) => (
                    <Badge variant={r.marks >= 75 ? 'success' : r.marks >= 50 ? 'blue' : 'danger'}>
                      {r.grade}
                    </Badge>
                  ),
                },
                {
                  header: 'Status',
                  render: (r) => (
                    <Badge variant={r.status === 'published' ? 'success' : r.status === 'submitted' ? 'mustard' : 'neutral'}>
                      {r.status}
                    </Badge>
                  ),
                },
                { header: 'Teacher Remarks', render: (r) => r.remarks || '—' },
              ]}
            />
          </Card>
        </>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          10. REPORT CARD MANAGEMENT
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'report-cards' && (
        <Card
          title="Student Report Cards & Academic Standings"
          subtitle="Generate, review, and download official academic report cards as PDF"
        >
          <div className="row g-3 mb-4">
            <div className="col-md-5">
              <label className="form-label small fw-bold">Select Class</label>
              <select
                className="edu-select"
                value={rcClassId}
                onChange={(e) => {
                  setRcClassId(e.target.value);
                  loadReportCards(e.target.value, rcTermId);
                }}
              >
                {classes.map((c: any) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-5">
              <label className="form-label small fw-bold">Select Term</label>
              <select
                className="edu-select"
                value={rcTermId}
                onChange={(e) => {
                  setRcTermId(e.target.value);
                  loadReportCards(rcClassId, e.target.value);
                }}
              >
                {terms.map((t: any) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-2 d-flex align-items-end">
              <Button
                variant="outline"
                className="w-100"
                icon="bi-arrow-clockwise"
                onClick={() => loadReportCards(rcClassId, rcTermId)}
              >
                Refresh
              </Button>
            </div>
          </div>

          {rcLoading ? (
            <LoadingState message="Calculating student academic standings..." />
          ) : (
            <DataTable
              rows={rcData?.student_cards || []}
              columns={[
                { header: 'Admission No', render: (s) => <span className="fw-bold">{s.admission_no}</span> },
                { header: 'Student Name', render: (s) => <span className="fw-bold">{s.name}</span> },
                {
                  header: 'Term Average',
                  render: (s) => (
                    <span className={`fw-bold ${s.average >= 50 ? 'text-success' : 'text-danger'}`}>
                      {s.average > 0 ? `${s.average}%` : 'No Marks'}
                    </span>
                  ),
                },
                {
                  header: 'Final Grade',
                  render: (s) => (
                    <Badge variant={s.average >= 75 ? 'success' : s.average >= 50 ? 'blue' : 'danger'}>
                      {s.final_grade}
                    </Badge>
                  ),
                },
                {
                  header: 'Class Rank',
                  render: (s) => (
                    <span className="fw-bold" style={{ color: 'var(--color-strong-blue)' }}>
                      #{s.class_rank} of {s.class_size}
                    </span>
                  ),
                },
                {
                  header: 'Official Report',
                  render: (s) => (
                    <a
                      href={s.pdf_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="edu-btn edu-btn-primary edu-btn-sm text-decoration-none"
                    >
                      <i className="bi bi-file-earmark-pdf-fill me-1" /> Download PDF
                    </a>
                  ),
                },
              ]}
            />
          )}
        </Card>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          11. SCHOOL SETTINGS
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'settings' && (
        <Card
          title="School Profile & Operating Configurations"
          subtitle="Customize your school identity, official contact information, and operating currency"
        >
          {settingsLoading ? (
            <LoadingState message="Loading school settings..." />
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleAction('/api/admin/settings', settingsForm, () => loadSettings());
              }}
            >
              <div className="row g-3">
                <div className="col-md-6">
                  <FormField label="School Official Name">
                    <input
                      className="edu-input"
                      value={settingsForm.name}
                      onChange={(e) => setSettingsForm({ ...settingsForm, name: e.target.value })}
                      required
                    />
                  </FormField>
                </div>
                <div className="col-md-6">
                  <FormField label="Official Phone Contact">
                    <input
                      className="edu-input"
                      value={settingsForm.phone}
                      onChange={(e) => setSettingsForm({ ...settingsForm, phone: e.target.value })}
                      placeholder="e.g. 0977123456"
                    />
                  </FormField>
                </div>
                <div className="col-md-12">
                  <FormField label="Physical Campus Address">
                    <input
                      className="edu-input"
                      value={settingsForm.address}
                      onChange={(e) => setSettingsForm({ ...settingsForm, address: e.target.value })}
                      placeholder="e.g. Plot 1045, Great East Road, Lusaka"
                    />
                  </FormField>
                </div>
                <div className="col-md-8">
                  <FormField label="School Logo URL">
                    <input
                      className="edu-input"
                      value={settingsForm.logo_url}
                      onChange={(e) => setSettingsForm({ ...settingsForm, logo_url: e.target.value })}
                      placeholder="https://your-domain.com/logo.png"
                    />
                  </FormField>
                </div>
                <div className="col-md-4">
                  <FormField label="Operating Currency">
                    <select
                      className="edu-select"
                      value={settingsForm.currency}
                      onChange={(e) => setSettingsForm({ ...settingsForm, currency: e.target.value })}
                    >
                      <option value="ZMW">ZMW - Zambian Kwacha (K)</option>
                      <option value="USD">USD - US Dollar ($)</option>
                      <option value="EUR">EUR - Euro (€)</option>
                      <option value="GBP">GBP - British Pound (£)</option>
                      <option value="KES">KES - Kenyan Shilling</option>
                      <option value="ZAR">ZAR - South African Rand</option>
                    </select>
                  </FormField>
                </div>
              </div>
              <div className="d-flex justify-content-end mt-4">
                <Button type="submit" variant="accent" icon="bi-check-circle-fill">
                  Save School Settings
                </Button>
              </div>
            </form>
          )}
        </Card>
      )}


      {/* ══════════════════════════════════════════════════════════════════
          CLASS TEACHER ALLOCATION TAB
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'class-teachers' && (
        <>
          <div className="d-flex flex-wrap align-items-center justify-content-between gap-3 mb-4">
            <div>
              <h2 className="h4 fw-bold text-dark mb-1">Class Teacher Allocation & Daily Attendance Assignment</h2>
              <p className="text-muted small mb-0">
                Designate designated Class Teachers to manage class rolls, daily attendance registers, and pastoral oversight.
              </p>
            </div>
            <div className="d-flex gap-2">
              <Button
                variant="accent"
                icon="bi-person-plus-fill"
                onClick={() =>
                  setAssignCtModal({
                    class_id: ctData?.unallocated_classes?.[0]?.id || '',
                    teacher_id: ctData?.unallocated_teachers?.[0]?.id || '',
                    academic_year: '2025/2026',
                    is_override: false,
                    override_reason: '',
                  })
                }
              >
                Assign Class Teacher
              </Button>
              <Button
                variant="outline"
                icon="bi-person-switch"
                onClick={() =>
                  setAssignSubModal({
                    class_id: classes[0]?.id || '',
                    substitute_teacher_id: teachers[0]?.id || '',
                    start_date: new Date().toISOString().slice(0, 10),
                    end_date: new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10),
                    reason: '',
                  })
                }
              >
                Assign Substitute
              </Button>
            </div>
          </div>

          <div className="row g-3 mb-4">
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-door-open-fill"
                label="Total Classes"
                value={classes.length}
                variant="blue"
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-person-check-fill"
                label="Assigned Class Teachers"
                value={ctData?.allocations?.length || 0}
                variant="blue"
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-exclamation-diamond-fill"
                label="Unassigned Classes"
                value={ctData?.unallocated_classes?.length || 0}
                variant={ctData?.unallocated_classes?.length > 0 ? 'mustard' : 'blue'}
                accentTop={ctData?.unallocated_classes?.length > 0}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-clock-history"
                label="Active Substitutes"
                value={subsData.filter((s: any) => s.is_active).length}
                variant="blue"
              />
            </div>
          </div>

          {ctData?.unallocated_classes && ctData.unallocated_classes.length > 0 && (
            <div className="alert alert-warning border-0 shadow-sm mb-4 d-flex align-items-center justify-content-between p-3" style={{ borderRadius: '0.75rem' }}>
              <div>
                <i className="bi bi-exclamation-triangle-fill me-2 fs-5 text-warning" />
                <strong>Unallocated Classes:</strong> The following {ctData.unallocated_classes.length} classes have no designated Class Teacher:{' '}
                {ctData.unallocated_classes.map((c: any) => c.name).join(', ')}.
              </div>
              <Button
                size="sm"
                variant="accent"
                onClick={() =>
                  setAssignCtModal({
                    class_id: ctData.unallocated_classes[0]?.id || '',
                    teacher_id: ctData.unallocated_teachers?.[0]?.id || '',
                    academic_year: '2025/2026',
                    is_override: false,
                    override_reason: '',
                  })
                }
              >
                Assign Now
              </Button>
            </div>
          )}

          <Card
            title="Designated Class Teacher Allocations"
            subtitle="Current active assignments per academic year. Only one designated Class Teacher allowed per class."
            className="mb-4"
            actions={
              <Button size="sm" variant="outline" onClick={loadClassTeachers} icon="bi-arrow-clockwise">
                Reload
              </Button>
            }
          >
            {ctLoading ? (
              <LoadingState message="Loading Class Teacher allocations..." />
            ) : (
              <DataTable
                rows={ctData?.allocations || []}
                columns={[
                  {
                    header: 'Class',
                    render: (a) => (
                      <div>
                        <span className="fw-bold text-dark">{a.class_name}</span>
                        {a.academic_year && <span className="text-muted small ms-1">({a.academic_year})</span>}
                      </div>
                    ),
                  },
                  {
                    header: 'Designated Class Teacher',
                    render: (a) => (
                      <div>
                        <span className="fw-bold text-primary">{a.teacher_name}</span>
                        <div className="text-muted small">Staff No: {a.staff_no || '—'}</div>
                      </div>
                    ),
                  },
                  {
                    header: 'Assigned Date',
                    render: (a) => a.assignment_date || '—',
                  },
                  {
                    header: 'Status & Policy',
                    render: (a) => (
                      <div className="d-flex flex-column gap-1">
                        <Badge variant="success">Active</Badge>
                        {a.is_override && (
                          <span className="badge bg-warning-subtle text-warning-emphasis border border-warning" title={a.override_reason}>
                            <i className="bi bi-shield-exclamation me-1" /> Override: {a.override_reason?.slice(0, 25)}...
                          </span>
                        )}
                      </div>
                    ),
                  },
                  {
                    header: 'Previous Teacher',
                    render: (a) => a.previous_teacher_name || <span className="text-muted">—</span>,
                  },
                  {
                    header: 'Actions',
                    render: (a) => (
                      <div className="d-flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            setAssignCtModal({
                              class_id: a.class_id,
                              teacher_id: a.teacher_id,
                              academic_year: a.academic_year || '2025/2026',
                              is_override: false,
                              override_reason: '',
                            })
                          }
                        >
                          Reassign
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={async () => {
                            if (!window.confirm(`Revoke class teacher allocation for ${a.class_name}?`)) return;
                            try {
                              await apiFetch(`/api/admin/class-teachers/${a.id}`, { method: 'DELETE' });
                              setMessage(`Class Teacher allocation revoked for ${a.class_name}.`);
                              loadClassTeachers();
                            } catch (err: any) {
                              setError(err.message);
                            }
                          }}
                        >
                          Revoke
                        </Button>
                      </div>
                    ),
                  },
                ]}
              />
            )}
          </Card>

          {/* Temporary Substitutes Card */}
          <Card
            title="Temporary Substitute Teacher Allocations"
            subtitle="Substitutes authorized to record daily attendance during teacher absence"
            className="mb-4"
          >
            <DataTable
              rows={subsData}
              columns={[
                { header: 'Class', render: (s) => <span className="fw-bold">{s.class_name}</span> },
                { header: 'Primary Teacher', render: (s) => s.original_teacher_name || '—' },
                { header: 'Substitute Teacher', render: (s) => <span className="fw-bold text-primary">{s.substitute_teacher_name}</span> },
                {
                  header: 'Coverage Window',
                  render: (s) => (
                    <span className="small">
                      {s.start_date} to {s.end_date}
                    </span>
                  ),
                },
                { header: 'Reason', render: (s) => s.reason || '—' },
                {
                  header: 'Status',
                  render: (s) => (s.is_active ? <Badge variant="success">Active</Badge> : <Badge variant="neutral">Inactive</Badge>),
                },
                {
                  header: 'Actions',
                  render: (s) =>
                    s.is_active ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={async () => {
                          try {
                            await apiFetch(`/api/admin/substitutes/${s.id}`, { method: 'DELETE' });
                            setMessage('Substitute allocation deactivated.');
                            loadSubstitutes();
                          } catch (err: any) {
                            setError(err.message);
                          }
                        }}
                      >
                        Deactivate
                      </Button>
                    ) : (
                      <span className="text-muted small">Closed</span>
                    ),
                },
              ]}
            />
          </Card>

          {/* Allocation History Log */}
          {ctData?.history && ctData.history.length > 0 && (
            <Card title="Allocation Audit Trail" subtitle="Historical records of reassignments and overrides">
              <DataTable
                rows={ctData.history}
                columns={[
                  { header: 'Academic Year', render: (h) => h.academic_year || '—' },
                  { header: 'Class', render: (h) => h.class_name },
                  { header: 'Teacher', render: (h) => h.teacher_name },
                  { header: 'Status', render: (h) => <Badge variant={h.status === 'active' ? 'success' : 'neutral'}>{h.status}</Badge> },
                  { header: 'Date', render: (h) => h.assignment_date || '—' },
                  { header: 'Override', render: (h) => (h.is_override ? h.override_reason || 'Yes' : 'No') },
                ]}
              />
            </Card>
          )}
        </>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          SMS & PARENT COMMUNICATION (EASYSENDSMS) TAB
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'sms' && (
        <>
          <div className="d-flex flex-wrap align-items-center justify-content-between gap-3 mb-4">
            <div>
              <div className="d-flex align-items-center gap-2 mb-1">
                <h2 className="h4 fw-bold text-dark mb-0">SMS & Parent Communication (EasySendSMS)</h2>
                {smsSettings?.is_dry_run && (
                  <span className="badge bg-info-subtle text-info-emphasis border border-info px-2 py-1" style={{ borderRadius: '0.5rem' }}>
                    <i className="bi bi-shield-check me-1" /> Dry-Run / Test Mode Active
                  </span>
                )}
                <span className="badge bg-primary-subtle text-primary border border-primary px-2 py-1" style={{ borderRadius: '0.5rem' }}>
                  EasySendSMS REST API
                </span>
              </div>
              <p className="text-muted small mb-0">
                Automated parent communication engine powered by official EasySendSMS REST API. Manages fee reminders, repeated absenteeism alerts, and direct guardian call logging.
              </p>
            </div>
            <div className="d-flex gap-2">
              <Button
                variant="outline"
                icon="bi-arrow-clockwise"
                onClick={() => {
                  loadSmsBalance(true);
                  loadSmsHistory();
                  loadSmsSettings();
                }}
              >
                Refresh
              </Button>
              <Button
                variant="accent"
                icon="bi-send-fill"
                onClick={() =>
                  setTestSmsModal({
                    phone: '',
                    message: 'SchoolStacks SMS Test: EasySendSMS automated parent notification gateway is fully operational.',
                  })
                }
              >
                Send Test SMS
              </Button>
            </div>
          </div>

          <div className="row g-3 mb-4">
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-wallet2"
                label="SMS Credit Balance"
                value={`${smsBalance?.currency || 'EUR'} ${Number(smsBalance?.balance || 0).toFixed(2)}`}
                variant="blue"
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-send-check-fill"
                label="Total SMS Sent"
                value={smsHistory?.metrics?.total_sent || 0}
                variant="blue"
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-check-all"
                label="Delivered"
                value={`${smsHistory?.metrics?.delivered || 0} (${smsHistory?.metrics?.total_sent ? Math.round(((smsHistory.metrics.delivered || 0) / smsHistory.metrics.total_sent) * 100) : 100}%)`}
                variant="blue"
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-exclamation-triangle"
                label="Failed / Undelivered"
                value={smsHistory?.metrics?.failed || 0}
                variant="mustard"
              />
            </div>
          </div>

          {/* Sub-navigation tabs */}
          <div className="d-flex gap-2 mb-4 border-bottom pb-2">
            <button
              type="button"
              className={`btn btn-sm ${smsSubTab === 'settings' ? 'btn-primary' : 'btn-light'}`}
              onClick={() => setSmsSubTab('settings')}
            >
              <i className="bi bi-gear-fill me-1" /> Gateway Settings
            </button>
            <button
              type="button"
              className={`btn btn-sm ${smsSubTab === 'reminders' ? 'btn-primary' : 'btn-light'}`}
              onClick={() => {
                setSmsSubTab('reminders');
                loadFeeReminders();
              }}
            >
              <i className="bi bi-cash-stack me-1" /> Automated Fee Reminders
            </button>
            <button
              type="button"
              className={`btn btn-sm ${smsSubTab === 'absenteeism' ? 'btn-primary' : 'btn-light'}`}
              onClick={() => {
                setSmsSubTab('absenteeism');
                loadAbsenteeism();
              }}
            >
              <i className="bi bi-person-x-fill me-1" /> Repeated Absenteeism Alerts
            </button>
            <button
              type="button"
              className={`btn btn-sm ${smsSubTab === 'history' ? 'btn-primary' : 'btn-light'}`}
              onClick={() => {
                setSmsSubTab('history');
                loadSmsHistory();
              }}
            >
              <i className="bi bi-journal-text me-1" /> Message History Ledger
            </button>
          </div>

          {/* Sub-tab 1: Settings */}
          {smsSubTab === 'settings' && (
            <Card title="EasySendSMS Integration & Automated Dispatch Configuration" subtitle="Configure school Sender ID, scheduling thresholds, and message templates.">
              {smsLoading ? (
                <LoadingState message="Loading SMS settings..." />
              ) : (
                <form
                  onSubmit={async (e) => {
                    e.preventDefault();
                    try {
                      await apiFetch('/api/admin/sms/settings', {
                        method: 'PUT',
                        body: JSON.stringify(smsSettings),
                      });
                      setMessage('SMS configuration saved successfully.');
                    } catch (err: any) {
                      setError(err.message);
                    }
                  }}
                >
                  <div className="row g-3">
                    <div className="col-md-6">
                      <div className="form-check form-switch mt-2">
                        <input
                          className="form-check-input"
                          type="checkbox"
                          id="smsEnabledCheck"
                          checked={Boolean(smsSettings?.sms_enabled)}
                          onChange={(e) => setSmsSettings({ ...smsSettings, sms_enabled: e.target.checked })}
                        />
                        <label className="form-check-label fw-bold" htmlFor="smsEnabledCheck">
                          Enable SMS Sending for this School
                        </label>
                      </div>
                      <small className="text-muted d-block mt-1">
                        When enabled, automated fee reminders and absenteeism notices are sent via EasySendSMS.
                      </small>
                    </div>

                    <div className="col-md-6">
                      <label className="edu-label">SMS Sender ID</label>
                      <input
                        type="text"
                        className="edu-input"
                        placeholder="e.g. SchoolStacks or Hillcrest"
                        maxLength={11}
                        value={smsSettings?.sender_id || ''}
                        onChange={(e) => setSmsSettings({ ...smsSettings, sender_id: e.target.value })}
                      />
                      <small className="text-muted">Maximum 11 alphanumeric characters approved on EasySendSMS.</small>
                    </div>

                    <div className="col-12"><hr /></div>

                    {/* Fee Reminders Settings */}
                    <div className="col-md-6">
                      <div className="form-check form-switch mb-2">
                        <input
                          className="form-check-input"
                          type="checkbox"
                          id="feeRemCheck"
                          checked={Boolean(smsSettings?.fee_reminders_enabled)}
                          onChange={(e) => setSmsSettings({ ...smsSettings, fee_reminders_enabled: e.target.checked })}
                        />
                        <label className="form-check-label fw-bold" htmlFor="feeRemCheck">
                          Automated Fee Reminders
                        </label>
                      </div>
                      <small className="text-muted d-block mb-3">
                        Triggers reminders 7 days before, on due date, and 7 days after due date. Excludes zero balances.
                      </small>

                      <label className="edu-label">Fee Reminder Template</label>
                      <textarea
                        className="edu-input"
                        rows={3}
                        value={smsSettings?.fee_reminder_template || ''}
                        onChange={(e) => setSmsSettings({ ...smsSettings, fee_reminder_template: e.target.value })}
                        placeholder="Variables: {school_name}, {student_name}, {balance}, {due_date}"
                      />
                      <small className="text-muted">Placeholders: <code>{'{school_name}'}</code>, <code>{'{student_name}'}</code>, <code>{'{balance}'}</code>, <code>{'{due_date}'}</code></small>
                    </div>

                    {/* Absenteeism Settings */}
                    <div className="col-md-6">
                      <div className="form-check form-switch mb-2">
                        <input
                          className="form-check-input"
                          type="checkbox"
                          id="absAlertCheck"
                          checked={Boolean(smsSettings?.absenteeism_alerts_enabled)}
                          onChange={(e) => setSmsSettings({ ...smsSettings, absenteeism_alerts_enabled: e.target.checked })}
                        />
                        <label className="form-check-label fw-bold" htmlFor="absAlertCheck">
                          Repeated Absenteeism Alerts
                        </label>
                      </div>
                      <small className="text-muted d-block mb-3">
                        Alerts parents when student accumulates unexplained absences. Excludes weekends, excused, and sick records.
                      </small>

                      <div className="row g-2 mb-2">
                        <div className="col-6">
                          <label className="edu-label">Consecutive Threshold</label>
                          <input
                            type="number"
                            className="edu-input"
                            min={1}
                            max={10}
                            value={smsSettings?.absenteeism_consecutive_days || 2}
                            onChange={(e) => setSmsSettings({ ...smsSettings, absenteeism_consecutive_days: Number(e.target.value) })}
                          />
                        </div>
                        <div className="col-6">
                          <label className="edu-label">Cumulative in 30 Days</label>
                          <input
                            type="number"
                            className="edu-input"
                            min={1}
                            max={30}
                            value={smsSettings?.absenteeism_cumulative_days || 5}
                            onChange={(e) => setSmsSettings({ ...smsSettings, absenteeism_cumulative_days: Number(e.target.value) })}
                          />
                        </div>
                      </div>

                      <label className="edu-label">Absenteeism Template</label>
                      <textarea
                        className="edu-input"
                        rows={2}
                        value={smsSettings?.absenteeism_template || ''}
                        onChange={(e) => setSmsSettings({ ...smsSettings, absenteeism_template: e.target.value })}
                        placeholder="Variables: {school_name}, {student_name}, {days}"
                      />
                      <small className="text-muted">Placeholders: <code>{'{school_name}'}</code>, <code>{'{student_name}'}</code>, <code>{'{days}'}</code></small>
                    </div>

                    <div className="col-12"><hr /></div>

                    <div className="col-md-6">
                      <div className="form-check form-switch">
                        <input
                          className="form-check-input"
                          type="checkbox"
                          id="subjAttCheck"
                          checked={Boolean(smsSettings?.enable_subject_attendance)}
                          onChange={(e) => setSmsSettings({ ...smsSettings, enable_subject_attendance: e.target.checked })}
                        />
                        <label className="form-check-label fw-bold" htmlFor="subjAttCheck">
                          Enable Optional Subject Attendance
                        </label>
                      </div>
                      <small className="text-muted d-block">
                        Allows subject teachers to record attendance per lesson period without altering daily class registers.
                      </small>
                    </div>

                    <div className="col-md-6">
                      <label className="edu-label">Daily Attendance Correction Window (Hours)</label>
                      <input
                        type="number"
                        className="edu-input"
                        min={1}
                        max={168}
                        value={smsSettings?.attendance_correction_window_hours || 24}
                        onChange={(e) => setSmsSettings({ ...smsSettings, attendance_correction_window_hours: Number(e.target.value) })}
                      />
                      <small className="text-muted">After this window, only school administrators can modify attendance.</small>
                    </div>

                    <div className="col-12 d-flex justify-content-end mt-4">
                      <Button type="submit" variant="accent" icon="bi-check-circle-fill">
                        Save SMS Settings
                      </Button>
                    </div>
                  </div>
                </form>
              )}
            </Card>
          )}

          {/* Sub-tab 2: Automated Fee Reminders */}
          {smsSubTab === 'reminders' && (
            <Card
              title="Automated School Fee Reminders"
              subtitle="Scans active student balances and schedules reminders based on due dates. Fully paid invoices are strictly excluded."
              actions={
                <div className="d-flex gap-2">
                  <Button size="sm" variant="outline" onClick={loadFeeReminders} icon="bi-search">
                    Scan & Preview
                  </Button>
                  <Button
                    size="sm"
                    variant="accent"
                    icon="bi-send-fill"
                    disabled={!feeRemindersPreview?.reminders?.length}
                    onClick={async () => {
                      if (!window.confirm(`Execute SMS reminder dispatch to ${feeRemindersPreview.reminders.length} parents?`)) return;
                      try {
                        const res = await apiFetch('/api/admin/sms/fee-reminders/run', { method: 'POST' });
                        setMessage(res.message);
                        loadFeeReminders();
                        loadSmsHistory();
                      } catch (err: any) {
                        setError(err.message);
                      }
                    }}
                  >
                    Execute Batch Send
                  </Button>
                </div>
              }
            >
              {feeRemindersLoading ? (
                <LoadingState message="Scanning outstanding fee balances..." />
              ) : (
                <>
                  <div className="d-flex align-items-center justify-content-between mb-3 p-3 bg-light rounded-3">
                    <div>
                      <strong>Eligible Reminders Found:</strong> {feeRemindersPreview?.count || 0} students
                    </div>
                    <div>
                      <strong>Total Outstanding:</strong> ZMW {Number(feeRemindersPreview?.total_outstanding || 0).toFixed(2)}
                    </div>
                  </div>

                  <DataTable
                    rows={feeRemindersPreview?.reminders || []}
                    columns={[
                      { header: 'Student Name', render: (r) => <span className="fw-bold">{r.student_name}</span> },
                      { header: 'Class', render: (r) => r.class_name },
                      { header: 'Guardian', render: (r) => r.parent_name },
                      { header: 'Guardian Phone', render: (r) => <span className="text-primary fw-semibold">{r.phone}</span> },
                      { header: 'Fee Total', render: (r) => `ZMW ${Number(r.total_fee).toFixed(2)}` },
                      { header: 'Outstanding Balance', render: (r) => <span className="text-danger fw-bold">ZMW {Number(r.balance).toFixed(2)}</span> },
                      { header: 'Reminder Stage', render: (r) => <Badge variant={r.stage?.includes('Overdue') ? 'danger' : 'mustard'}>{r.stage}</Badge> },
                      { header: 'Message Preview', render: (r) => <span className="small text-muted">{r.message}</span> },
                      {
                        header: 'Call',
                        render: (r) => (
                          <Button
                            size="sm"
                            variant="accent"
                            icon="bi-telephone-outbound-fill"
                            onClick={() => openCallParent(r)}
                          >
                            Call
                          </Button>
                        ),
                      },
                    ]}
                  />
                </>
              )}
            </Card>
          )}

          {/* Sub-tab 3: Repeated Absenteeism */}
          {smsSubTab === 'absenteeism' && (
            <Card
              title="Repeated Absenteeism Tracking & Escalations"
              subtitle="Monitors consecutive unexplained absences and 30-day cumulative trends to alert parents and flag intervention cases."
              actions={
                <div className="d-flex gap-2">
                  <Button size="sm" variant="outline" onClick={loadAbsenteeism} icon="bi-search">
                    Scan Absenteeism
                  </Button>
                  <Button
                    size="sm"
                    variant="accent"
                    icon="bi-send-exclamation-fill"
                    disabled={!absenteeismPreview?.alerts?.length}
                    onClick={async () => {
                      if (!window.confirm(`Run absenteeism sweep and dispatch alerts to parents?`)) return;
                      try {
                        const res = await apiFetch('/api/admin/sms/absenteeism/run', { method: 'POST' });
                        setMessage(res.message);
                        loadAbsenteeism();
                        loadSmsHistory();
                      } catch (err: any) {
                        setError(err.message);
                      }
                    }}
                  >
                    Run Sweep & Send Alerts
                  </Button>
                </div>
              }
            >
              {absenteeismLoading ? (
                <LoadingState message="Analyzing student attendance registers..." />
              ) : (
                <DataTable
                  rows={absenteeismPreview?.alerts || []}
                  columns={[
                    { header: 'Student Name', render: (a) => <span className="fw-bold">{a.student_name}</span> },
                    { header: 'Class', render: (a) => a.class_name },
                    { header: 'Consecutive Absences', render: (a) => <span className="fw-bold text-danger">{a.consecutive_absences} Days</span> },
                    { header: 'Cumulative (30 Days)', render: (a) => `${a.cumulative_absences} Days` },
                    {
                      header: 'Escalation Level',
                      render: (a) => {
                        let bVar: any = 'mustard';
                        if (a.level?.includes('Urgent')) bVar = 'danger';
                        if (a.level?.includes('Intervention')) bVar = 'danger';
                        return <Badge variant={bVar}>{a.level}</Badge>;
                      },
                    },
                    { header: 'Guardian Phone', render: (a) => a.phone || 'No phone' },
                    {
                      header: 'Actions',
                      render: (a) => (
                        <div className="d-flex gap-2">
                          <Button
                            size="sm"
                            variant="accent"
                            icon="bi-telephone-outbound-fill"
                            onClick={() => openCallParent(a)}
                          >
                            Call Parent
                          </Button>
                        </div>
                      ),
                    },
                  ]}
                />
              )}
            </Card>
          )}

          {/* Sub-tab 4: Message History */}
          {smsSubTab === 'history' && (
            <Card
              title="SMS Message Ledger & Delivery Status"
              subtitle="Audited outbound SMS records with real-time delivery status correlation"
              actions={
                <Button size="sm" variant="outline" onClick={loadSmsHistory} icon="bi-arrow-clockwise">
                  Reload Ledger
                </Button>
              }
            >
              <DataTable
                rows={smsHistory?.messages || []}
                columns={[
                  { header: 'Date & Time', render: (m) => (m.created_at ? new Date(m.created_at).toLocaleString() : '—') },
                  { header: 'Recipient Phone', render: (m) => <span className="fw-bold text-primary">{m.recipient_phone}</span> },
                  { header: 'Recipient Name', render: (m) => m.recipient_name || '—' },
                  { header: 'Category', render: (m) => <Badge variant="blue">{m.message_type}</Badge> },
                  { header: 'Message', render: (m) => <span className="small text-muted">{m.message_body?.slice(0, 45)}...</span> },
                  {
                    header: 'Status',
                    render: (m) => {
                      let bVar: any = 'neutral';
                      if (m.status === 'delivered') bVar = 'success';
                      else if (m.status === 'sent') bVar = 'blue';
                      else if (m.status === 'failed') bVar = 'danger';
                      return <Badge variant={bVar}>{m.status}</Badge>;
                    },
                  },
                  { header: 'Cost (ZMW)', render: (m) => Number(m.cost || 0).toFixed(4) },
                  { header: 'Provider ID', render: (m) => <span className="small text-muted">{m.provider_message_id || '—'}</span> },
                ]}
              />
            </Card>
          )}
        </>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          REGISTER STUDENT MODAL
         ══════════════════════════════════════════════════════════════════ */}
      <Modal
        open={studentModalOpen}
        title="Register New Student"
        onClose={() => setStudentModalOpen(false)}
        size="lg"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            // Validate student phone if provided
            if (stuForm.phone) {
              const res = validateZambianPhone(stuForm.phone, false);
              if (!res.valid) {
                setStudentPhoneError(res.error || null);
                return;
              }
            }
            // Validate parent phone if provided
            if (stuForm.parent_phone) {
              const res = validateZambianPhone(stuForm.parent_phone, false);
              if (!res.valid) {
                setParentPhoneError(res.error || null);
                return;
              }
            }
            handleAction('/api/admin/students', stuForm, () => {
              setStudentModalOpen(false);
              setStuForm({
                first_name: '',
                last_name: '',
                admission_no: '',
                gender: 'Female',
                class_id: '',
                phone: '',
                parent_username: '',
                parent_phone: '',
              });
              setStudentPhoneError(null);
              setParentPhoneError(null);
            });
          }}
        >
          <div className="row g-2">
            <div className="col-sm-6">
              <FormField label="First Name" required>
                <input
                  className="edu-input"
                  value={stuForm.first_name}
                  onChange={(e) => setStuForm({ ...stuForm, first_name: e.target.value })}
                  required
                />
              </FormField>
            </div>
            <div className="col-sm-6">
              <FormField label="Last Name" required>
                <input
                  className="edu-input"
                  value={stuForm.last_name}
                  onChange={(e) => setStuForm({ ...stuForm, last_name: e.target.value })}
                  required
                />
              </FormField>
            </div>
          </div>

          <div className="row g-2">
            <div className="col-sm-6">
              <FormField label="Admission Number" required>
                <input
                  className="edu-input"
                  placeholder="e.g. LH005"
                  value={stuForm.admission_no}
                  onChange={(e) => setStuForm({ ...stuForm, admission_no: e.target.value })}
                  required
                />
              </FormField>
            </div>
            <div className="col-sm-6">
              <FormField label="Gender" required>
                <select
                  className="edu-select"
                  value={stuForm.gender}
                  onChange={(e) => setStuForm({ ...stuForm, gender: e.target.value })}
                >
                  <option value="Female">Female</option>
                  <option value="Male">Male</option>
                </select>
              </FormField>
            </div>
          </div>

          <div className="row g-2">
            <div className="col-sm-6">
              <FormField label="Class Placement" required>
                <select
                  className="edu-select"
                  value={stuForm.class_id}
                  onChange={(e) => setStuForm({ ...stuForm, class_id: e.target.value })}
                  required
                >
                  <option value="">-- Select Class --</option>
                  {classes.map((c: any) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </FormField>
            </div>
            <div className="col-sm-6">
              <FormField
                label="Student Phone Number (Optional)"
                hint="e.g. 0977123456 or +260977123456 (spaces handled automatically)"
              >
                <input
                  className={`edu-input ${studentPhoneError ? 'is-invalid border-danger' : ''}`}
                  placeholder="0977123456"
                  value={stuForm.phone}
                  onChange={(e) => {
                    setStuForm({ ...stuForm, phone: e.target.value });
                    if (studentPhoneError) setStudentPhoneError(null);
                  }}
                  onBlur={() => {
                    if (stuForm.phone) {
                      const res = validateZambianPhone(stuForm.phone, false);
                      if (!res.valid) setStudentPhoneError(res.error || null);
                    }
                  }}
                />
                {studentPhoneError && (
                  <div className="text-danger small mt-1">{studentPhoneError}</div>
                )}
              </FormField>
            </div>
          </div>

          <div className="row g-2">
            <div className="col-sm-6">
              <FormField label="Parent Username (Optional)">
                <input
                  className="edu-input"
                  placeholder="parent_username"
                  value={stuForm.parent_username}
                  onChange={(e) => setStuForm({ ...stuForm, parent_username: e.target.value })}
                />
              </FormField>
            </div>
            <div className="col-sm-6">
              <FormField
                label="Parent Phone Number (Optional)"
                hint="e.g. 0977123456 or +260977123456"
              >
                <input
                  className={`edu-input ${parentPhoneError ? 'is-invalid border-danger' : ''}`}
                  placeholder="0977123456"
                  value={stuForm.parent_phone}
                  onChange={(e) => {
                    setStuForm({ ...stuForm, parent_phone: e.target.value });
                    if (parentPhoneError) setParentPhoneError(null);
                  }}
                  onBlur={() => {
                    if (stuForm.parent_phone) {
                      const res = validateZambianPhone(stuForm.parent_phone, false);
                      if (!res.valid) setParentPhoneError(res.error || null);
                    }
                  }}
                />
                {parentPhoneError && (
                  <div className="text-danger small mt-1">{parentPhoneError}</div>
                )}
              </FormField>
            </div>
          </div>

          <div className="d-flex justify-content-end gap-2 mt-3">
            <Button type="button" variant="outline" onClick={() => setStudentModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="accent">
              Register Student
            </Button>
          </div>
        </form>
      </Modal>

      {/* ══════════════════════════════════════════════════════════════════
          EDIT STUDENT MODAL
         ══════════════════════════════════════════════════════════════════ */}
      {studentToEdit && (
        <Modal
          open={Boolean(studentToEdit)}
          title={`Edit Student: ${studentToEdit.first_name} ${studentToEdit.last_name}`}
          onClose={() => setStudentToEdit(null)}
          size="lg"
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (studentToEdit.phone) {
                const res = validateZambianPhone(studentToEdit.phone, false);
                if (!res.valid) {
                  setEditStudentPhoneError(res.error || null);
                  return;
                }
              }
              if (studentToEdit.parent_phone) {
                const res = validateZambianPhone(studentToEdit.parent_phone, false);
                if (!res.valid) {
                  setEditParentPhoneError(res.error || null);
                  return;
                }
              }
              handleAction(
                `/api/admin/students/${studentToEdit.id}`,
                studentToEdit,
                () => setStudentToEdit(null),
                'PUT'
              );
            }}
          >
            <div className="row g-2">
              <div className="col-sm-6">
                <FormField label="First Name" required>
                  <input
                    className="edu-input"
                    value={studentToEdit.first_name}
                    onChange={(e) =>
                      setStudentToEdit({ ...studentToEdit, first_name: e.target.value })
                    }
                    required
                  />
                </FormField>
              </div>
              <div className="col-sm-6">
                <FormField label="Last Name" required>
                  <input
                    className="edu-input"
                    value={studentToEdit.last_name}
                    onChange={(e) =>
                      setStudentToEdit({ ...studentToEdit, last_name: e.target.value })
                    }
                    required
                  />
                </FormField>
              </div>
            </div>

            <div className="row g-2">
              <div className="col-sm-4">
                <FormField label="Admission Number" required>
                  <input
                    className="edu-input"
                    value={studentToEdit.admission_no}
                    onChange={(e) =>
                      setStudentToEdit({ ...studentToEdit, admission_no: e.target.value })
                    }
                    required
                  />
                </FormField>
              </div>
              <div className="col-sm-4">
                <FormField label="Class (Transfer Workflow)" required>
                  <select
                    className="edu-select"
                    value={studentToEdit.class_id}
                    onChange={(e) =>
                      setStudentToEdit({ ...studentToEdit, class_id: e.target.value })
                    }
                    required
                  >
                    {classes.map((c: any) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </FormField>
              </div>
              <div className="col-sm-4">
                <FormField label="Enrollment Status">
                  <select
                    className="edu-select"
                    value={studentToEdit.status || 'active'}
                    onChange={(e) =>
                      setStudentToEdit({ ...studentToEdit, status: e.target.value })
                    }
                  >
                    <option value="active">Active</option>
                    <option value="transferred">Transferred</option>
                    <option value="graduated">Graduated</option>
                    <option value="archived">Archived</option>
                  </select>
                </FormField>
              </div>
            </div>

            <div className="row g-2">
              <div className="col-sm-6">
                <FormField
                  label="Student Phone Number"
                  hint="e.g. 0977123456 or +260977123456"
                >
                  <input
                    className={`edu-input ${editStudentPhoneError ? 'is-invalid border-danger' : ''}`}
                    value={studentToEdit.phone || ''}
                    onChange={(e) => {
                      setStudentToEdit({ ...studentToEdit, phone: e.target.value });
                      if (editStudentPhoneError) setEditStudentPhoneError(null);
                    }}
                    onBlur={() => {
                      if (studentToEdit.phone) {
                        const res = validateZambianPhone(studentToEdit.phone, false);
                        if (!res.valid) setEditStudentPhoneError(res.error || null);
                      }
                    }}
                  />
                  {editStudentPhoneError && (
                    <div className="text-danger small mt-1">{editStudentPhoneError}</div>
                  )}
                </FormField>
              </div>
              <div className="col-sm-6">
                <FormField
                  label="Parent Phone Number"
                  hint="e.g. 0977123456 or +260977123456"
                >
                  <input
                    className={`edu-input ${editParentPhoneError ? 'is-invalid border-danger' : ''}`}
                    value={studentToEdit.parent_phone || ''}
                    onChange={(e) => {
                      setStudentToEdit({ ...studentToEdit, parent_phone: e.target.value });
                      if (editParentPhoneError) setEditParentPhoneError(null);
                    }}
                    onBlur={() => {
                      if (studentToEdit.parent_phone) {
                        const res = validateZambianPhone(studentToEdit.parent_phone, false);
                        if (!res.valid) setEditParentPhoneError(res.error || null);
                      }
                    }}
                  />
                  {editParentPhoneError && (
                    <div className="text-danger small mt-1">{editParentPhoneError}</div>
                  )}
                </FormField>
              </div>
            </div>

            <div className="d-flex justify-content-end gap-2 mt-3">
              <Button type="button" variant="outline" onClick={() => setStudentToEdit(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary">
                Save Changes
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {/* Delete Student Dialog */}
      {studentToDelete && (
        <ConfirmDialog
          open={Boolean(studentToDelete)}
          title="Delete / Archive Student"
          message={`Are you sure you want to delete ${studentToDelete.first_name} ${studentToDelete.last_name} (${studentToDelete.admission_no})? If the student has historical fees, marks, or attendance, the system will protect their audit history and prompt to archive them instead.`}
          confirmLabel="Delete Student"
          onClose={() => setStudentToDelete(null)}
          onConfirm={() => {
            handleAction(
              `/api/admin/students/${studentToDelete.id}`,
              {},
              () => setStudentToDelete(null),
              'DELETE'
            );
          }}
        />
      )}

      {/* ══════════════════════════════════════════════════════════════════
          REGISTER TEACHER MODAL
         ══════════════════════════════════════════════════════════════════ */}
      <Modal
        open={teacherModalOpen}
        title="Register New Teacher"
        onClose={() => setTeacherModalOpen(false)}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const phoneRes = validateZambianPhone(teaForm.phone, true);
            if (!phoneRes.valid) {
              setTeacherPhoneError(phoneRes.error || null);
              return;
            }
            handleAction(
              '/api/admin/teachers',
              { ...teaForm, phone: phoneRes.normalized },
              () => {
                setTeacherModalOpen(false);
                setTeaForm({
                  first_name: '',
                  last_name: '',
                  phone: '',
                  email: '',
                  subject_specialization: '',
                });
                setTeacherPhoneError(null);
              }
            );
          }}
        >
          <div className="row g-2">
            <div className="col-sm-6">
              <FormField label="First Name" required>
                <input
                  className="edu-input"
                  value={teaForm.first_name}
                  onChange={(e) => setTeaForm({ ...teaForm, first_name: e.target.value })}
                  required
                />
              </FormField>
            </div>
            <div className="col-sm-6">
              <FormField label="Last Name" required>
                <input
                  className="edu-input"
                  value={teaForm.last_name}
                  onChange={(e) => setTeaForm({ ...teaForm, last_name: e.target.value })}
                  required
                />
              </FormField>
            </div>
          </div>

          <FormField
            label="Phone Number"
            required
            hint="e.g. 0977123456 or +260977123456 (spaces and hyphens are accepted automatically)"
          >
            <input
              className={`edu-input ${teacherPhoneError ? 'is-invalid border-danger' : ''}`}
              placeholder="e.g. 0977123456"
              value={teaForm.phone}
              onChange={(e) => {
                setTeaForm({ ...teaForm, phone: e.target.value });
                if (teacherPhoneError) setTeacherPhoneError(null);
              }}
              onBlur={() => {
                if (teaForm.phone) {
                  const res = validateZambianPhone(teaForm.phone, true);
                  if (!res.valid) setTeacherPhoneError(res.error || null);
                }
              }}
              required
            />
            {teacherPhoneError && (
              <div className="text-danger small mt-1">{teacherPhoneError}</div>
            )}
          </FormField>

          <FormField label="Email Address (Optional)">
            <input
              type="email"
              className="edu-input"
              placeholder="teacher@school.zm"
              value={teaForm.email}
              onChange={(e) => setTeaForm({ ...teaForm, email: e.target.value })}
            />
          </FormField>

          <FormField label="Subject Specialization">
            <input
              className="edu-input"
              placeholder="e.g. Mathematics & Physics"
              value={teaForm.subject_specialization}
              onChange={(e) =>
                setTeaForm({ ...teaForm, subject_specialization: e.target.value })
              }
            />
          </FormField>

          <div className="d-flex justify-content-end gap-2 mt-3">
            <Button type="button" variant="outline" onClick={() => setTeacherModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="accent">
              Register Teacher
            </Button>
          </div>
        </form>
      </Modal>

      {/* ══════════════════════════════════════════════════════════════════
          EDIT TEACHER MODAL
         ══════════════════════════════════════════════════════════════════ */}
      {teacherToEdit && (
        <Modal
          open={Boolean(teacherToEdit)}
          title={`Edit Teacher: ${teacherToEdit.first_name} ${teacherToEdit.last_name}`}
          onClose={() => setTeacherToEdit(null)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const phoneRes = validateZambianPhone(teacherToEdit.phone, true);
              if (!phoneRes.valid) {
                setEditTeacherPhoneError(phoneRes.error || null);
                return;
              }
              handleAction(
                `/api/admin/teachers/${teacherToEdit.id}`,
                { ...teacherToEdit, phone: phoneRes.normalized },
                () => setTeacherToEdit(null),
                'PUT'
              );
            }}
          >
            <div className="row g-2">
              <div className="col-sm-6">
                <FormField label="First Name" required>
                  <input
                    className="edu-input"
                    value={teacherToEdit.first_name}
                    onChange={(e) =>
                      setTeacherToEdit({ ...teacherToEdit, first_name: e.target.value })
                    }
                    required
                  />
                </FormField>
              </div>
              <div className="col-sm-6">
                <FormField label="Last Name" required>
                  <input
                    className="edu-input"
                    value={teacherToEdit.last_name}
                    onChange={(e) =>
                      setTeacherToEdit({ ...teacherToEdit, last_name: e.target.value })
                    }
                    required
                  />
                </FormField>
              </div>
            </div>

            <FormField
              label="Phone Number"
              required
              hint="e.g. 0977123456 or +260977123456 (spaces handled automatically)"
            >
              <input
                className={`edu-input ${editTeacherPhoneError ? 'is-invalid border-danger' : ''}`}
                value={teacherToEdit.phone || ''}
                onChange={(e) => {
                  setTeacherToEdit({ ...teacherToEdit, phone: e.target.value });
                  if (editTeacherPhoneError) setEditTeacherPhoneError(null);
                }}
                onBlur={() => {
                  if (teacherToEdit.phone) {
                    const res = validateZambianPhone(teacherToEdit.phone, true);
                    if (!res.valid) setEditTeacherPhoneError(res.error || null);
                  }
                }}
                required
              />
              {editTeacherPhoneError && (
                <div className="text-danger small mt-1">{editTeacherPhoneError}</div>
              )}
            </FormField>

            <FormField label="Email Address">
              <input
                type="email"
                className="edu-input"
                value={teacherToEdit.email || ''}
                onChange={(e) =>
                  setTeacherToEdit({ ...teacherToEdit, email: e.target.value })
                }
              />
            </FormField>

            <FormField label="Subject Specialization">
              <input
                className="edu-input"
                value={teacherToEdit.subject_specialization || ''}
                onChange={(e) =>
                  setTeacherToEdit({ ...teacherToEdit, subject_specialization: e.target.value })
                }
              />
            </FormField>

            <div className="d-flex justify-content-end gap-2 mt-3">
              <Button type="button" variant="outline" onClick={() => setTeacherToEdit(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary">
                Save Teacher
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {/* Toggle Teacher Active Status Dialog */}
      {teacherToToggle && (
        <ConfirmDialog
          open={Boolean(teacherToToggle)}
          title={teacherToToggle.is_active ? 'Deactivate Teacher' : 'Reactivate Teacher'}
          message={
            teacherToToggle.is_active
              ? `Are you sure you want to deactivate ${teacherToToggle.first_name} ${teacherToToggle.last_name}? Inactive teachers are preserved for historical exam marks and reports, but cannot be assigned to new timetable slots.`
              : `Reactivate ${teacherToToggle.first_name} ${teacherToToggle.last_name}? They will be available for new timetable and classroom assignments.`
          }
          confirmLabel={teacherToToggle.is_active ? 'Deactivate' : 'Reactivate'}
          confirmVariant={teacherToToggle.is_active ? 'danger' : 'primary'}
          onClose={() => setTeacherToToggle(null)}
          onConfirm={() => {
            handleAction(
              `/api/admin/teachers/${teacherToToggle.id}/toggle-status`,
              {},
              () => setTeacherToToggle(null)
            );
          }}
        />
      )}

      {/* Delete Teacher Dialog */}
      {teacherToDelete && (
        <ConfirmDialog
          open={Boolean(teacherToDelete)}
          title="Delete Teacher"
          message={`Are you sure you want to permanently delete ${teacherToDelete.first_name} ${teacherToDelete.last_name} (${teacherToDelete.staff_no})? If this teacher is currently assigned to classes or timetables, the system will protect the records and advise deactivation instead.`}
          confirmLabel="Delete Teacher"
          onClose={() => setTeacherToDelete(null)}
          onConfirm={() => {
            handleAction(
              `/api/admin/teachers/${teacherToDelete.id}`,
              {},
              () => setTeacherToDelete(null),
              'DELETE'
            );
          }}
        />
      )}

      {/* ══════════════════════════════════════════════════════════════════
          EDIT CLASS MODAL & DELETE DIALOG
         ══════════════════════════════════════════════════════════════════ */}
      {classToEdit && (
        <Modal
          open={Boolean(classToEdit)}
          title={`Edit Class: ${classToEdit.name}`}
          onClose={() => setClassToEdit(null)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleAction(
                `/api/admin/classes/${classToEdit.id}`,
                classToEdit,
                () => setClassToEdit(null),
                'PUT'
              );
            }}
          >
            <FormField label="Class Name" required>
              <input
                className="edu-input"
                value={classToEdit.name}
                onChange={(e) => setClassToEdit({ ...classToEdit, name: e.target.value })}
                required
              />
            </FormField>
            <div className="row g-2">
              <div className="col-sm-6">
                <FormField label="Capacity" required>
                  <input
                    type="number"
                    className="edu-input"
                    value={classToEdit.capacity}
                    onChange={(e) => setClassToEdit({ ...classToEdit, capacity: e.target.value })}
                    required
                  />
                </FormField>
              </div>
              <div className="col-sm-6">
                <FormField label="Grade Level">
                  <input
                    className="edu-input"
                    placeholder="e.g. Grade 11"
                    value={classToEdit.grade_level || ''}
                    onChange={(e) =>
                      setClassToEdit({ ...classToEdit, grade_level: e.target.value })
                    }
                  />
                </FormField>
              </div>
            </div>
            <FormField label="Class Teacher">
              <select
                className="edu-select"
                value={classToEdit.class_teacher_id || ''}
                onChange={(e) =>
                  setClassToEdit({ ...classToEdit, class_teacher_id: e.target.value })
                }
              >
                <option value="">-- None Assigned --</option>
                {teachers
                  .filter((t: any) => t.is_active)
                  .map((t: any) => (
                    <option key={t.id} value={t.id}>
                      {t.first_name} {t.last_name}
                    </option>
                  ))}
              </select>
            </FormField>
            <div className="d-flex justify-content-end gap-2 mt-3">
              <Button type="button" variant="outline" onClick={() => setClassToEdit(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary">
                Save Class
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {classToDelete && (
        <ConfirmDialog
          open={Boolean(classToDelete)}
          title="Delete Class"
          message={`Are you sure you want to delete class '${classToDelete.name}'? If students or timetables are currently linked to this class, deletion will be safely rejected to prevent orphan records.`}
          confirmLabel="Delete Class"
          onClose={() => setClassToDelete(null)}
          onConfirm={() => {
            handleAction(
              `/api/admin/classes/${classToDelete.id}`,
              {},
              () => setClassToDelete(null),
              'DELETE'
            );
          }}
        />
      )}

      {/* ══════════════════════════════════════════════════════════════════
          EDIT SUBJECT MODAL & DELETE DIALOG
         ══════════════════════════════════════════════════════════════════ */}
      {subjectToEdit && (
        <Modal
          open={Boolean(subjectToEdit)}
          title={`Edit Subject: ${subjectToEdit.name}`}
          onClose={() => setSubjectToEdit(null)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleAction(
                `/api/admin/subjects/${subjectToEdit.id}`,
                subjectToEdit,
                () => setSubjectToEdit(null),
                'PUT'
              );
            }}
          >
            <FormField label="Subject Name" required>
              <input
                className="edu-input"
                value={subjectToEdit.name}
                onChange={(e) => setSubjectToEdit({ ...subjectToEdit, name: e.target.value })}
                required
              />
            </FormField>
            <FormField label="Subject Code" required>
              <input
                className="edu-input"
                value={subjectToEdit.code}
                onChange={(e) => setSubjectToEdit({ ...subjectToEdit, code: e.target.value })}
                required
              />
            </FormField>
            <FormField label="Description (Optional)">
              <textarea
                rows={3}
                className="edu-textarea"
                value={subjectToEdit.description || ''}
                onChange={(e) =>
                  setSubjectToEdit({ ...subjectToEdit, description: e.target.value })
                }
              />
            </FormField>
            <div className="d-flex justify-content-end gap-2 mt-3">
              <Button type="button" variant="outline" onClick={() => setSubjectToEdit(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary">
                Save Subject
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {subjectToDelete && (
        <ConfirmDialog
          open={Boolean(subjectToDelete)}
          title="Delete Subject"
          message={`Are you sure you want to delete subject '${subjectToDelete.name}' (${subjectToDelete.code})? If exam marks or timetable sessions exist, deletion will be blocked and you can archive it instead.`}
          confirmLabel="Delete Subject"
          onClose={() => setSubjectToDelete(null)}
          onConfirm={() => {
            handleAction(
              `/api/admin/subjects/${subjectToDelete.id}`,
              {},
              () => setSubjectToDelete(null),
              'DELETE'
            );
          }}
        />
      )}

      {/* ══════════════════════════════════════════════════════════════════
          EDIT TERM MODAL & DELETE DIALOG
         ══════════════════════════════════════════════════════════════════ */}
      {termToEdit && (
        <Modal
          open={Boolean(termToEdit)}
          title={`Edit Term: ${termToEdit.name}`}
          onClose={() => setTermToEdit(null)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (termToEdit.end_date <= termToEdit.start_date) {
                setError('End date must be after start date.');
                return;
              }
              handleAction(
                `/api/admin/terms/${termToEdit.id}`,
                termToEdit,
                () => setTermToEdit(null),
                'PUT'
              );
            }}
          >
            <FormField label="Term Name" required>
              <input
                className="edu-input"
                value={termToEdit.name}
                onChange={(e) => setTermToEdit({ ...termToEdit, name: e.target.value })}
                required
              />
            </FormField>
            <div className="row g-2">
              <div className="col-sm-6">
                <FormField label="Start Date" required>
                  <input
                    type="date"
                    className="edu-input"
                    value={termToEdit.start_date}
                    onChange={(e) =>
                      setTermToEdit({ ...termToEdit, start_date: e.target.value })
                    }
                    required
                  />
                </FormField>
              </div>
              <div className="col-sm-6">
                <FormField label="End Date" required>
                  <input
                    type="date"
                    className="edu-input"
                    value={termToEdit.end_date}
                    onChange={(e) =>
                      setTermToEdit({ ...termToEdit, end_date: e.target.value })
                    }
                    required
                  />
                </FormField>
              </div>
            </div>
            <div className="d-flex justify-content-end gap-2 mt-3">
              <Button type="button" variant="outline" onClick={() => setTermToEdit(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary">
                Save Term Dates
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {termToDelete && (
        <ConfirmDialog
          open={Boolean(termToDelete)}
          title="Delete Academic Term"
          message={`Are you sure you want to delete '${termToDelete.name}'? Existing exams, fee structures, and payments connected to this term cannot be orphaned.`}
          confirmLabel="Delete Term"
          onClose={() => setTermToDelete(null)}
          onConfirm={() => {
            handleAction(
              `/api/admin/terms/${termToDelete.id}`,
              {},
              () => setTermToDelete(null),
              'DELETE'
            );
          }}
        />
      )}

      {/* ══════════════════════════════════════════════════════════════════
          EDIT EXAM MODAL & DELETE DIALOG
         ══════════════════════════════════════════════════════════════════ */}
      {examToEdit && (
        <Modal
          open={Boolean(examToEdit)}
          title={`Edit / Reschedule Exam: ${examToEdit.name}`}
          onClose={() => setExamToEdit(null)}
          size="lg"
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const sDate = examToEdit.start_date || examToEdit.date;
              const eDate = examToEdit.end_date || sDate;
              if (sDate && eDate && eDate < sDate) {
                setError('Exam end date cannot be earlier than start date.');
                return;
              }
              if (examToEdit.start_time && examToEdit.end_time && examToEdit.end_time <= examToEdit.start_time) {
                setError('Exam end time must be after start time.');
                return;
              }
              handleAction(
                `/api/admin/exams/${examToEdit.id}`,
                { ...examToEdit, start_date: sDate, end_date: eDate, date: sDate },
                () => setExamToEdit(null),
                'PUT'
              );
            }}
          >
            <div className="row g-2">
              <div className="col-sm-6">
                <FormField label="Exam Name" required>
                  <input
                    className="edu-input"
                    value={examToEdit.name}
                    onChange={(e) => setExamToEdit({ ...examToEdit, name: e.target.value })}
                    required
                  />
                </FormField>
              </div>
              <div className="col-sm-6">
                <FormField label="Academic Term" required>
                  <select
                    className="edu-select"
                    value={examToEdit.term_id}
                    onChange={(e) => setExamToEdit({ ...examToEdit, term_id: e.target.value })}
                    required
                  >
                    {terms.map((t: any) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </FormField>
              </div>
            </div>

            <div className="row g-2">
              <div className="col-sm-6">
                <FormField label="Class">
                  <select
                    className="edu-select"
                    value={examToEdit.class_id || ''}
                    onChange={(e) => setExamToEdit({ ...examToEdit, class_id: e.target.value })}
                  >
                    <option value="">-- All Classes --</option>
                    {classes.map((c: any) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </FormField>
              </div>
              <div className="col-sm-6">
                <FormField label="Subject">
                  <select
                    className="edu-select"
                    value={examToEdit.subject_id || ''}
                    onChange={(e) => setExamToEdit({ ...examToEdit, subject_id: e.target.value })}
                  >
                    <option value="">-- All Subjects --</option>
                    {subjects.map((s: any) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </FormField>
              </div>
            </div>

            <div className="row g-2">
              <div className="col-sm-3">
                <FormField label="Start Date">
                  <input
                    type="date"
                    className="edu-input"
                    value={examToEdit.start_date || examToEdit.date || ''}
                    onChange={(e) => setExamToEdit({ ...examToEdit, start_date: e.target.value, date: e.target.value })}
                  />
                </FormField>
              </div>
              <div className="col-sm-3">
                <FormField label="End Date">
                  <input
                    type="date"
                    className="edu-input"
                    value={examToEdit.end_date || examToEdit.start_date || examToEdit.date || ''}
                    onChange={(e) => setExamToEdit({ ...examToEdit, end_date: e.target.value })}
                  />
                </FormField>
              </div>
              <div className="col-sm-3">
                <FormField label="Start Time">
                  <input
                    type="time"
                    className="edu-input"
                    value={examToEdit.start_time || ''}
                    onChange={(e) => setExamToEdit({ ...examToEdit, start_time: e.target.value })}
                  />
                </FormField>
              </div>
              <div className="col-sm-3">
                <FormField label="End Time">
                  <input
                    type="time"
                    className="edu-input"
                    value={examToEdit.end_time || ''}
                    onChange={(e) => setExamToEdit({ ...examToEdit, end_time: e.target.value })}
                  />
                </FormField>
              </div>
            </div>

            <div className="row g-2">
              <div className="col-sm-6">
                <FormField label="Venue / Hall">
                  <input
                    className="edu-input"
                    placeholder="e.g. Main Hall"
                    value={examToEdit.venue || ''}
                    onChange={(e) => setExamToEdit({ ...examToEdit, venue: e.target.value })}
                  />
                </FormField>
              </div>
              <div className="col-sm-6">
                <FormField label="Exam Status">
                  <select
                    className="edu-select"
                    value={examToEdit.status || 'scheduled'}
                    onChange={(e) => setExamToEdit({ ...examToEdit, status: e.target.value })}
                  >
                    <option value="scheduled">Scheduled</option>
                    <option value="completed">Completed</option>
                    <option value="cancelled">Cancelled</option>
                  </select>
                </FormField>
              </div>
            </div>

            <div className="d-flex justify-content-end gap-2 mt-3">
              <Button type="button" variant="outline" onClick={() => setExamToEdit(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary">
                Save Exam Details
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {examToDelete && (
        <ConfirmDialog
          open={Boolean(examToDelete)}
          title="Delete / Cancel Exam"
          message={`Are you sure you want to delete exam '${examToDelete.name}'? If student marks have already been recorded, deletion will be prevented and you can set its status to 'cancelled' instead.`}
          confirmLabel="Delete Exam"
          onClose={() => setExamToDelete(null)}
          onConfirm={() => {
            handleAction(
              `/api/admin/exams/${examToDelete.id}`,
              {},
              () => setExamToDelete(null),
              'DELETE'
            );
          }}
        />
      )}

      {/* ── Provision Parent Modal ── */}
      {parentModalOpen && (
        <Modal
          open={parentModalOpen}
          title="Provision New Parent Account"
          onClose={() => setParentModalOpen(false)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleAction(
                '/api/admin/parents',
                {
                  ...parentForm,
                  student_ids: parentForm.student_id ? [parentForm.student_id] : [],
                },
                () => setParentModalOpen(false)
              );
            }}
          >
            <div className="row g-2">
              <div className="col-sm-6">
                <FormField label="First Name" required>
                  <input
                    className="edu-input"
                    value={parentForm.first_name}
                    onChange={(e) => setParentForm({ ...parentForm, first_name: e.target.value })}
                    required
                  />
                </FormField>
              </div>
              <div className="col-sm-6">
                <FormField label="Last Name" required>
                  <input
                    className="edu-input"
                    value={parentForm.last_name}
                    onChange={(e) => setParentForm({ ...parentForm, last_name: e.target.value })}
                    required
                  />
                </FormField>
              </div>
            </div>
            <div className="row g-2">
              <div className="col-sm-6">
                <FormField label="Phone Number (e.g. 0977112233)" required>
                  <input
                    className="edu-input"
                    value={parentForm.phone}
                    onChange={(e) => setParentForm({ ...parentForm, phone: e.target.value })}
                    required
                  />
                </FormField>
              </div>
              <div className="col-sm-6">
                <FormField label="Email Address">
                  <input
                    type="email"
                    className="edu-input"
                    value={parentForm.email}
                    onChange={(e) => setParentForm({ ...parentForm, email: e.target.value })}
                  />
                </FormField>
              </div>
            </div>
            <div className="row g-2">
              <div className="col-sm-6">
                <FormField label="Username (Optional)">
                  <input
                    className="edu-input"
                    placeholder="Defaults to phone"
                    value={parentForm.username}
                    onChange={(e) => setParentForm({ ...parentForm, username: e.target.value })}
                  />
                </FormField>
              </div>
              <div className="col-sm-6">
                <FormField label="Initial Password" required>
                  <PasswordInput
                    value={parentForm.password}
                    onChange={(e) => setParentForm({ ...parentForm, password: e.target.value })}
                    required
                  />
                </FormField>
              </div>
            </div>
            <FormField label="Link Student / Child (Optional)">
              <select
                className="edu-select"
                value={parentForm.student_id}
                onChange={(e) => setParentForm({ ...parentForm, student_id: e.target.value })}
              >
                <option value="">-- Select Child to Link --</option>
                {students.map((s: any) => (
                  <option key={s.id} value={s.id}>
                    {s.first_name} {s.last_name} ({s.admission_no} - {s.class_name})
                  </option>
                ))}
              </select>
            </FormField>
            <div className="d-flex justify-content-end gap-2 mt-3">
              <Button type="button" variant="outline" onClick={() => setParentModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" icon="bi-person-check-fill">
                Provision Account
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {/* ── Link Child Modal ── */}
      {linkModalParent && (
        <Modal
          open={Boolean(linkModalParent)}
          title={`Manage Child Links for ${linkModalParent.first_name} ${linkModalParent.last_name}`}
          onClose={() => setLinkModalParent(null)}
        >
          <div className="mb-3">
            <h6 className="fw-bold mb-2">Currently Linked Children:</h6>
            {(linkModalParent.linked_students || []).length > 0 ? (
              <div className="d-flex flex-column gap-2 mb-3">
                {linkModalParent.linked_students.map((st: any) => (
                  <div key={st.id} className="p-2 border rounded d-flex justify-content-between align-items-center">
                    <div>
                      <span className="fw-semibold">{st.name || `${st.first_name} ${st.last_name}`}</span>{' '}
                      <span className="text-muted small">({st.admission_no} • {st.class_name})</span>
                    </div>
                    <Button
                      size="sm"
                      variant="danger"
                      icon="bi-x"
                      onClick={() => {
                        handleAction(
                          `/api/admin/parents/${linkModalParent.id}/link-student`,
                          { student_id: st.id, action: 'unlink' },
                          () => setLinkModalParent(null)
                        );
                      }}
                    >
                      Unlink
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-muted small mb-3">No students linked to this parent profile yet.</div>
            )}

            <div className="border-top pt-3">
              <label className="edu-label mb-1">Link an Enrolled Student:</label>
              <div className="d-flex gap-2">
                <select
                  className="edu-select"
                  value={linkStudentId}
                  onChange={(e) => setLinkStudentId(e.target.value)}
                >
                  <option value="">-- Choose Student --</option>
                  {students.map((s: any) => (
                    <option key={s.id} value={s.id}>
                      {s.first_name} {s.last_name} ({s.admission_no} • {s.class_name})
                    </option>
                  ))}
                </select>
                <Button
                  variant="primary"
                  size="sm"
                  disabled={!linkStudentId}
                  icon="bi-plus-circle"
                  onClick={() => {
                    handleAction(
                      `/api/admin/parents/${linkModalParent.id}/link-student`,
                      { student_id: linkStudentId, action: 'link' },
                      () => setLinkModalParent(null)
                    );
                  }}
                >
                  Link
                </Button>
              </div>
            </div>
          </div>
          <div className="d-flex justify-content-end">
            <Button variant="outline" onClick={() => setLinkModalParent(null)}>
              Close
            </Button>
          </div>
        </Modal>
      )}

      {/* ── Reset Password Modal ── */}
      {resetPassParent && (
        <Modal
          open={Boolean(resetPassParent)}
          title={`Reset Password for ${resetPassParent.first_name} ${resetPassParent.last_name}`}
          onClose={() => setResetPassParent(null)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleAction(
                `/api/admin/parents/${resetPassParent.id}/reset-password`,
                { password: newParentPass },
                () => setResetPassParent(null)
              );
            }}
          >
            <FormField label="New Password (min 6 characters)" required>
              <PasswordInput
                minLength={6}
                value={newParentPass}
                onChange={(e) => setNewParentPass(e.target.value)}
                required
              />
            </FormField>
            <div className="d-flex justify-content-end gap-2 mt-3">
              <Button type="button" variant="outline" onClick={() => setResetPassParent(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" icon="bi-key-fill">
                Update Password
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          EDIT TIMETABLE MODAL & DELETE DIALOG
         ══════════════════════════════════════════════════════════════════ */}
      {timetableToEdit && (
        <Modal
          open={Boolean(timetableToEdit)}
          title={`Edit Timetable Slot: ${timetableToEdit.class_name} – ${timetableToEdit.subject_name}`}
          onClose={() => setTimetableToEdit(null)}
        >
          {timetableClashError && (
            <div className="alert alert-danger p-2 small mb-3">
              <i className="bi bi-exclamation-triangle-fill me-1" />
              {timetableClashError}
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (timetableToEdit.end_time <= timetableToEdit.start_time) {
                setError('End time must be after start time.');
                return;
              }
              handleAction(
                `/api/admin/timetable/${timetableToEdit.id}`,
                timetableToEdit,
                () => setTimetableToEdit(null),
                'PUT'
              );
            }}
          >
            <FormField label="Class" required>
              <select
                className="edu-select"
                value={timetableToEdit.class_id}
                onChange={(e) =>
                  setTimetableToEdit({ ...timetableToEdit, class_id: e.target.value })
                }
                required
              >
                {classes.map((c: any) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label="Subject" required>
              <select
                className="edu-select"
                value={timetableToEdit.subject_id}
                onChange={(e) =>
                  setTimetableToEdit({ ...timetableToEdit, subject_id: e.target.value })
                }
                required
              >
                {subjects.map((s: any) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.code})
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label="Teacher" required>
              <select
                className="edu-select"
                value={timetableToEdit.teacher_id}
                onChange={(e) =>
                  setTimetableToEdit({ ...timetableToEdit, teacher_id: e.target.value })
                }
                required
              >
                {teachers.map((t: any) => (
                  <option key={t.id} value={t.id}>
                    {t.first_name} {t.last_name}
                  </option>
                ))}
              </select>
            </FormField>

            <div className="row g-2 mb-3">
              <div className="col-sm-6">
                <label className="edu-label">Day of Week</label>
                <select
                  className="edu-select"
                  value={timetableToEdit.day}
                  onChange={(e) =>
                    setTimetableToEdit({ ...timetableToEdit, day: e.target.value })
                  }
                >
                  {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'].map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-sm-6">
                <label className="edu-label">Room / Venue</label>
                <input
                  className="edu-input"
                  value={timetableToEdit.room || ''}
                  onChange={(e) =>
                    setTimetableToEdit({ ...timetableToEdit, room: e.target.value })
                  }
                />
              </div>
            </div>

            <div className="row g-2 mb-3">
              <div className="col-6">
                <label className="edu-label">Start Time</label>
                <input
                  type="time"
                  className="edu-input"
                  value={timetableToEdit.start_time}
                  onChange={(e) =>
                    setTimetableToEdit({ ...timetableToEdit, start_time: e.target.value })
                  }
                  required
                />
              </div>
              <div className="col-6">
                <label className="edu-label">End Time</label>
                <input
                  type="time"
                  className="edu-input"
                  value={timetableToEdit.end_time}
                  onChange={(e) =>
                    setTimetableToEdit({ ...timetableToEdit, end_time: e.target.value })
                  }
                  required
                />
              </div>
            </div>

            <div className="d-flex justify-content-end gap-2 mt-3">
              <Button type="button" variant="outline" onClick={() => setTimetableToEdit(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary">
                Update Slot
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {timetableToDelete && (
        <ConfirmDialog
          open={Boolean(timetableToDelete)}
          title="Delete Timetable Slot"
          message={`Are you sure you want to remove the ${timetableToDelete.subject_name} session for ${timetableToDelete.class_name} on ${timetableToDelete.day} (${timetableToDelete.start_time} - ${timetableToDelete.end_time})?`}
          confirmLabel="Delete Slot"
          onClose={() => setTimetableToDelete(null)}
          onConfirm={() => {
            handleAction(
              `/api/admin/timetable/${timetableToDelete.id}`,
              {},
              () => setTimetableToDelete(null),
              'DELETE'
            );
          }}
        />
      )}

      {/* ══════════════════════════════════════════════════════════════════
          MANUAL PAYMENT MODAL
         ══════════════════════════════════════════════════════════════════ */}
      {payModalStudent && (
        <Modal
          open={Boolean(payModalStudent)}
          title={`Record Fee: ${payModalStudent.first_name} ${payModalStudent.last_name}`}
          onClose={() => setPayModalStudent(null)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleAction(
                '/api/admin/manual-payment',
                {
                  ...manualPayForm,
                  student_id: payModalStudent.id,
                },
                () => {
                  setPayModalStudent(null);
                  setManualPayForm({
                    term_id: '',
                    amount: '',
                    bank_reference: '',
                    payment_date: new Date().toISOString().slice(0, 10),
                  });
                }
              );
            }}
          >
            <FormField label="Term">
              <select
                className="edu-select"
                value={manualPayForm.term_id}
                onChange={(e) =>
                  setManualPayForm({ ...manualPayForm, term_id: e.target.value })
                }
                required
              >
                <option value="">-- Select Term --</option>
                {terms.map((t: any) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField label="Amount Paid (ZMW)">
              <input
                type="number"
                step="0.01"
                className="edu-input"
                placeholder="2500.00"
                value={manualPayForm.amount}
                onChange={(e) =>
                  setManualPayForm({ ...manualPayForm, amount: e.target.value })
                }
                required
              />
            </FormField>
            <FormField label="Bank Reference / Deposit Slip No">
              <input
                className="edu-input"
                placeholder="DEP-123456"
                value={manualPayForm.bank_reference}
                onChange={(e) =>
                  setManualPayForm({ ...manualPayForm, bank_reference: e.target.value })
                }
                required
              />
            </FormField>
            <FormField label="Payment Date">
              <input
                type="date"
                className="edu-input"
                value={manualPayForm.payment_date}
                onChange={(e) =>
                  setManualPayForm({ ...manualPayForm, payment_date: e.target.value })
                }
                required
              />
            </FormField>
            <div className="d-flex justify-content-end gap-2 mt-3">
              <Button type="button" variant="outline" onClick={() => setPayModalStudent(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="accent" icon="bi-check-circle">
                Confirm Payment
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          ATTENDANCE CORRECTION MODAL
         ══════════════════════════════════════════════════════════════════ */}
      {attCorrectStudent && (
        <Modal
          open={!!attCorrectStudent}
          title={`Correct Attendance Record: ${attCorrectStudent.name}`}
          onClose={() => setAttCorrectStudent(null)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleAction(
                '/api/admin/attendance/correct',
                {
                  student_id: attCorrectStudent.id,
                  date: attDate,
                  status: attCorrectStatus,
                  remarks: attCorrectRemarks,
                  reason: attCorrectReason,
                },
                () => {
                  setAttCorrectStudent(null);
                  loadAttendance(attDate, attClassId);
                }
              );
            }}
          >
            <div className="mb-3">
              <label className="edu-label">Attendance Status</label>
              <select
                className="edu-select"
                value={attCorrectStatus}
                onChange={(e) => setAttCorrectStatus(e.target.value)}
                required
              >
                <option value="Present">Present</option>
                <option value="Late">Late</option>
                <option value="Absent">Absent</option>
                <option value="Excused">Excused</option>
                <option value="Sick">Sick</option>
              </select>
            </div>
            <FormField label="Remarks / Note">
              <input
                className="edu-input"
                value={attCorrectRemarks}
                onChange={(e) => setAttCorrectRemarks(e.target.value)}
                placeholder="Optional student remark (e.g. Parent notified in advance)"
              />
            </FormField>
            <FormField label="Administrative Reason (Required for Audit Trail)">
              <textarea
                rows={2}
                className="edu-textarea"
                value={attCorrectReason}
                onChange={(e) => setAttCorrectReason(e.target.value)}
                placeholder="Specify reason for correcting historical attendance record"
                required
              />
            </FormField>
            <div className="d-flex justify-content-end gap-2 mt-4">
              <Button type="button" variant="outline" onClick={() => setAttCorrectStudent(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" icon="bi-check2-circle">
                Save Attendance Correction
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          ASSIGN CLASS TEACHER MODAL (WITH 1-CLASS POLICY & OVERRIDE)
         ══════════════════════════════════════════════════════════════════ */}
      {assignCtModal && (
        <Modal
          open={Boolean(assignCtModal)}
          title="Assign Designated Class Teacher"
          onClose={() => setAssignCtModal(null)}
          size="md"
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await apiFetch('/api/admin/class-teachers', {
                  method: 'POST',
                  body: JSON.stringify(assignCtModal),
                });
                setMessage('Class Teacher assigned successfully.');
                setAssignCtModal(null);
                loadClassTeachers();
              } catch (err: any) {
                if (err.requires_override) {
                  setAssignCtModal((prev: any) => ({
                    ...prev,
                    is_override: true,
                    conflict_message: err.message,
                  }));
                } else {
                  setError(err.message);
                }
              }
            }}
          >
            <div className="mb-3">
              <label className="edu-label">Academic Year</label>
              <input
                type="text"
                className="edu-input"
                value={assignCtModal.academic_year}
                onChange={(e) => setAssignCtModal({ ...assignCtModal, academic_year: e.target.value })}
                required
              />
            </div>

            <div className="mb-3">
              <label className="edu-label">Select Class</label>
              <select
                className="edu-select"
                value={assignCtModal.class_id}
                onChange={(e) => setAssignCtModal({ ...assignCtModal, class_id: e.target.value })}
                required
              >
                <option value="">-- Select Class --</option>
                {classes.map((c: any) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="mb-3">
              <label className="edu-label">Select Designated Teacher</label>
              <select
                className="edu-select"
                value={assignCtModal.teacher_id}
                onChange={(e) => {
                  const tid = Number(e.target.value);
                  const conflict = ctData?.allocations?.find((a: any) => a.teacher_id === tid && Number(a.class_id) !== Number(assignCtModal.class_id));
                  setAssignCtModal({
                    ...assignCtModal,
                    teacher_id: e.target.value,
                    conflict_message: conflict ? `Teacher is already Class Teacher for ${conflict.class_name}. 1-class-per-teacher policy applies.` : null,
                  });
                }}
                required
              >
                <option value="">-- Select Teacher --</option>
                {teachers.map((t: any) => (
                  <option key={t.id} value={t.id}>
                    {t.first_name} {t.last_name} ({t.staff_no || t.subject_specialization || 'Staff'})
                  </option>
                ))}
              </select>
            </div>

            {assignCtModal.conflict_message && (
              <div className="alert alert-warning p-2 small mb-3">
                <i className="bi bi-shield-exclamation me-1" />
                <strong>Policy Conflict:</strong> {assignCtModal.conflict_message}
              </div>
            )}

            {assignCtModal.is_override && (
              <div className="p-3 mb-3 border border-warning rounded-3 bg-warning-subtle">
                <div className="form-check mb-2">
                  <input
                    className="form-check-input"
                    type="checkbox"
                    id="overrideCheck"
                    checked={assignCtModal.is_override}
                    onChange={(e) => setAssignCtModal({ ...assignCtModal, is_override: e.target.checked })}
                  />
                  <label className="form-check-label fw-bold small" htmlFor="overrideCheck">
                    Authorize Administrative Multi-Class Override
                  </label>
                </div>
                <label className="edu-label">Override Reason (Required)</label>
                <textarea
                  className="edu-input"
                  rows={2}
                  required
                  placeholder="State the administrative reason (e.g. temporary staff shortage, department head assignment)..."
                  value={assignCtModal.override_reason || ''}
                  onChange={(e) => setAssignCtModal({ ...assignCtModal, override_reason: e.target.value })}
                />
              </div>
            )}

            <div className="d-flex justify-content-end gap-2 mt-4">
              <Button type="button" variant="outline" onClick={() => setAssignCtModal(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="accent" icon="bi-check-circle-fill">
                Confirm Allocation
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          ASSIGN SUBSTITUTE TEACHER MODAL
         ══════════════════════════════════════════════════════════════════ */}
      {assignSubModal && (
        <Modal
          open={Boolean(assignSubModal)}
          title="Assign Temporary Substitute Teacher"
          onClose={() => setAssignSubModal(null)}
          size="md"
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await apiFetch('/api/admin/substitutes', {
                  method: 'POST',
                  body: JSON.stringify(assignSubModal),
                });
                setMessage('Substitute teacher assigned successfully.');
                setAssignSubModal(null);
                loadSubstitutes();
              } catch (err: any) {
                setError(err.message);
              }
            }}
          >
            <div className="mb-3">
              <label className="edu-label">Select Class</label>
              <select
                className="edu-select"
                value={assignSubModal.class_id}
                onChange={(e) => setAssignSubModal({ ...assignSubModal, class_id: e.target.value })}
                required
              >
                <option value="">-- Select Class --</option>
                {classes.map((c: any) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="mb-3">
              <label className="edu-label">Substitute Teacher</label>
              <select
                className="edu-select"
                value={assignSubModal.substitute_teacher_id}
                onChange={(e) => setAssignSubModal({ ...assignSubModal, substitute_teacher_id: e.target.value })}
                required
              >
                <option value="">-- Select Substitute --</option>
                {teachers.map((t: any) => (
                  <option key={t.id} value={t.id}>
                    {t.first_name} {t.last_name}
                  </option>
                ))}
              </select>
            </div>

            <div className="row g-2 mb-3">
              <div className="col-6">
                <label className="edu-label">Start Date</label>
                <input
                  type="date"
                  className="edu-input"
                  value={assignSubModal.start_date}
                  onChange={(e) => setAssignSubModal({ ...assignSubModal, start_date: e.target.value })}
                  required
                />
              </div>
              <div className="col-6">
                <label className="edu-label">End Date</label>
                <input
                  type="date"
                  className="edu-input"
                  value={assignSubModal.end_date}
                  onChange={(e) => setAssignSubModal({ ...assignSubModal, end_date: e.target.value })}
                  required
                />
              </div>
            </div>

            <div className="mb-3">
              <label className="edu-label">Reason for Substitution</label>
              <input
                type="text"
                className="edu-input"
                placeholder="e.g. Maternity leave, official conference, sick leave"
                value={assignSubModal.reason}
                onChange={(e) => setAssignSubModal({ ...assignSubModal, reason: e.target.value })}
                required
              />
            </div>

            <div className="d-flex justify-content-end gap-2 mt-4">
              <Button type="button" variant="outline" onClick={() => setAssignSubModal(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="accent">
                Authorize Substitute
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          SEND TEST SMS MODAL
         ══════════════════════════════════════════════════════════════════ */}
      {testSmsModal && (
        <Modal
          open={Boolean(testSmsModal)}
          title="Send Test SMS Notification"
          onClose={() => setTestSmsModal(null)}
          size="md"
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                const res = await apiFetch('/api/admin/sms/send-test', {
                  method: 'POST',
                  body: JSON.stringify({
                    phone_number: testSmsModal.phone,
                    message: testSmsModal.message,
                  }),
                });
                setMessage(`Test SMS sent! Provider status: ${res.status}${res.dry_run ? ' (Dry-Run Simulation)' : ''}`);
                setTestSmsModal(null);
                loadSmsHistory();
              } catch (err: any) {
                setError(err.message);
              }
            }}
          >
            <div className="mb-3">
              <label className="edu-label">Recipient Phone Number</label>
              <input
                type="text"
                className="edu-input"
                placeholder="+26097XXXXXXX or 097XXXXXXX"
                value={testSmsModal.phone}
                onChange={(e) => setTestSmsModal({ ...testSmsModal, phone: e.target.value })}
                required
              />
              <small className="text-muted">Enter Zambian or international mobile number.</small>
            </div>

            <div className="mb-3">
              <label className="edu-label">Test Message Content</label>
              <textarea
                className="edu-input"
                rows={3}
                value={testSmsModal.message}
                onChange={(e) => setTestSmsModal({ ...testSmsModal, message: e.target.value })}
                required
              />
            </div>

            <div className="d-flex justify-content-end gap-2 mt-4">
              <Button type="button" variant="outline" onClick={() => setTestSmsModal(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="accent" icon="bi-send-fill">
                Dispatch Test SMS
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          CALL PARENT & LOGGING MODAL
         ══════════════════════════════════════════════════════════════════ */}
      {callModal && (
        <Modal
          open={Boolean(callModal)}
          title="Direct Guardian Call & Communication Log"
          onClose={() => setCallModal(null)}
          size="lg"
        >
          <div className="row g-4">
            <div className="col-md-5 border-end">
              <div className="p-3 bg-light rounded-3 mb-3">
                <div className="small text-muted text-uppercase fw-bold mb-1">Student Details</div>
                <h5 className="fw-bold text-dark mb-1">{callModal.studentName}</h5>
                <div className="text-muted small">Class: {callModal.className || '—'}</div>
              </div>

              <div className="p-3 border rounded-3 mb-3">
                <div className="small text-muted text-uppercase fw-bold mb-1">Primary Guardian</div>
                <div className="fw-bold text-dark mb-1">{callModal.parentName}</div>
                <div className="text-primary fw-bold mb-2">{callModal.phone || 'No phone recorded'}</div>

                {callModal.phone ? (
                  <a
                    href={`tel:${callModal.phone}`}
                    className="btn btn-primary w-100 fw-bold d-flex align-items-center justify-content-center gap-2 py-2"
                    style={{ backgroundColor: '#002583', borderRadius: '0.5rem' }}
                  >
                    <i className="bi bi-telephone-outbound-fill" />
                    Call Guardian Now
                  </a>
                ) : (
                  <button type="button" className="btn btn-secondary w-100" disabled>
                    No Phone Number
                  </button>
                )}
              </div>

              {callModal.calls && callModal.calls.length > 0 && (
                <div>
                  <div className="small text-muted text-uppercase fw-bold mb-2">Previous Staff Calls</div>
                  <div className="d-flex flex-column gap-2" style={{ maxHeight: '160px', overflowY: 'auto' }}>
                    {callModal.calls.map((c: any) => (
                      <div key={c.id} className="p-2 border rounded-2 small bg-white">
                        <div className="d-flex justify-content-between">
                          <span className="fw-bold">{c.status}</span>
                          <span className="text-muted" style={{ fontSize: '0.7rem' }}>{c.created_at ? new Date(c.created_at).toLocaleDateString() : ''}</span>
                        </div>
                        <div className="text-muted text-truncate">{c.remarks || c.reason}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="col-md-7">
              <h6 className="fw-bold text-dark mb-3">Log Call Outcome & Staff Remarks</h6>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleLogCall();
                }}
              >
                <div className="mb-3">
                  <label className="edu-label">Call Reason</label>
                  <select
                    className="edu-select"
                    value={callModal.reason}
                    onChange={(e) => setCallModal({ ...callModal, reason: e.target.value })}
                  >
                    <option value="Absenteeism Follow-up">Absenteeism Follow-up</option>
                    <option value="Fee Balance Collection">Fee Balance Collection</option>
                    <option value="Academic Performance">Academic Performance</option>
                    <option value="Disciplinary Concern">Disciplinary Concern</option>
                    <option value="Health / Medical Emergency">Health / Medical Emergency</option>
                    <option value="General Pastoral Welfare">General Pastoral Welfare</option>
                  </select>
                </div>

                <div className="mb-3">
                  <label className="edu-label">Call Outcome</label>
                  <select
                    className="edu-select"
                    value={callModal.outcome}
                    onChange={(e) => setCallModal({ ...callModal, outcome: e.target.value })}
                  >
                    <option value="Answered">Answered / Spoke with Guardian</option>
                    <option value="No Answer">No Answer / Rang Out</option>
                    <option value="Line Busy">Line Busy</option>
                    <option value="Invalid Number">Invalid Number / Unreachable</option>
                    <option value="Callback Requested">Callback Requested</option>
                    <option value="Left Message">Left Voicemail / SMS</option>
                  </select>
                </div>

                <div className="mb-3">
                  <label className="edu-label">Detailed Call Remarks</label>
                  <textarea
                    className="edu-input"
                    rows={4}
                    placeholder="Record notes from conversation, agreed action points, or reason for non-contact..."
                    value={callModal.remarks || ''}
                    onChange={(e) => setCallModal({ ...callModal, remarks: e.target.value })}
                    required
                  />
                </div>

                <div className="d-flex justify-content-end gap-2 mt-4">
                  <Button type="button" variant="outline" onClick={() => setCallModal(null)}>
                    Cancel
                  </Button>
                  <Button type="submit" variant="primary" icon="bi-journal-check">
                    Save Call Log
                  </Button>
                </div>
              </form>
            </div>
          </div>
        </Modal>
      )}

    </AppLayout>
  );
};
export default AdminPortal;