import React, { useState, useEffect, useCallback } from 'react';
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

const TEACHER_NAV: NavItem[] = [
  { id: 'dashboard', label: 'Teacher Dashboard', icon: 'bi-speedometer2' },
  { id: 'attendance', label: 'Mark Attendance', icon: 'bi-calendar2-check-fill' },
  { id: 'results', label: 'Enter Exam Marks', icon: 'bi-journal-check' },
  { id: 'assignments', label: 'Assignments & Grading', icon: 'bi-clipboard2-check-fill' },
  { id: 'materials', label: 'Study Materials', icon: 'bi-folder-symlink-fill' },
  { id: 'announcements', label: 'School Announcements', icon: 'bi-megaphone-fill' },
];

export const TeacherPortal: React.FC = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Attendance state
  const [attClassId, setAttClassId] = useState('');
  const [attDate, setAttDate] = useState(new Date().toISOString().slice(0, 10));
  const [attStudents, setAttStudents] = useState<any[]>([]);
  const [attMap, setAttMap] = useState<Record<number, string>>({});
  const [attInfo, setAttInfo] = useState<{
    already_recorded: boolean;
    present_count: number;
    absent_count: number;
    recorded_by_name: string | null;
    updated_at: string | null;
  } | null>(null);
  const [attIsEditing, setAttIsEditing] = useState(false);

  // Results state
  const [resClassId, setResClassId] = useState('');
  const [resSubjId, setResSubjId] = useState('');
  const [resExamId, setResExamId] = useState('');
  const [resStudents, setResStudents] = useState<any[]>([]);
  const [marksMap, setMarksMap] = useState<Record<number, string>>({});

  // Assignment form & submissions modal
  const [assignForm, setAssignForm] = useState({
    title: '',
    description: '',
    class_id: '',
    subject_id: '',
    assignment_date: new Date().toISOString().slice(0, 10),
    due_date: '',
  });
  const [assignFile, setAssignFile] = useState<File | null>(null);
  const [subsModal, setSubsModal] = useState<any>(null);

  // Material upload form
  const [matTitle, setMatTitle] = useState('');
  const [matDesc, setMatDesc] = useState('');
  const [matClassId, setMatClassId] = useState('');
  const [matSubjId, setMatSubjId] = useState('');
  const [matFile, setMatFile] = useState<File | null>(null);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/api/teacher/overview');
      setData(res);
      if (res.classes?.[0] && !attClassId) {
        setAttClassId(String(res.classes[0].id));
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [attClassId]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const loadAttendanceSheet = async (classId: string, date: string) => {
    if (!classId) return;
    try {
      const res = await apiFetch(`/api/teacher/attendance/${classId}?date=${date}`);
      setAttStudents(res.students || []);
      const nextMap: Record<number, string> = {};
      (res.students || []).forEach((s: any) => {
        nextMap[s.id] = s.status || 'Present';
      });
      setAttMap(nextMap);
      setAttInfo({
        already_recorded: Boolean(res.already_recorded),
        present_count: res.present_count || 0,
        absent_count: res.absent_count || 0,
        recorded_by_name: res.recorded_by_name || null,
        updated_at: res.updated_at || null,
      });
      setAttIsEditing(!res.already_recorded);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const saveAttendance = async () => {
    try {
      const res = await apiFetch(`/api/teacher/attendance/${attClassId}`, {
        method: 'POST',
        body: JSON.stringify({
          date: attDate,
          records: attMap,
          allow_edit: attIsEditing,
        }),
      });
      setMessage(res.message);
      await loadAttendanceSheet(attClassId, attDate);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const markAllStatus = (status: 'Present' | 'Absent') => {
    const updated: Record<number, string> = {};
    attStudents.forEach((s) => {
      updated[s.id] = status;
    });
    setAttMap(updated);
  };

  const loadResultsSheet = async () => {
    if (!resClassId || !resSubjId || !resExamId) return;
    try {
      const res = await apiFetch(
        `/api/teacher/results/${resClassId}/${resSubjId}/${resExamId}`
      );
      setResStudents(res.students || []);
      const m: Record<number, string> = {};
      (res.students || []).forEach((s: any) => {
        m[s.id] = s.marks !== '' && s.marks !== undefined ? String(s.marks) : '';
      });
      setMarksMap(m);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const saveResults = async () => {
    try {
      const res = await apiFetch(
        `/api/teacher/results/${resClassId}/${resSubjId}/${resExamId}`,
        {
          method: 'POST',
          body: JSON.stringify({ marks: marksMap }),
        }
      );
      setMessage(res.message);
      await loadResultsSheet();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleCreateAssignment = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const fd = new FormData();
      fd.append('title', assignForm.title);
      fd.append('description', assignForm.description);
      fd.append('class_id', assignForm.class_id);
      fd.append('subject_id', assignForm.subject_id);
      fd.append('assignment_date', assignForm.assignment_date);
      fd.append('due_date', assignForm.due_date);
      if (assignFile) {
        fd.append('file', assignFile);
      }
      const res = await apiFetch('/api/teacher/assignments', {
        method: 'POST',
        body: fd,
      });
      setMessage(res.message);
      setAssignForm({
        title: '',
        description: '',
        class_id: '',
        subject_id: '',
        assignment_date: new Date().toISOString().slice(0, 10),
        due_date: '',
      });
      setAssignFile(null);
      await loadOverview();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleMaterialUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!matFile) return;
    const fd = new FormData();
    fd.append('title', matTitle);
    fd.append('description', matDesc);
    fd.append('class_id', matClassId);
    fd.append('subject_id', matSubjId);
    fd.append('file', matFile);
    try {
      const res = await apiFetch('/api/teacher/materials', {
        method: 'POST',
        body: fd,
      });
      setMessage(res.message);
      setMatTitle('');
      setMatDesc('');
      setMatFile(null);
      await loadOverview();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleArchiveMaterial = async (materialId: number, currentStatus: boolean) => {
    try {
      const res = await apiFetch(`/api/materials/${materialId}/archive`, {
        method: 'POST',
        body: JSON.stringify({ is_archived: !currentStatus }),
      });
      setMessage(res.message);
      await loadOverview();
    } catch (err: any) {
      setError(err.message);
    }
  };

  if (loading) return <LoadingState message="Loading Teacher Portal..." />;

  const classes = data?.classes || [];
  const subjects = data?.subjects || [];
  const exams = data?.exams || [];
  const assignments = data?.assignments || [];
  const materials = data?.materials || [];
  const announcements = data?.announcements || [];
  const classSubjectMap: Record<number, number[]> = data?.class_subject_map || {};

  // Cascading subject lists
  const availableResSubjects =
    resClassId && classSubjectMap[Number(resClassId)]
      ? subjects.filter((s: any) => classSubjectMap[Number(resClassId)].includes(s.id))
      : subjects;

  const availableAssignSubjects =
    assignForm.class_id && classSubjectMap[Number(assignForm.class_id)]
      ? subjects.filter((s: any) => classSubjectMap[Number(assignForm.class_id)].includes(s.id))
      : subjects;

  const availableMatSubjects =
    matClassId && classSubjectMap[Number(matClassId)]
      ? subjects.filter((s: any) => classSubjectMap[Number(matClassId)].includes(s.id))
      : subjects;

  // Live attendance counts
  const presentCount = Object.values(attMap).filter((v) => v === 'Present').length;
  const absentCount = Object.values(attMap).filter((v) => v === 'Absent').length;

  return (
    <AppLayout
      title={`Teacher Portal — ${data?.teacher?.first_name || ''} ${data?.teacher?.last_name || ''}`}
      subtitle={`Staff No: ${data?.teacher?.staff_no || '—'} • Specialization: ${data?.teacher?.specialization || 'General'}`}
      navItems={TEACHER_NAV}
      activeTab={activeTab}
      onSelectTab={setActiveTab}
    >
      <AlertBanner variant="success" message={message} onDismiss={() => setMessage(null)} />
      <AlertBanner variant="danger" message={error} onDismiss={() => setError(null)} />

      {classes.length === 0 && (
        <div className="alert alert-warning d-flex align-items-center gap-2 mb-4">
          <i className="bi bi-info-circle-fill fs-5" />
          <div>
            <strong>Teaching Schedule Pending:</strong> You have not been assigned to any classes or subjects in the school timetable yet. Please contact your school administrator to configure your teaching allocation.
          </div>
        </div>
      )}

      {activeTab === 'dashboard' && (
        <>
          <div className="row g-3 mb-4">
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-door-open-fill"
                label="Assigned Classes"
                value={classes.length}
                variant="blue"
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-book-fill"
                label="Assigned Subjects"
                value={subjects.length}
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-clipboard2-check-fill"
                label="Active Assignments"
                value={assignments.length}
                variant="mustard"
                accentTop
              />
            </div>
            <div className="col-sm-6 col-xl-3">
              <StatCard
                icon="bi-folder2-open"
                label="Study Materials"
                value={materials.length}
              />
            </div>
          </div>

          <div className="row g-4 mb-4">
            <div className="col-lg-7">
              <Card
                title="Recent Assignments & Submissions"
                actions={
                  <Button size="sm" variant="accent" onClick={() => setActiveTab('assignments')}>
                    Manage Assignments
                  </Button>
                }
              >
                <DataTable
                  rows={assignments}
                  columns={[
                    { header: 'Title', render: (a) => <span className="fw-bold">{a.title}</span> },
                    { header: 'Class', render: (a) => a.class_name },
                    { header: 'Subject', render: (a) => a.subject_name },
                    {
                      header: 'Attachment',
                      render: (a) =>
                        a.has_attachment ? (
                          <a
                            href={`/api/assignments/${a.id}/attachment`}
                            download
                            className="edu-btn edu-btn-outline edu-btn-sm"
                          >
                            <i className="bi bi-paperclip" /> File
                          </a>
                        ) : (
                          <span className="text-muted small">None</span>
                        ),
                    },
                    {
                      header: 'Submissions',
                      render: (a) => <Badge variant="mustard">{a.submissions_count} submitted</Badge>,
                    },
                  ]}
                />
              </Card>
            </div>

            <div className="col-lg-5">
              <Card
                title="School Announcements"
                actions={
                  <Button size="sm" variant="outline" onClick={() => setActiveTab('announcements')}>
                    All ({announcements.length})
                  </Button>
                }
              >
                {announcements.length === 0 ? (
                  <div className="text-muted small">No announcements posted yet.</div>
                ) : (
                  <div className="d-flex flex-column gap-3">
                    {announcements.slice(0, 3).map((ann: any) => (
                      <div
                        key={ann.id}
                        className="p-3 rounded-2 border"
                        style={{ background: 'var(--color-surface)' }}
                      >
                        <div className="d-flex justify-content-between align-items-center mb-1">
                          <span className="fw-bold text-primary">{ann.title}</span>
                          <span className="text-muted small">{ann.created_at?.slice(0, 10)}</span>
                        </div>
                        <div className="small text-muted">{ann.message}</div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </div>
          </div>
        </>
      )}

      {/* ── ATTENDANCE TAB ── */}
      {activeTab === 'attendance' && (
        <Card
          title="Daily Class Attendance Register"
          subtitle="Enforces once-per-day roll call per class. Changes to previously submitted registers require edit mode."
        >
          <div className="row g-2 align-items-end mb-4">
            <div className="col-md-5">
              <label className="edu-label">Assigned Class</label>
              <select
                className="edu-select"
                value={attClassId}
                onChange={(e) => {
                  setAttClassId(e.target.value);
                  setAttStudents([]);
                  setAttInfo(null);
                }}
              >
                <option value="">-- Select Your Class --</option>
                {classes.map((c: any) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-4">
              <label className="edu-label">Attendance Date</label>
              <input
                type="date"
                className="edu-input"
                value={attDate}
                onChange={(e) => {
                  setAttDate(e.target.value);
                  setAttStudents([]);
                  setAttInfo(null);
                }}
              />
            </div>
            <div className="col-md-3">
              <Button
                variant="primary"
                className="w-100"
                disabled={!attClassId}
                icon="bi-search"
                onClick={() => loadAttendanceSheet(attClassId, attDate)}
              >
                Load Register
              </Button>
            </div>
          </div>

          {attInfo?.already_recorded && (
            <div
              className="p-3 rounded-3 mb-3 d-flex flex-wrap align-items-center justify-content-between gap-2"
              style={{ background: '#FFF8E1', border: '1px solid #FFE082' }}
            >
              <div>
                <i className="bi bi-shield-check text-success me-2 fs-5" />
                <strong>Attendance Already Recorded:</strong> {attInfo.present_count} Present,{' '}
                {attInfo.absent_count} Absent on {attDate}.
                {attInfo.recorded_by_name && (
                  <span className="ms-1 text-muted small">
                    (Saved by {attInfo.recorded_by_name}
                    {attInfo.updated_at ? ` at ${attInfo.updated_at.slice(11, 16)}` : ''})
                  </span>
                )}
              </div>
              <Button
                size="sm"
                variant={attIsEditing ? 'accent' : 'outline'}
                icon={attIsEditing ? 'bi-lock-fill' : 'bi-pencil-square'}
                onClick={() => setAttIsEditing(!attIsEditing)}
              >
                {attIsEditing ? 'Lock Register' : 'Unlock Register to Edit'}
              </Button>
            </div>
          )}

          {attStudents.length > 0 && (
            <>
              {/* Quick Actions & Live Indicator */}
              <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3 p-2 bg-light border rounded">
                <div className="d-flex align-items-center gap-2">
                  <span className="small fw-semibold text-muted">Roll Call Count:</span>
                  <span className="badge bg-success-subtle text-success border border-success-subtle">
                    <i className="bi bi-check-circle-fill me-1" /> {presentCount} Present
                  </span>
                  <span className="badge bg-danger-subtle text-danger border border-danger-subtle">
                    <i className="bi bi-x-circle-fill me-1" /> {absentCount} Absent
                  </span>
                  <span className="badge bg-secondary-subtle text-dark border">
                    Total: {attStudents.length}
                  </span>
                </div>
                <div className="d-flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!attIsEditing}
                    onClick={() => markAllStatus('Present')}
                  >
                    Mark All Present
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!attIsEditing}
                    onClick={() => markAllStatus('Absent')}
                  >
                    Mark All Absent
                  </Button>
                </div>
              </div>

              <div className="edu-table-wrap mb-3">
                <table className="edu-table">
                  <thead>
                    <tr>
                      <th style={{ width: '20%' }}>Admission No</th>
                      <th style={{ width: '45%' }}>Student Name</th>
                      <th style={{ width: '35%' }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {attStudents.map((s) => {
                      const isPresent = attMap[s.id] === 'Present';
                      return (
                        <tr key={s.id}>
                          <td>
                            <Badge variant="blue">{s.admission_no}</Badge>
                          </td>
                          <td className="fw-bold">
                            {s.first_name} {s.last_name}
                          </td>
                          <td>
                            <div className="d-flex gap-2">
                              <Button
                                size="sm"
                                variant={isPresent ? 'accent' : 'outline'}
                                disabled={!attIsEditing}
                                icon="bi-check-lg"
                                onClick={() => setAttMap({ ...attMap, [s.id]: 'Present' })}
                              >
                                Present
                              </Button>
                              <Button
                                size="sm"
                                variant={!isPresent ? 'danger' : 'outline'}
                                disabled={!attIsEditing}
                                icon="bi-x-lg"
                                onClick={() => setAttMap({ ...attMap, [s.id]: 'Absent' })}
                              >
                                Absent
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="d-flex justify-content-end gap-2">
                <Button
                  variant="accent"
                  icon="bi-check2-circle"
                  disabled={!attIsEditing}
                  onClick={saveAttendance}
                >
                  {attInfo?.already_recorded ? 'Update Register Changes' : 'Save Daily Attendance'}
                </Button>
              </div>
            </>
          )}
        </Card>
      )}

      {/* ── EXAM MARKS TAB ── */}
      {activeTab === 'results' && (
        <Card title="Enter Student Exam Marks" subtitle="Scores automatically compute ECZ grades">
          <div className="row g-2 align-items-end mb-4">
            <div className="col-md-3">
              <label className="edu-label">Assigned Class</label>
              <select
                className="edu-select"
                value={resClassId}
                onChange={(e) => {
                  setResClassId(e.target.value);
                  setResSubjId('');
                }}
              >
                <option value="">-- Class --</option>
                {classes.map((c: any) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-3">
              <label className="edu-label">Assigned Subject</label>
              <select
                className="edu-select"
                value={resSubjId}
                onChange={(e) => setResSubjId(e.target.value)}
                disabled={!resClassId}
              >
                <option value="">-- Subject --</option>
                {availableResSubjects.map((s: any) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-3">
              <label className="edu-label">Examination</label>
              <select
                className="edu-select"
                value={resExamId}
                onChange={(e) => setResExamId(e.target.value)}
              >
                <option value="">-- Examination --</option>
                {exams.map((ex: any) => (
                  <option key={ex.id} value={ex.id}>
                    {ex.name} {ex.start_date ? `(${ex.start_date})` : ''}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-3">
              <Button
                variant="primary"
                className="w-100"
                disabled={!resClassId || !resSubjId || !resExamId}
                icon="bi-search"
                onClick={loadResultsSheet}
              >
                Load Students
              </Button>
            </div>
          </div>

          {resStudents.length > 0 && (
            <>
              <div className="edu-table-wrap mb-3">
                <table className="edu-table">
                  <thead>
                    <tr>
                      <th>Admission No</th>
                      <th>Student Name</th>
                      <th>Exam Score (0 - 100%)</th>
                      <th>Calculated ECZ Grade</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resStudents.map((s) => (
                      <tr key={s.id}>
                        <td>{s.admission_no}</td>
                        <td className="fw-bold">
                          {s.first_name} {s.last_name}
                        </td>
                        <td style={{ maxWidth: 160 }}>
                          <input
                            type="number"
                            min={0}
                            max={100}
                            className="edu-input py-1"
                            value={marksMap[s.id] ?? ''}
                            onChange={(e) =>
                              setMarksMap({ ...marksMap, [s.id]: e.target.value })
                            }
                          />
                        </td>
                        <td>
                          <Badge variant="mustard">{s.grade}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Button variant="accent" icon="bi-save" onClick={saveResults}>
                Save Exam Marks
              </Button>
            </>
          )}
        </Card>
      )}

      {/* ── ASSIGNMENTS TAB ── */}
      {activeTab === 'assignments' && (
        <div className="row g-4">
          <div className="col-lg-5">
            <Card title="Create Assignment" subtitle="Publish coursework with optional file attachments (up to 10MB)">
              <form onSubmit={handleCreateAssignment}>
                <FormField label="Assignment Title" required>
                  <input
                    className="edu-input"
                    value={assignForm.title}
                    onChange={(e) => setAssignForm({ ...assignForm, title: e.target.value })}
                    placeholder="e.g. Algebra Quadratic Equations Worksheet"
                    required
                  />
                </FormField>
                <div className="row g-2">
                  <div className="col-6">
                    <FormField label="Assigned Class" required>
                      <select
                        className="edu-select"
                        value={assignForm.class_id}
                        onChange={(e) => {
                          setAssignForm({ ...assignForm, class_id: e.target.value, subject_id: '' });
                        }}
                        required
                      >
                        <option value="">-- Class --</option>
                        {classes.map((c: any) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                    </FormField>
                  </div>
                  <div className="col-6">
                    <FormField label="Assigned Subject" required>
                      <select
                        className="edu-select"
                        value={assignForm.subject_id}
                        onChange={(e) =>
                          setAssignForm({ ...assignForm, subject_id: e.target.value })
                        }
                        disabled={!assignForm.class_id}
                        required
                      >
                        <option value="">-- Subject --</option>
                        {availableAssignSubjects.map((s: any) => (
                          <option key={s.id} value={s.id}>
                            {s.name}
                          </option>
                        ))}
                      </select>
                    </FormField>
                  </div>
                </div>
                <div className="row g-2">
                  <div className="col-6">
                    <FormField label="Assignment Date" required>
                      <input
                        type="date"
                        className="edu-input"
                        value={assignForm.assignment_date}
                        onChange={(e) => setAssignForm({ ...assignForm, assignment_date: e.target.value })}
                        required
                      />
                    </FormField>
                  </div>
                  <div className="col-6">
                    <FormField label="Submission Deadline" required>
                      <input
                        type="date"
                        className="edu-input"
                        value={assignForm.due_date}
                        onChange={(e) => setAssignForm({ ...assignForm, due_date: e.target.value })}
                        required
                      />
                    </FormField>
                  </div>
                </div>
                <FormField label="Instructions & Description" required>
                  <textarea
                    rows={3}
                    className="edu-textarea"
                    value={assignForm.description}
                    onChange={(e) =>
                      setAssignForm({ ...assignForm, description: e.target.value })
                    }
                    placeholder="Provide detailed instructions or rubric..."
                    required
                  />
                </FormField>
                <FormField label="Attachment (PDF, DOCX, DOC, PNG, JPG — max 10MB)">
                  <input
                    type="file"
                    className="edu-input"
                    accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.txt"
                    onChange={(e) => setAssignFile(e.target.files?.[0] || null)}
                  />
                  {assignFile && (
                    <div className="d-flex align-items-center justify-content-between mt-1 p-2 bg-light rounded border">
                      <span className="small text-truncate me-2">
                        <i className="bi bi-paperclip me-1" />
                        {assignFile.name} ({(assignFile.size / 1024 / 1024).toFixed(2)} MB)
                      </span>
                      <button
                        type="button"
                        className="btn btn-sm btn-link text-danger p-0 text-decoration-none"
                        onClick={() => setAssignFile(null)}
                      >
                        Remove
                      </button>
                    </div>
                  )}
                </FormField>
                <Button type="submit" variant="accent" className="w-100" icon="bi-send-fill">
                  Publish Assignment
                </Button>
              </form>
            </Card>
          </div>
          <div className="col-lg-7">
            <Card title="Published Assignments & Submissions">
              <DataTable
                rows={assignments}
                columns={[
                  { header: 'Title', render: (a) => <span className="fw-bold">{a.title}</span> },
                  { header: 'Class / Subject', render: (a) => `${a.class_name} • ${a.subject_name}` },
                  {
                    header: 'Deadline',
                    render: (a) => a.deadline?.slice(0, 10) || '—',
                  },
                  {
                    header: 'Attachment',
                    render: (a) =>
                      a.has_attachment ? (
                        <a
                          href={`/api/assignments/${a.id}/attachment`}
                          download
                          className="edu-btn edu-btn-outline edu-btn-sm"
                          title={a.attachment_name || 'Download'}
                        >
                          <i className="bi bi-paperclip" /> File
                        </a>
                      ) : (
                        <span className="text-muted small">None</span>
                      ),
                  },
                  {
                    header: 'Submissions',
                    render: (a) => (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={async () => {
                          const res = await apiFetch(`/api/teacher/submissions/${a.id}`);
                          setSubsModal(res);
                        }}
                      >
                        View ({a.submissions_count})
                      </Button>
                    ),
                  },
                ]}
              />
            </Card>
          </div>
        </div>
      )}

      {/* ── MATERIALS TAB ── */}
      {activeTab === 'materials' && (
        <div className="row g-4">
          <div className="col-lg-5">
            <Card title="Upload Study Material" subtitle="Scoped to your assigned classes and subjects">
              <form onSubmit={handleMaterialUpload}>
                <FormField label="Material Title" required>
                  <input
                    className="edu-input"
                    value={matTitle}
                    onChange={(e) => setMatTitle(e.target.value)}
                    placeholder="e.g. Geometry Revision Notes"
                    required
                  />
                </FormField>
                <div className="row g-2">
                  <div className="col-6">
                    <FormField label="Assigned Class" required>
                      <select
                        className="edu-select"
                        value={matClassId}
                        onChange={(e) => {
                          setMatClassId(e.target.value);
                          setMatSubjId('');
                        }}
                        required
                      >
                        <option value="">-- Class --</option>
                        {classes.map((c: any) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                    </FormField>
                  </div>
                  <div className="col-6">
                    <FormField label="Assigned Subject" required>
                      <select
                        className="edu-select"
                        value={matSubjId}
                        onChange={(e) => setMatSubjId(e.target.value)}
                        disabled={!matClassId}
                        required
                      >
                        <option value="">-- Subject --</option>
                        {availableMatSubjects.map((s: any) => (
                          <option key={s.id} value={s.id}>
                            {s.name}
                          </option>
                        ))}
                      </select>
                    </FormField>
                  </div>
                </div>
                <FormField label="Description" required>
                  <textarea
                    rows={2}
                    className="edu-textarea"
                    value={matDesc}
                    onChange={(e) => setMatDesc(e.target.value)}
                    placeholder="Brief description or chapter syllabus..."
                    required
                  />
                </FormField>
                <FormField label="Document File (PDF, DOCX, PPTX, Image — max 15MB)" required>
                  <input
                    type="file"
                    className="edu-input"
                    onChange={(e) => setMatFile(e.target.files?.[0] || null)}
                    required
                  />
                </FormField>
                <Button type="submit" variant="accent" className="w-100" icon="bi-upload">
                  Upload Material
                </Button>
              </form>
            </Card>
          </div>
          <div className="col-lg-7">
            <Card title="Study Materials Archive">
              <DataTable
                rows={materials}
                columns={[
                  {
                    header: 'Title',
                    render: (m) => (
                      <div>
                        <span className="fw-bold">{m.title}</span>
                        {m.is_archived && <span className="badge bg-secondary ms-1">Archived</span>}
                        <div className="small text-muted">{m.description}</div>
                      </div>
                    ),
                  },
                  { header: 'Class', render: (m) => m.class_name },
                  { header: 'Subject', render: (m) => m.subject_name },
                  {
                    header: 'Actions',
                    render: (m) => (
                      <div className="d-flex gap-1">
                        <a
                          href={`/api/materials/${m.id}/download`}
                          className="edu-btn edu-btn-outline edu-btn-sm"
                          download
                        >
                          <i className="bi bi-download" /> Download
                        </a>
                        <Button
                          size="sm"
                          variant={m.is_archived ? 'primary' : 'outline'}
                          title={m.is_archived ? 'Restore material' : 'Archive material'}
                          onClick={() => handleArchiveMaterial(m.id, m.is_archived)}
                        >
                          <i className={`bi ${m.is_archived ? 'bi-arrow-clockwise' : 'bi-archive'}`} />
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

      {/* ── ANNOUNCEMENTS TAB ── */}
      {activeTab === 'announcements' && (
        <Card
          title="School Announcements"
          subtitle="Official administrative memos and class notices published by administration"
        >
          {announcements.length === 0 ? (
            <div className="text-muted small p-4 text-center">No announcements have been published yet.</div>
          ) : (
            <div className="d-flex flex-column gap-3">
              {announcements.map((ann: any) => (
                <div
                  key={ann.id}
                  className="p-3 rounded-3 border"
                  style={{ background: 'var(--color-surface)' }}
                >
                  <div className="d-flex justify-content-between align-items-start mb-2">
                    <div>
                      <h5 className="mb-0 fw-bold text-primary">{ann.title}</h5>
                      <span className="small text-muted">
                        Published: {ann.created_at ? new Date(ann.created_at).toLocaleDateString() : '—'}
                      </span>
                    </div>
                    {ann.priority && ann.priority !== 'Normal' && (
                      <Badge variant="mustard">{ann.priority}</Badge>
                    )}
                  </div>
                  <div className="edu-body mb-0" style={{ whiteSpace: 'pre-line' }}>
                    {ann.message}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* ── Submissions Review Modal ── */}
      <Modal
        open={Boolean(subsModal)}
        title={`Submissions — ${subsModal?.assignment?.title || ''}`}
        onClose={() => setSubsModal(null)}
      >
        {!subsModal?.submissions?.length ? (
          <div className="text-muted small">No student submissions recorded yet.</div>
        ) : (
          <div className="d-flex flex-column gap-3">
            {subsModal.submissions.map((sub: any) => (
              <div
                key={sub.id}
                className="p-3 rounded-3"
                style={{ background: 'var(--color-cool-gray)' }}
              >
                <div className="d-flex justify-content-between align-items-center mb-2">
                  <span className="fw-bold">{sub.student_name}</span>
                  <a
                    href={`/admin/download/${sub.file_path}`}
                    className="edu-btn edu-btn-outline edu-btn-sm"
                  >
                    Download File
                  </a>
                </div>
                <div className="small text-muted">
                  Marks: <strong>{sub.marks ?? 'Not graded'}</strong> &bull; Feedback:{' '}
                  {sub.feedback || '—'}
                </div>
              </div>
            ))}
          </div>
        )}
      </Modal>
    </AppLayout>
  );
};
