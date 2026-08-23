"""SQLite schema, helpers, migrations, and deterministic demo data for SmartAttend."""
import json
import os
import random
import sqlite3
from datetime import date, datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads", "leaves")
SUBJECT_BANK = {
    1: [("Engineering Mathematics I", "MA101"), ("Physics", "PH101"), ("Programming in C", "CS101"), ("Basic Electrical Engineering", "EE101")],
    2: [("Engineering Mathematics II", "MA102"), ("Chemistry", "CH101"), ("Data Structures", "CS102"), ("Digital Logic Design", "CS103")],
    3: [("Data Structures", "CS201"), ("Operating Systems", "CS202"), ("Computer Networks", "CS203"), ("Discrete Mathematics", "MA201"), ("Object Oriented Programming", "CS204")],
    4: [("Database Management Systems", "CS205"), ("Computer Organization", "CS206"), ("Algorithms", "CS207"), ("Software Engineering", "CS208")],
    5: [("Web Technologies", "CS301"), ("Artificial Intelligence", "CS302"), ("Operating Systems Lab", "CS303"), ("Compiler Design", "CS304")],
    6: [("Machine Learning", "CS306"), ("Cloud Computing", "CS307"), ("Cyber Security", "CS308"), ("Mobile App Development", "CS309")],
    7: [("Big Data Analytics", "CS401"), ("Internet of Things", "CS402"), ("Elective II", "CS4E2"), ("Project Phase I", "CS403")],
    8: [("Project Phase II", "CS404"), ("Elective IV", "CS4E4"), ("Seminar", "CS405")],
}

SCHEMA = '''
CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, student_id TEXT UNIQUE NOT NULL, password TEXT NOT NULL, name TEXT NOT NULL, department TEXT, program TEXT, year TEXT, college TEXT, current_semester INTEGER DEFAULT 1, target_attendance REAL DEFAULT 75, theme TEXT DEFAULT 'system');
CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY, domain_id TEXT UNIQUE NOT NULL, password TEXT NOT NULL, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS semesters (id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, number INTEGER NOT NULL, label TEXT NOT NULL, is_active INTEGER DEFAULT 0, is_closed INTEGER DEFAULT 0, UNIQUE(student_id, number), FOREIGN KEY(student_id) REFERENCES students(id));
CREATE TABLE IF NOT EXISTS subjects (id INTEGER PRIMARY KEY, semester_id INTEGER NOT NULL, name TEXT NOT NULL, code TEXT, faculty TEXT, FOREIGN KEY(semester_id) REFERENCES semesters(id));
CREATE TABLE IF NOT EXISTS attendance_records (id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL, record_date TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('present','absent')), FOREIGN KEY(subject_id) REFERENCES subjects(id));
CREATE TABLE IF NOT EXISTS timetable_entries (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL,
    semester_number INTEGER NOT NULL,
    day_of_week TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    subject TEXT NOT NULL,
    room TEXT,
    faculty TEXT,
    FOREIGN KEY(student_id) REFERENCES students(id)
);
CREATE TABLE IF NOT EXISTS leave_requests (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL,
    semester_number INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    reason TEXT NOT NULL,
    document_filename TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
    admin_note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(student_id) REFERENCES students(id)
);
CREATE TABLE IF NOT EXISTS notices (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    semester_number INTEGER,
    is_important INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS academic_history (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL,
    semester_number INTEGER NOT NULL,
    semester_label TEXT NOT NULL,
    total_classes INTEGER NOT NULL DEFAULT 0,
    attended_classes INTEGER NOT NULL DEFAULT 0,
    absent_classes INTEGER NOT NULL DEFAULT 0,
    percentage REAL NOT NULL DEFAULT 0,
    subjects_json TEXT NOT NULL DEFAULT '[]',
    closed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(student_id) REFERENCES students(id)
);
'''


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def create_student(student_id, password, name, department='', program='', year='', college='', current_semester=1, target_attendance=75, conn=None):
    own = conn is None
    conn = conn or get_db()
    cur = conn.execute(
        'INSERT INTO students (student_id,password,name,department,program,year,college,current_semester,target_attendance) VALUES (?,?,?,?,?,?,?,?,?)',
        (student_id, password, name, department, program, year, college, current_semester, target_attendance),
    )
    student_db_id = cur.lastrowid
    # Only create the semesters up to and including the current one as placeholders
    for number in range(1, 9):
        conn.execute(
            'INSERT INTO semesters (student_id,number,label,is_active,is_closed) VALUES (?,?,?,?,?)',
            (student_db_id, number, f'Semester {number}', 1 if number == current_semester else 0, 0),
        )
    conn.commit()
    if own:
        conn.close()
    return student_db_id


def add_subject_to_semester(student_db_id, semester_number, name, code='', faculty='', conn=None):
    own = conn is None
    conn = conn or get_db()
    sem = conn.execute('SELECT id FROM semesters WHERE student_id=? AND number=?', (student_db_id, semester_number)).fetchone()
    if not sem:
        if own:
            conn.close()
        return None
    cur = conn.execute('INSERT INTO subjects (semester_id,name,code,faculty) VALUES (?,?,?,?)', (sem['id'], name, code, faculty))
    conn.commit()
    subject_id = cur.lastrowid
    if own:
        conn.close()
    return subject_id


def sync_active_semester(conn, student_id, current_semester):
    conn.execute('UPDATE semesters SET is_active=0 WHERE student_id=?', (student_id,))
    conn.execute('UPDATE semesters SET is_active=1 WHERE student_id=? AND number=?', (student_id, current_semester))


def close_semester(conn, student_db_id, semester_number, subjects_with_stats):
    """Archive the semester summary into academic_history and mark it closed."""
    total = sum(s['total'] for s in subjects_with_stats)
    attended = sum(s['attended'] for s in subjects_with_stats)
    absent = total - attended
    pct = round(attended * 100 / total, 1) if total else 0.0
    subjects_json = json.dumps([
        {
            'name': s['name'],
            'code': s.get('code', ''),
            'faculty': s.get('faculty', ''),
            'attended': s['attended'],
            'total': s['total'],
            'absent': s['total'] - s['attended'],
            'percentage': s['percentage'],
        }
        for s in subjects_with_stats
    ])
    closed_at = datetime.now().isoformat(timespec='seconds')
    conn.execute(
        '''INSERT OR REPLACE INTO academic_history
           (student_id, semester_number, semester_label, total_classes, attended_classes, absent_classes, percentage, subjects_json, closed_at)
           VALUES (?,?,?,?,?,?,?,?,?)''',
        (student_db_id, semester_number, f'Semester {semester_number}', total, attended, absent, pct, subjects_json, closed_at),
    )
    conn.execute(
        'UPDATE semesters SET is_active=0, is_closed=1 WHERE student_id=? AND number=?',
        (student_db_id, semester_number),
    )
    conn.execute(
        'UPDATE students SET current_semester=NULL WHERE id=?',
        (student_db_id,),
    )
    conn.commit()


def seed_timetable_demo(conn, student_db_id, semester_number):
    if conn.execute('SELECT COUNT(*) FROM timetable_entries WHERE student_id=? AND semester_number=?', (student_db_id, semester_number)).fetchone()[0]:
        return
    subjects = SUBJECT_BANK.get(semester_number, [])
    if not subjects:
        return
    schedule = [
        ('MONDAY', '09:00', '10:00', subjects[0][0], 'A204', 'Dr. Sharma'),
        ('MONDAY', '10:00', '11:00', subjects[1][0], 'A205', 'Prof. Kumar'),
        ('TUESDAY', '09:00', '10:00', subjects[2][0], 'B101', 'Dr. Patel'),
        ('WEDNESDAY', '11:00', '12:00', subjects[3][0], 'C302', 'Prof. Reddy'),
        ('THURSDAY', '14:00', '15:00', subjects[0][0], 'Lab-1', 'Dr. Sharma'),
        ('FRIDAY', '10:00', '11:00', subjects[1][0], 'A205', 'Prof. Kumar'),
    ]
    if len(subjects) > 4:
        schedule.append(('FRIDAY', '15:00', '16:00', subjects[4][0], 'D110', 'Dr. Iyer'))
    for day, start, end, subject, room, faculty in schedule:
        conn.execute(
            'INSERT INTO timetable_entries (student_id,semester_number,day_of_week,start_time,end_time,subject,room,faculty) VALUES (?,?,?,?,?,?,?,?)',
            (student_db_id, semester_number, day, start, end, subject, room, faculty),
        )


def seed_notices_demo(conn, semester_number):
    if conn.execute('SELECT COUNT(*) FROM notices').fetchone()[0]:
        return
    now = datetime.now().isoformat(timespec='seconds')
    conn.execute(
        'INSERT INTO notices (title,message,semester_number,is_important,created_at) VALUES (?,?,?,?,?)',
        ('Mid-Semester Attendance Review', f'Semester {semester_number} students must maintain at least 75% attendance before the mid-semester evaluation.', semester_number, 1, now),
    )
    conn.execute(
        'INSERT INTO notices (title,message,semester_number,is_important,created_at) VALUES (?,?,?,?,?)',
        ('Library Extended Hours', 'Central library will remain open until 9 PM during exam preparation week.', None, 0, now),
    )
    conn.execute(
        'INSERT INTO notices (title,message,semester_number,is_important,created_at) VALUES (?,?,?,?,?)',
        ('Lab Schedule Update', f'Please check your updated lab timetable for Semester {semester_number} on the Timetable page.', semester_number, 0, now),
    )


def seed_demo_data(conn):
    conn.execute('INSERT OR IGNORE INTO admins (domain_id,password,name) VALUES (?,?,?)', ('ADMIN001', 'admin123', 'Domain Administrator'))
    random.seed(2026)
    current_sem = 3
    student_db_id = create_student(
        'IT2026047', 'demo123', 'Jagadeesh', 'Information Technology', 'B.Tech IT', '3rd Year',
        'Sri Sairam Institute of Technology', current_sem, 75, conn,
    )
    # Restore current_semester since create_student sets it properly but we need it as integer
    conn.execute('UPDATE students SET current_semester=? WHERE id=?', (current_sem, student_db_id))
    targets = {1: 84, 2: 89, 3: 77, 4: 70, 5: 74}
    for number, subjects in SUBJECT_BANK.items():
        sem = conn.execute('SELECT id FROM semesters WHERE student_id=? AND number=?', (student_db_id, number)).fetchone()['id']
        for name, code in subjects:
            sid = conn.execute(
                'INSERT INTO subjects (semester_id,name,code,faculty) VALUES (?,?,?,?)',
                (sem, name, code, 'Faculty ' + str(random.randint(1, 8))),
            ).lastrowid
            if number <= current_sem:
                start = date.today() - timedelta(days=(35 if number == current_sem else 105))
                score = targets.get(number, 75) + random.randint(-7, 7)
                for day in (start + timedelta(days=n) for n in range((date.today() - start).days)):
                    if day.weekday() < 6:
                        conn.execute(
                            'INSERT INTO attendance_records (subject_id,record_date,status) VALUES (?,?,?)',
                            (sid, day.isoformat(), 'present' if random.randint(1, 100) <= score else 'absent'),
                        )

    # Mark semesters 1 and 2 as closed with academic history snapshots
    for closed_sem in [1, 2]:
        sem_row = conn.execute('SELECT id FROM semesters WHERE student_id=? AND number=?', (student_db_id, closed_sem)).fetchone()
        sem_subjects = conn.execute('SELECT * FROM subjects WHERE semester_id=?', (sem_row['id'],)).fetchall()
        subjects_data = []
        for s in sem_subjects:
            row = conn.execute(
                "SELECT COUNT(*) total, COALESCE(SUM(status='present'),0) attended FROM attendance_records WHERE subject_id=?",
                (s['id'],),
            ).fetchone()
            attended_c = row['attended']
            total_c = row['total']
            pct = round(attended_c * 100 / total_c, 1) if total_c else 0.0
            subjects_data.append({
                'name': s['name'], 'code': s['code'] or '', 'faculty': s['faculty'] or '',
                'attended': attended_c, 'total': total_c, 'absent': total_c - attended_c, 'percentage': pct,
            })
        tot = sum(x['total'] for x in subjects_data)
        att = sum(x['attended'] for x in subjects_data)
        pct_overall = round(att * 100 / tot, 1) if tot else 0.0
        closed_at = (datetime.now() - timedelta(days=200 - closed_sem * 70)).isoformat(timespec='seconds')
        conn.execute(
            '''INSERT INTO academic_history
               (student_id, semester_number, semester_label, total_classes, attended_classes, absent_classes, percentage, subjects_json, closed_at)
               VALUES (?,?,?,?,?,?,?,?,?)''',
            (student_db_id, closed_sem, f'Semester {closed_sem}', tot, att, tot - att, pct_overall, json.dumps(subjects_data), closed_at),
        )
        conn.execute(
            'UPDATE semesters SET is_active=0, is_closed=1 WHERE student_id=? AND number=?',
            (student_db_id, closed_sem),
        )

    sync_active_semester(conn, student_db_id, current_sem)
    seed_timetable_demo(conn, student_db_id, current_sem)
    seed_notices_demo(conn, current_sem)


def migrate_existing(conn):
    # Add is_closed column if missing
    try:
        conn.execute('ALTER TABLE semesters ADD COLUMN is_closed INTEGER DEFAULT 0')
        conn.commit()
    except Exception:
        pass  # Column already exists

    # Add academic_history table if missing
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS academic_history (
            id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL,
            semester_number INTEGER NOT NULL,
            semester_label TEXT NOT NULL,
            total_classes INTEGER NOT NULL DEFAULT 0,
            attended_classes INTEGER NOT NULL DEFAULT 0,
            absent_classes INTEGER NOT NULL DEFAULT 0,
            percentage REAL NOT NULL DEFAULT 0,
            subjects_json TEXT NOT NULL DEFAULT '[]',
            closed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id)
        );
    ''')

    for row in conn.execute('SELECT id, current_semester FROM students WHERE current_semester IS NOT NULL'):
        sync_active_semester(conn, row['id'], row['current_semester'])
    demo = conn.execute("SELECT id, current_semester FROM students WHERE student_id='IT2026047'").fetchone()
    if demo and demo['current_semester']:
        seed_timetable_demo(conn, demo['id'], demo['current_semester'])
        seed_notices_demo(conn, demo['current_semester'])


def init_db(reset=False):
    fresh = reset or not os.path.exists(DB_PATH)
    conn = get_db()
    conn.executescript(SCHEMA)
    ensure_upload_dir()

    if reset:
        conn.executescript(
            'DELETE FROM academic_history; DELETE FROM leave_requests; DELETE FROM notices; DELETE FROM timetable_entries; '
            'DELETE FROM attendance_records; DELETE FROM subjects; DELETE FROM semesters; DELETE FROM students; DELETE FROM admins;'
        )

    has_students = conn.execute('SELECT COUNT(*) FROM students').fetchone()[0] > 0
    if fresh or reset or not has_students:
        seed_demo_data(conn)
    else:
        migrate_existing(conn)

    conn.commit()
    conn.close()


if __name__ == '__main__':
    init_db(reset=True)
    print('Created demo database:', DB_PATH)
