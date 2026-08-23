"""SQLite schema, helpers, and deterministic demo data for SmartAttend."""
import os
import random
import sqlite3
from datetime import date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")
SUBJECT_BANK = {
    1: [("Engineering Mathematics I", "MA101"), ("Physics", "PH101"), ("Programming in C", "CS101"), ("Basic Electrical Engineering", "EE101")],
    2: [("Engineering Mathematics II", "MA102"), ("Chemistry", "CH101"), ("Data Structures", "CS102"), ("Digital Logic Design", "CS103")],
    3: [("Data Structures", "CS201"), ("Operating Systems", "CS202"), ("Computer Networks", "CS203"), ("Discrete Mathematics", "MA201")],
    4: [("Database Management Systems", "CS205"), ("Computer Organization", "CS206"), ("Algorithms", "CS207"), ("Software Engineering", "CS208")],
    5: [("Web Technologies", "CS301"), ("Artificial Intelligence", "CS302"), ("Operating Systems Lab", "CS303"), ("Compiler Design", "CS304")],
    6: [("Machine Learning", "CS306"), ("Cloud Computing", "CS307"), ("Cyber Security", "CS308"), ("Mobile App Development", "CS309")],
    7: [("Big Data Analytics", "CS401"), ("Internet of Things", "CS402"), ("Elective II", "CS4E2"), ("Project Phase I", "CS403")],
    8: [("Project Phase II", "CS404"), ("Elective IV", "CS4E4"), ("Seminar", "CS405")],
}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, student_id TEXT UNIQUE NOT NULL, password TEXT NOT NULL, name TEXT NOT NULL, department TEXT, program TEXT, year TEXT, college TEXT, current_semester INTEGER DEFAULT 1, target_attendance REAL DEFAULT 75, theme TEXT DEFAULT 'system');
CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY, domain_id TEXT UNIQUE NOT NULL, password TEXT NOT NULL, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS semesters (id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, number INTEGER NOT NULL, label TEXT NOT NULL, is_active INTEGER DEFAULT 0, UNIQUE(student_id, number), FOREIGN KEY(student_id) REFERENCES students(id));
CREATE TABLE IF NOT EXISTS subjects (id INTEGER PRIMARY KEY, semester_id INTEGER NOT NULL, name TEXT NOT NULL, code TEXT, faculty TEXT, FOREIGN KEY(semester_id) REFERENCES semesters(id));
CREATE TABLE IF NOT EXISTS attendance_records (id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL, record_date TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('present','absent')), FOREIGN KEY(subject_id) REFERENCES subjects(id));
'''

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def create_student(student_id, password, name, department='', program='', year='', college='', current_semester=1, target_attendance=75, conn=None):
    own = conn is None; conn = conn or get_db()
    cur = conn.execute('INSERT INTO students (student_id,password,name,department,program,year,college,current_semester,target_attendance) VALUES (?,?,?,?,?,?,?,?,?)', (student_id,password,name,department,program,year,college,current_semester,target_attendance))
    for number in range(1, 9):
        conn.execute('INSERT INTO semesters (student_id,number,label,is_active) VALUES (?,?,?,?)', (cur.lastrowid,number,f'Semester {number}',number == current_semester))
    conn.commit()
    if own: conn.close()
    return cur.lastrowid

def add_subject_to_semester(student_db_id, semester_number, name, code='', faculty='', conn=None):
    own = conn is None; conn = conn or get_db()
    sem = conn.execute('SELECT id FROM semesters WHERE student_id=? AND number=?', (student_db_id, semester_number)).fetchone()
    if not sem:
        if own: conn.close()
        return None
    cur = conn.execute('INSERT INTO subjects (semester_id,name,code,faculty) VALUES (?,?,?,?)', (sem['id'],name,code,faculty))
    conn.commit()
    if own: conn.close()
    return cur.lastrowid

def init_db(reset=False):
    fresh = reset or not os.path.exists(DB_PATH)
    conn = get_db(); conn.executescript(SCHEMA)
    if not fresh and conn.execute('SELECT COUNT(*) FROM students').fetchone()[0]:
        conn.close(); return
    if reset: conn.executescript('DELETE FROM attendance_records; DELETE FROM subjects; DELETE FROM semesters; DELETE FROM students; DELETE FROM admins;')
    conn.execute('INSERT INTO admins (domain_id,password,name) VALUES (?,?,?)', ('ADMIN001','admin123','Domain Administrator'))
    random.seed(2026)
    student = create_student('IT2026047','demo123','Jagadeesh','Information Technology','B.Tech IT','3rd Year','Sri Sairam Institute of Technology',5,75,conn)
    targets={1:84,2:89,3:77,4:70,5:74}
    for number, subjects in SUBJECT_BANK.items():
        sem = conn.execute('SELECT id FROM semesters WHERE student_id=? AND number=?', (student,number)).fetchone()['id']
        for name, code in subjects:
            sid=conn.execute('INSERT INTO subjects (semester_id,name,code,faculty) VALUES (?,?,?,?)',(sem,name,code,'Faculty '+str(random.randint(1,8)))).lastrowid
            if number <= 5:
                start=date.today()-timedelta(days=(35 if number==5 else 105)); score=targets[number]+random.randint(-7,7)
                for day in (start+timedelta(days=n) for n in range((date.today()-start).days)):
                    if day.weekday()<6: conn.execute('INSERT INTO attendance_records (subject_id,record_date,status) VALUES (?,?,?)',(sid,day.isoformat(),'present' if random.randint(1,100)<=score else 'absent'))
    conn.commit(); conn.close()

if __name__ == '__main__':
    init_db(reset=True); print('Created demo database:', DB_PATH)
