"""SmartAttend: current-semester attendance portal with student and domain admin portals."""
import json
import math
import os
import sqlite3
import uuid
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from database import UPLOAD_DIR, add_subject_to_semester, close_semester, create_student, ensure_upload_dir, get_db, init_db

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-this-demo-secret'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
ALLOWED_LEAVE_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}
DAYS_ORDER = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']

init_db()
ensure_upload_dir()


def percent(attended, total):
    return round(attended * 100 / total, 1) if total else 0.0


def status_label(value):
    return 'safe' if value >= 75 else ('warning' if value >= 65 else 'critical')


def status_text(value):
    if value >= 75:
        return 'Attendance Safe'
    if value >= 65:
        return 'Needs Attention'
    return 'Critical'


def predict(attended, total, target):
    p = percent(attended, total)
    if not total:
        return {'kind': 'neutral', 'message': 'No attendance data has been imported for this semester.'}
    if p >= target:
        n = max(0, math.floor(attended * 100 / target - total))
        suffix = 'es' if n != 1 else ''
        return {'kind': 'positive', 'message': f'You can miss {n} more class{suffix} while maintaining {target:g}%.'}
    n = max(0, math.ceil((target * total - 100 * attended) / (100 - target)))
    suffix = 'es' if n != 1 else ''
    return {'kind': 'warning', 'message': f'Attend the next {n} class{suffix} continuously to reach {target:g}%.'}


def student_required(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if not session.get('student_id'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return inner


def admin_required(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if not session.get('admin_id'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return inner


def stats(conn, subject_id):
    row = conn.execute(
        "SELECT COUNT(*) total, COALESCE(SUM(status='present'),0) attended FROM attendance_records WHERE subject_id=?",
        (subject_id,),
    ).fetchone()
    return row['attended'], row['total']


def subjects_for_semester(conn, sem_id):
    result = []
    for s in conn.execute('SELECT * FROM subjects WHERE semester_id=? ORDER BY name', (sem_id,)):
        attended, total = stats(conn, s['id'])
        pct = percent(attended, total)
        result.append({
            **dict(s),
            'attended': attended,
            'total': total,
            'absent': total - attended,
            'percentage': pct,
            'status': status_label(pct) if total else 'none',
        })
    return result


def get_active_semester_row(conn, student_row):
    """Get the currently active semester for a student. Returns None if no active semester."""
    if student_row['current_semester'] is None:
        return None
    return conn.execute(
        'SELECT * FROM semesters WHERE student_id=? AND number=? AND is_active=1 AND is_closed=0',
        (student_row['id'], student_row['current_semester']),
    ).fetchone()


def semester_summary(conn, student_row):
    sem = get_active_semester_row(conn, student_row)
    if not sem:
        return None, {'attended': 0, 'total': 0, 'absent': 0, 'percentage': 0.0, 'status': 'none'}
    sub = subjects_for_semester(conn, sem['id'])
    attended = sum(x['attended'] for x in sub)
    total = sum(x['total'] for x in sub)
    return {**dict(sem), 'subjects': sub}, {
        'attended': attended,
        'total': total,
        'absent': total - attended,
        'percentage': percent(attended, total),
        'status': status_label(percent(attended, total)) if total else 'none',
    }


def student(conn):
    return conn.execute('SELECT * FROM students WHERE id=?', (session['student_id'],)).fetchone()


def notices_for_student(conn, current_semester):
    if current_semester is None:
        return conn.execute(
            'SELECT * FROM notices WHERE semester_number IS NULL ORDER BY is_important DESC, created_at DESC',
        ).fetchall()
    return conn.execute(
        'SELECT * FROM notices WHERE semester_number IS NULL OR semester_number=? ORDER BY is_important DESC, created_at DESC',
        (current_semester,),
    ).fetchall()


def timetable_for_student(conn, student_id, semester_number):
    rows = conn.execute(
        'SELECT * FROM timetable_entries WHERE student_id=? AND semester_number=? ORDER BY day_of_week, start_time',
        (student_id, semester_number),
    ).fetchall()
    grouped = {day: [] for day in DAYS_ORDER}
    for row in rows:
        grouped.setdefault(row['day_of_week'], []).append(dict(row))
    return grouped


def today_timetable(conn, student_id, semester_number):
    today = datetime.now().strftime('%A').upper()
    return conn.execute(
        'SELECT * FROM timetable_entries WHERE student_id=? AND semester_number=? AND day_of_week=? ORDER BY start_time',
        (student_id, semester_number, today),
    ).fetchall()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_LEAVE_EXTENSIONS


def save_leave_document(file):
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(UPLOAD_DIR, filename))
    return filename


def greeting():
    hour = datetime.now().hour
    if hour < 12:
        return 'Good Morning'
    if hour < 17:
        return 'Good Afternoon'
    return 'Good Evening'


def leave_summary_for_student(conn, student_id, semester_number):
    """Return count of pending, approved, rejected leave requests for current semester."""
    if semester_number is None:
        return {'pending': 0, 'approved': 0, 'rejected': 0, 'total': 0}
    rows = conn.execute(
        'SELECT status, COUNT(*) cnt FROM leave_requests WHERE student_id=? AND semester_number=? GROUP BY status',
        (student_id, semester_number),
    ).fetchall()
    result = {'pending': 0, 'approved': 0, 'rejected': 0, 'total': 0}
    for r in rows:
        result[r['status']] = r['cnt']
        result['total'] += r['cnt']
    return result


# ─── Student routes ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if session.get('student_id'):
        return redirect(url_for('dashboard'))
    if session.get('admin_id'):
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db()
        row = conn.execute(
            'SELECT * FROM students WHERE student_id=? AND password=?',
            (request.form.get('student_id', '').strip(), request.form.get('password', '')),
        ).fetchone()
        conn.close()
        if row:
            session.clear()
            session['student_id'] = row['id']
            return redirect(url_for('dashboard'))
        flash('Invalid Student ID or password.', 'error')
    return render_template('login.html', portal='Student')


@app.route('/demo-login')
def demo_login():
    conn = get_db()
    row = conn.execute("SELECT id FROM students WHERE student_id='IT2026047'").fetchone()
    conn.close()
    session.clear()
    session['student_id'] = row['id']
    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@student_required
def dashboard():
    conn = get_db()
    s = student(conn)
    sem, current = semester_summary(conn, s)
    sub = sem['subjects'] if sem else []
    notices = notices_for_student(conn, s['current_semester'])
    important = [n for n in notices if n['is_important']]
    today = []
    if s['current_semester']:
        today = today_timetable(conn, s['id'], s['current_semester'])
    leave_stats = leave_summary_for_student(conn, s['id'], s['current_semester'])
    conn.close()
    return render_template(
        'dashboard.html',
        student=s,
        current=current,
        semester=sem,
        subjects=sub,
        insight=predict(current['attended'], current['total'], s['target_attendance']),
        notices=important[:3],
        today_schedule=today,
        greeting=greeting(),
        status_text=status_text(current['percentage']),
        leave_stats=leave_stats,
    )


@app.route('/current-semester')
@student_required
def current_semester():
    conn = get_db()
    s = student(conn)
    sem, current = semester_summary(conn, s)
    sub = sem['subjects'] if sem else []
    notices = [n for n in notices_for_student(conn, s['current_semester']) if n['is_important']]
    conn.close()
    return render_template(
        'semester.html',
        student=s,
        semester=sem,
        subjects=sub,
        attendance=current['percentage'],
        attended=current['attended'],
        total=current['total'],
        absent=current['absent'],
        notices=notices,
    )


@app.route('/semesters')
@student_required
def semesters():
    return redirect(url_for('current_semester'))


@app.route('/semester/<int:semester_id>')
@student_required
def semester_detail(semester_id):
    return redirect(url_for('current_semester'))


@app.route('/timetable')
@student_required
def timetable():
    conn = get_db()
    s = student(conn)
    if not s['current_semester']:
        conn.close()
        return render_template('no_active_semester.html', student=s)
    schedule = timetable_for_student(conn, s['id'], s['current_semester'])
    has_timetable = any(schedule.get(day) for day in DAYS_ORDER)
    conn.close()
    return render_template('timetable.html', student=s, schedule=schedule, days=DAYS_ORDER, has_timetable=has_timetable)


@app.route('/leave-requests', methods=['GET', 'POST'])
@student_required
def leave_requests():
    conn = get_db()
    s = student(conn)
    if not s['current_semester']:
        conn.close()
        return render_template('no_active_semester.html', student=s)
    if request.method == 'POST':
        start_date = request.form.get('start_date', '').strip()
        end_date = request.form.get('end_date', '').strip()
        reason = request.form.get('reason', '').strip()
        file = request.files.get('document')
        if not start_date or not end_date or not reason:
            flash('Start date, end date, and reason are required.', 'error')
        elif start_date > end_date:
            flash('End date must be on or after start date.', 'error')
        elif not file or not file.filename:
            flash('Please upload a leave letter.', 'error')
        elif not allowed_file(file.filename):
            flash('Allowed file types: PDF, DOC, DOCX, JPG, JPEG, PNG.', 'error')
        else:
            filename = save_leave_document(file)
            conn.execute(
                'INSERT INTO leave_requests (student_id,semester_number,start_date,end_date,reason,document_filename,status,created_at) VALUES (?,?,?,?,?,?,\"pending\",?)',
                (s['id'], s['current_semester'], start_date, end_date, reason, filename, datetime.now().isoformat(timespec='seconds')),
            )
            conn.commit()
            flash('Leave request submitted successfully.', 'success')
            conn.close()
            return redirect(url_for('leave_requests'))
    rows = conn.execute(
        'SELECT * FROM leave_requests WHERE student_id=? AND semester_number=? ORDER BY created_at DESC',
        (s['id'], s['current_semester']),
    ).fetchall()
    conn.close()
    return render_template('leave_requests.html', student=s, requests=rows)


@app.route('/leave-requests/document/<int:request_id>')
@student_required
def leave_document(request_id):
    conn = get_db()
    s = student(conn)
    row = conn.execute('SELECT * FROM leave_requests WHERE id=? AND student_id=?', (request_id, s['id'])).fetchone()
    conn.close()
    if not row or not row['document_filename']:
        abort(404)
    return send_from_directory(UPLOAD_DIR, row['document_filename'], as_attachment=False)


@app.route('/notices')
@student_required
def notices():
    conn = get_db()
    s = student(conn)
    rows = notices_for_student(conn, s['current_semester'])
    conn.close()
    return render_template('notices.html', student=s, notices=rows)


@app.route('/calculator')
@student_required
def calculator():
    conn = get_db()
    s = student(conn)
    if not s['current_semester']:
        conn.close()
        return render_template('no_active_semester.html', student=s)
    _, current = semester_summary(conn, s)
    conn.close()
    return render_template('calculator.html', student=s, current=current, semester_label=f"Semester {s['current_semester']}")


@app.route('/analytics')
@student_required
def analytics():
    conn = get_db()
    s = student(conn)
    if not s['current_semester']:
        conn.close()
        return render_template('no_active_semester.html', student=s)
    sem, current = semester_summary(conn, s)
    data = sem['subjects'] if sem else []
    weekly = conn.execute(
        """
        SELECT strftime('%W', ar.record_date) week, COUNT(*) total,
               COALESCE(SUM(ar.status='present'),0) attended
        FROM attendance_records ar
        JOIN subjects su ON su.id = ar.subject_id
        JOIN semesters se ON se.id = su.semester_id
        WHERE se.student_id=? AND se.number=?
        GROUP BY week ORDER BY week DESC LIMIT 8
        """,
        (s['id'], s['current_semester']),
    ).fetchall()
    monthly = conn.execute(
        """
        SELECT strftime('%Y-%m', ar.record_date) month, COUNT(*) total,
               COALESCE(SUM(ar.status='present'),0) attended
        FROM attendance_records ar
        JOIN subjects su ON su.id = ar.subject_id
        JOIN semesters se ON se.id = su.semester_id
        WHERE se.student_id=? AND se.number=?
        GROUP BY month ORDER BY month DESC LIMIT 6
        """,
        (s['id'], s['current_semester']),
    ).fetchall()
    trend = conn.execute(
        """
        SELECT ar.record_date, COUNT(*) total, COALESCE(SUM(ar.status='present'),0) attended
        FROM attendance_records ar
        JOIN subjects su ON su.id = ar.subject_id
        JOIN semesters se ON se.id = su.semester_id
        WHERE se.student_id=? AND se.number=?
        GROUP BY ar.record_date ORDER BY ar.record_date DESC LIMIT 30
        """,
        (s['id'], s['current_semester']),
    ).fetchall()
    conn.close()
    trend_labels = [r['record_date'] for r in reversed(trend)]
    running = []
    a = t = 0
    for r in reversed(trend):
        a += r['attended']
        t += r['total']
        running.append(percent(a, t))
    return render_template(
        'analytics.html',
        student=s,
        current=current,
        semester_label=f"Semester {s['current_semester']}",
        subjects=data,
        weekly=weekly,
        monthly=monthly,
        trend_labels=trend_labels,
        trend_values=running,
        prediction=predict(current['attended'], current['total'], s['target_attendance']),
    )


@app.route('/history')
@student_required
def history():
    conn = get_db()
    s = student(conn)
    if not s['current_semester']:
        conn.close()
        return render_template('no_active_semester.html', student=s)
    rows = conn.execute(
        """
        SELECT ar.*, su.name subject_name, se.label
        FROM attendance_records ar
        JOIN subjects su ON su.id = ar.subject_id
        JOIN semesters se ON se.id = su.semester_id
        WHERE se.student_id=? AND se.number=?
        ORDER BY record_date DESC LIMIT 100
        """,
        (s['id'], s['current_semester']),
    ).fetchall()
    conn.close()
    return render_template('history.html', student=s, records=rows, semester_label=f"Semester {s['current_semester']}")


@app.route('/academic-history')
@student_required
def academic_history():
    conn = get_db()
    s = student(conn)
    history_rows = conn.execute(
        'SELECT * FROM academic_history WHERE student_id=? ORDER BY semester_number ASC',
        (s['id'],),
    ).fetchall()
    # Parse subjects JSON for each row
    history = []
    for row in history_rows:
        entry = dict(row)
        entry['subjects'] = json.loads(entry['subjects_json'])
        entry['status'] = status_label(entry['percentage']) if entry['total_classes'] else 'none'
        history.append(entry)
    conn.close()
    return render_template('academic_history.html', student=s, history=history)


@app.route('/api/calculate')
def api_calculate():
    attended = max(0, request.args.get('attended', type=int) or 0)
    total = max(attended, request.args.get('total', type=int) or 0)
    target = min(99.9, max(1, request.args.get('target', type=float) or 75))
    pct = percent(attended, total)
    return jsonify(percentage=pct, status=status_label(pct), prediction=predict(attended, total, target))


# ─── Admin routes ──────────────────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        conn = get_db()
        row = conn.execute(
            'SELECT * FROM admins WHERE domain_id=? AND password=?',
            (request.form.get('domain_id', '').strip(), request.form.get('password', '')),
        ).fetchone()
        conn.close()
        if row:
            session.clear()
            session['admin_id'] = row['id']
            return redirect(url_for('admin_dashboard'))
        flash('Invalid Domain ID or password.', 'error')
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn = get_db()
    roster = []
    for s in conn.execute('SELECT * FROM students ORDER BY name'):
        _, current = semester_summary(conn, s)
        roster.append({
            **dict(s),
            'percentage': current['percentage'] if current['total'] else None,
            'status': current['status'] if current['total'] else 'none',
        })
    pending_leave_count = conn.execute("SELECT COUNT(*) FROM leave_requests WHERE status='pending'").fetchone()[0]
    conn.close()
    return render_template('admin_dashboard.html', roster=roster, pending_leave_count=pending_leave_count)


@app.route('/admin/students/new', methods=['GET', 'POST'])
@admin_required
def admin_new_student():
    if request.method == 'POST':
        d = request.form
        if not d.get('student_id') or not d.get('password') or not d.get('name'):
            flash('Student ID, password and name are required.', 'error')
        else:
            try:
                new = create_student(
                    d['student_id'].strip(), d['password'], d['name'].strip(),
                    d.get('department', ''), d.get('program', ''), d.get('year', ''), d.get('college', ''),
                    int(d.get('current_semester', 1)),
                )
                flash('Student login created. Add subjects next.', 'success')
                return redirect(url_for('admin_subjects', student_id=new))
            except sqlite3.IntegrityError:
                flash('That Student ID already exists.', 'error')
    return render_template('admin_new_student.html')


@app.route('/admin/students/<int:student_id>/subjects', methods=['GET', 'POST'])
@admin_required
def admin_subjects(student_id):
    conn = get_db()
    s = conn.execute('SELECT * FROM students WHERE id=?', (student_id,)).fetchone()
    if not s:
        conn.close()
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        add_subject_to_semester(
            student_id, request.form.get('semester', type=int),
            request.form.get('name', '').strip(), request.form.get('code', '').strip(),
            request.form.get('faculty', '').strip(), conn,
        )
        flash('Subject added.', 'success')
        return redirect(url_for('admin_subjects', student_id=student_id))
    sems = []
    for sem in conn.execute('SELECT * FROM semesters WHERE student_id=? ORDER BY number', (student_id,)):
        sub = subjects_for_semester(conn, sem['id'])
        sems.append({**dict(sem), 'subject_count': len(sub), 'subjects': sub})
    conn.close()
    return render_template('admin_subjects.html', student=s, semesters=sems)


@app.route('/admin/students/<int:student_id>')
@admin_required
def admin_student(student_id):
    conn = get_db()
    s = conn.execute('SELECT * FROM students WHERE id=?', (student_id,)).fetchone()
    sem, current = semester_summary(conn, s)
    # Academic history for this student
    history_rows = conn.execute(
        'SELECT * FROM academic_history WHERE student_id=? ORDER BY semester_number ASC',
        (student_id,),
    ).fetchall()
    history = []
    for row in history_rows:
        entry = dict(row)
        entry['subjects'] = json.loads(entry['subjects_json'])
        history.append(entry)
    conn.close()
    return render_template('admin_student.html', student=s, semester=sem, current=current, history=history)


@app.route('/admin/students/<int:student_id>/close', methods=['POST'])
@admin_required
def admin_close_semester(student_id):
    conn = get_db()
    s = conn.execute('SELECT * FROM students WHERE id=?', (student_id,)).fetchone()
    if not s or not s['current_semester']:
        flash('No active semester to close.', 'error')
        conn.close()
        return redirect(url_for('admin_student', student_id=student_id))

    sem = get_active_semester_row(conn, s)
    if not sem:
        flash('No active semester found.', 'error')
        conn.close()
        return redirect(url_for('admin_student', student_id=student_id))

    subjects_with_stats = subjects_for_semester(conn, sem['id'])
    close_semester(conn, student_id, s['current_semester'], subjects_with_stats)
    flash(f"Semester {s['current_semester']} has been closed and archived. You can now start a new semester.", 'success')
    conn.close()
    return redirect(url_for('admin_student', student_id=student_id))


@app.route('/admin/students/<int:student_id>/start-semester', methods=['POST'])
@admin_required
def admin_start_semester(student_id):
    conn = get_db()
    s = conn.execute('SELECT * FROM students WHERE id=?', (student_id,)).fetchone()
    if not s:
        conn.close()
        return redirect(url_for('admin_dashboard'))

    # Ensure current semester is closed / no active semester
    if s['current_semester'] is not None:
        active = get_active_semester_row(conn, s)
        if active:
            flash('Cannot start a new semester while one is still active. Close the current semester first.', 'error')
            conn.close()
            return redirect(url_for('admin_student', student_id=student_id))

    new_sem_num = request.form.get('semester_number', type=int)
    if not new_sem_num or new_sem_num < 1 or new_sem_num > 8:
        flash('Please select a valid semester number (1–8).', 'error')
        conn.close()
        return redirect(url_for('admin_student', student_id=student_id))

    # Check if this semester already has archived history - warn but allow
    already_archived = conn.execute(
        'SELECT id FROM academic_history WHERE student_id=? AND semester_number=?',
        (student_id, new_sem_num),
    ).fetchone()
    if already_archived:
        flash(f'Note: Semester {new_sem_num} already has archived history. Starting it again will create fresh data alongside the archive.', 'warning')

    # Reset the semester row for the new semester: clear subjects, timetable, attendance for it
    sem_row = conn.execute(
        'SELECT id FROM semesters WHERE student_id=? AND number=?',
        (student_id, new_sem_num),
    ).fetchone()
    if sem_row:
        # Delete attendance records for subjects in this semester
        conn.execute(
            '''DELETE FROM attendance_records WHERE subject_id IN
               (SELECT id FROM subjects WHERE semester_id=?)''',
            (sem_row['id'],),
        )
        conn.execute('DELETE FROM subjects WHERE semester_id=?', (sem_row['id'],))
        conn.execute(
            'UPDATE semesters SET is_active=0, is_closed=0 WHERE student_id=?',
            (student_id,),
        )
        conn.execute(
            'UPDATE semesters SET is_active=1 WHERE student_id=? AND number=?',
            (student_id, new_sem_num),
        )
    else:
        # Create the semester row if it doesn't exist
        conn.execute(
            'INSERT INTO semesters (student_id,number,label,is_active,is_closed) VALUES (?,?,?,1,0)',
            (student_id, new_sem_num, f'Semester {new_sem_num}'),
        )

    # Clear timetable entries for the new semester
    conn.execute(
        'DELETE FROM timetable_entries WHERE student_id=? AND semester_number=?',
        (student_id, new_sem_num),
    )

    # Update the student's current_semester
    conn.execute('UPDATE students SET current_semester=? WHERE id=?', (new_sem_num, student_id))
    conn.commit()
    flash(f'Semester {new_sem_num} has been started for {s["name"]}. Please add subjects and timetable.', 'success')
    conn.close()
    return redirect(url_for('admin_subjects', student_id=student_id))


@app.route('/admin/timetable', methods=['GET', 'POST'])
@admin_required
def admin_timetable():
    conn = get_db()
    students = conn.execute('SELECT * FROM students ORDER BY name').fetchall()
    selected_id = request.form.get('student_id', type=int) or request.args.get('student_id', type=int) or (students[0]['id'] if students else None)
    selected = conn.execute('SELECT * FROM students WHERE id=?', (selected_id,)).fetchone() if selected_id else None

    if request.method == 'POST' and selected:
        action = request.form.get('action')
        if action == 'add':
            conn.execute(
                'INSERT INTO timetable_entries (student_id,semester_number,day_of_week,start_time,end_time,subject,room,faculty) VALUES (?,?,?,?,?,?,?,?)',
                (
                    selected['id'], selected['current_semester'],
                    request.form.get('day_of_week', '').upper(),
                    request.form.get('start_time', ''), request.form.get('end_time', ''),
                    request.form.get('subject', ''), request.form.get('room', ''), request.form.get('faculty', ''),
                ),
            )
            conn.commit()
            flash('Timetable entry added.', 'success')
        elif action == 'edit':
            conn.execute(
                'UPDATE timetable_entries SET day_of_week=?, start_time=?, end_time=?, subject=?, room=?, faculty=? WHERE id=? AND student_id=?',
                (
                    request.form.get('day_of_week', '').upper(),
                    request.form.get('start_time', ''), request.form.get('end_time', ''),
                    request.form.get('subject', ''), request.form.get('room', ''), request.form.get('faculty', ''),
                    request.form.get('entry_id', type=int), selected['id'],
                ),
            )
            conn.commit()
            flash('Timetable entry updated.', 'success')
        elif action == 'delete':
            conn.execute(
                'DELETE FROM timetable_entries WHERE id=? AND student_id=?',
                (request.form.get('entry_id', type=int), selected['id']),
            )
            conn.commit()
            flash('Timetable entry deleted.', 'success')
        return redirect(url_for('admin_timetable', student_id=selected['id']))

    entries = []
    has_timetable = False
    if selected and selected['current_semester']:
        entries = conn.execute(
            'SELECT * FROM timetable_entries WHERE student_id=? AND semester_number=? ORDER BY day_of_week, start_time',
            (selected['id'], selected['current_semester']),
        ).fetchall()
        has_timetable = bool(entries)
    conn.close()
    return render_template('admin_timetable.html', students=students, selected=selected, entries=entries, days=DAYS_ORDER, has_timetable=has_timetable)


@app.route('/admin/leave-requests', methods=['GET', 'POST'])
@admin_required
def admin_leave_requests():
    conn = get_db()
    if request.method == 'POST':
        req_id = request.form.get('request_id', type=int)
        action = request.form.get('action')
        note = request.form.get('admin_note', '').strip()
        if action in ('approved', 'rejected'):
            conn.execute(
                'UPDATE leave_requests SET status=?, admin_note=? WHERE id=?',
                (action, note or None, req_id),
            )
            conn.commit()
            flash(f'Leave request {action}.', 'success')
        return redirect(url_for('admin_leave_requests'))

    filter_status = request.args.get('status', 'all')
    if filter_status == 'pending':
        rows = conn.execute(
            """
            SELECT lr.*, s.name student_name, s.student_id login_id, s.current_semester
            FROM leave_requests lr
            JOIN students s ON s.id = lr.student_id
            WHERE lr.status='pending'
            ORDER BY lr.created_at DESC
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT lr.*, s.name student_name, s.student_id login_id, s.current_semester
            FROM leave_requests lr
            JOIN students s ON s.id = lr.student_id
            ORDER BY lr.created_at DESC
            """
        ).fetchall()
    conn.close()
    return render_template('admin_leave_requests.html', requests=rows, filter_status=filter_status)


@app.route('/admin/leave-requests/document/<int:request_id>')
@admin_required
def admin_leave_document(request_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM leave_requests WHERE id=?', (request_id,)).fetchone()
    conn.close()
    if not row or not row['document_filename']:
        abort(404)
    return send_from_directory(UPLOAD_DIR, row['document_filename'], as_attachment=True)


@app.route('/admin/notices', methods=['GET', 'POST'])
@admin_required
def admin_notices():
    conn = get_db()
    # Get current semesters for all active students
    active_semesters = conn.execute(
        "SELECT DISTINCT current_semester FROM students WHERE current_semester IS NOT NULL ORDER BY current_semester"
    ).fetchall()
    active_sem_numbers = [r['current_semester'] for r in active_semesters]

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            sem = request.form.get('semester_number', '').strip()
            semester_number = None if sem == 'all' else int(sem)
            conn.execute(
                'INSERT INTO notices (title,message,semester_number,is_important,created_at) VALUES (?,?,?,?,?)',
                (
                    request.form.get('title', '').strip(),
                    request.form.get('message', '').strip(),
                    semester_number,
                    1 if request.form.get('is_important') else 0,
                    datetime.now().isoformat(timespec='seconds'),
                ),
            )
            conn.commit()
            flash('Notice created.', 'success')
        elif action == 'edit':
            sem = request.form.get('semester_number', '').strip()
            semester_number = None if sem == 'all' else int(sem)
            conn.execute(
                'UPDATE notices SET title=?, message=?, semester_number=?, is_important=? WHERE id=?',
                (
                    request.form.get('title', '').strip(),
                    request.form.get('message', '').strip(),
                    semester_number,
                    1 if request.form.get('is_important') else 0,
                    request.form.get('notice_id', type=int),
                ),
            )
            conn.commit()
            flash('Notice updated.', 'success')
        elif action == 'delete':
            conn.execute('DELETE FROM notices WHERE id=?', (request.form.get('notice_id', type=int),))
            conn.commit()
            flash('Notice deleted.', 'success')
        return redirect(url_for('admin_notices'))

    rows = conn.execute('SELECT * FROM notices ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin_notices.html', notices=rows, active_sem_numbers=active_sem_numbers)


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
