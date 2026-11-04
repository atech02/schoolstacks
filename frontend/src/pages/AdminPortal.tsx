import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AppLayout, NavItem } from '../layouts/AppLayout';
import { apiFetch } from '../services/api';
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

const ADMIN_NAV: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard & Analytics', icon: 'bi-grid-1x2-fill' },
  { id: 'students', label: 'Students', icon: 'bi-mortarboard-fill' },
  { id: 'teachers', label: 'Teachers', icon: 'bi-person-badge-fill' },
  { id: 'parents', label: 'Parents', icon: 'bi-people-fill' },
  { id: 'academics', label: 'Classes, Subjects & Terms', icon: 'bi-layers-fill' },
  { id: 'fees', label: 'Fees & Online Payments', icon: 'bi-cash-coin' },
  { id: 'timetable', label: 'Timetable', icon: 'bi-calendar3-week' },
  { id: 'announcements', label: 'Announcements', icon: 'bi-megaphone-fill' },
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
          1. DASHBOARD & ANALYTICS
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'dashboard' && (
        <>
          <div className="row g-3 mb-4">
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-mortarboard-fill"
                label="Enrolled Students"
                value={metrics.total_students || 0}
                variant="blue"
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-person-workspace"
                label="Teaching Staff"
                value={metrics.total_teachers || 0}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-door-open-fill"
                label="Active Classes"
                value={metrics.total_classes || 0}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-cash-coin"
                label="Fees Collected (ZMW)"
                value={`K${Number(metrics.total_collected_zmw || 0).toFixed(2)}`}
                variant="mustard"
                accentTop
              />
            </div>
          </div>

          <div className="row g-4 mb-4">
            <div className="col-lg-7">
              <Card
                title="Subject Performance Averages"
                subtitle="Mean exam scores across registered school subjects"
              >
                {subjects.length === 0 ? (
                  <div className="text-muted small">No subjects configured yet.</div>
                ) : (
                  <div className="d-flex flex-column gap-3">
                    {subjects.map((s: any) => (
                      <div key={s.id}>
                        <div className="d-flex justify-content-between small fw-bold mb-1">
                          <span>
                            {s.name} ({s.code})
                          </span>
                          <span style={{ color: 'var(--color-strong-blue)' }}>
                            {s.average}% ({s.count} results)
                          </span>
                        </div>
                        <div
                          className="progress"
                          style={{ height: 10, background: 'var(--color-cool-gray)' }}
                        >
                          <div
                            className="progress-bar"
                            style={{
                              width: `${Math.min(100, Math.max(6, s.average))}%`,
                              background:
                                s.average >= 50
                                  ? 'var(--color-strong-blue)'
                                  : 'var(--color-mustard)',
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </div>

            <div className="col-lg-5">
              <Card title="Academic & Attendance Summary" subtitle="School-wide KPIs">
                <div className="row g-3">
                  <div className="col-6">
                    <div className="p-3 rounded border text-center" style={{ background: '#F8FAFC' }}>
                      <div className="text-muted small">Passing Exam Marks</div>
                      <div className="h4 fw-bold mb-0 text-success">{metrics.pass_count || 0}</div>
                    </div>
                  </div>
                  <div className="col-6">
                    <div className="p-3 rounded border text-center" style={{ background: '#F8FAFC' }}>
                      <div className="text-muted small">Failing Exam Marks</div>
                      <div className="h4 fw-bold mb-0 text-danger">{metrics.fail_count || 0}</div>
                    </div>
                  </div>
                  <div className="col-6">
                    <div className="p-3 rounded border text-center" style={{ background: '#F8FAFC' }}>
                      <div className="text-muted small">Present Attendances</div>
                      <div className="h4 fw-bold mb-0" style={{ color: 'var(--color-strong-blue)' }}>
                        {metrics.present_count || 0}
                      </div>
                    </div>
                  </div>
                  <div className="col-6">
                    <div className="p-3 rounded border text-center" style={{ background: '#F8FAFC' }}>
                      <div className="text-muted small">Absent Records</div>
                      <div className="h4 fw-bold mb-0 text-warning">{metrics.absent_count || 0}</div>
                    </div>
                  </div>
                </div>
              </Card>
            </div>
          </div>

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
    </AppLayout>
  );
};
export default AdminPortal;