# SmartAttend — Current-Semester Attendance Portal

SmartAttend is a Flask + SQLite attendance and academic portal for an SIH demonstration. It uses an iOS-inspired glassmorphism interface with two independent login portals.

## Current-semester architecture

SmartAttend is a **current-semester** system. Each student has a `current_semester` field (for example, `3`). The entire student portal works around that semester only:

- Dashboard, subjects, calculator, analytics, and history use **current-semester attendance only**
- Previous semesters remain in the database as academic history but are **not** combined into the primary attendance percentage
- Timetable, leave requests, and notices are scoped to the student's current semester
- Students do not manually pick a semester for normal attendance tracking

## What it does

### Student portal

Sign in with Student ID to access:

- **Home** — current-semester attendance, subjects, important notices, today's timetable, smart insight
- **Current Semester** — semester attendance breakdown and subject list
- **Timetable** — read-only weekly schedule published by admin
- **Leave Requests** — submit leave with document upload; track status and admin notes
- **Notices** — semester-specific and all-student announcements
- **Calculator** — defaults to current-semester attendance
- **Analytics** — current-semester charts and prediction
- **History** — read-only current-semester attendance records

### Domain/Admin portal

Sign in with Domain ID to:

- Create and manage student accounts
- Add subjects to semesters
- Publish/edit/delete **current-semester timetables** per student
- Approve or reject **leave requests** with optional admin notes
- Create/edit/delete **notices** (semester-specific or all students)
- View each student's **current-semester attendance** and status

### Attendance is read-only

There is **no attendance marking**. Students and admins cannot create or edit attendance records. The SQLite database contains imported/demo records used only for viewing and calculation.

Semester percentage formula: `sum(attended classes) / sum(conducted classes) × 100`

Status thresholds:

- **Safe** — ≥ 75%
- **Warning** — 65–74.99%
- **Critical** — < 65%

## Run locally

Requires Python 3.9 or newer.

```bash
cd smartattend
python -m pip install -r requirements.txt
python database.py
python app.py
```

Open http://127.0.0.1:5000

To recreate demo data from scratch:

```bash
python database.py
```

Existing databases are migrated safely — new tables are added with `CREATE TABLE IF NOT EXISTS` without deleting student or attendance data.

## Demo credentials

| Portal | ID | Password |
| --- | --- | --- |
| Student | `IT2026047` | `demo123` |
| Domain/Admin | `ADMIN001` | `admin123` |

Demo student **Jagadeesh** is in **Semester 3** with current-semester subjects, attendance, timetable, and notices seeded automatically.

## File uploads (leave requests)

Leave letters are stored in:

```text
uploads/leaves/
```

Files are saved with unique UUID-based filenames. Allowed types:

- PDF, DOC, DOCX, JPG, JPEG, PNG
- Maximum size: 5 MB

Students can only download their own documents. Admins can download any leave document.

## Security and access rules

| Action | Student | Admin |
| --- | --- | --- |
| View own current-semester attendance | ✓ | ✓ (all students) |
| View own timetable | ✓ | — |
| Submit leave request | ✓ | — |
| Approve/reject leave | ✗ | ✓ |
| View notices for current semester + all | ✓ | — |
| Create/edit/delete notices | ✗ | ✓ |
| Create/edit/delete timetable | ✗ | ✓ |
| Mark or edit attendance | ✗ | ✗ |

Student routes require student login. Admin routes require admin login. Students cannot access another student's timetable, leave documents, or attendance.

## Project layout

```text
smartattend/
  app.py                 Flask routes, current-semester logic, file uploads
  database.py            SQLite schema, migrations, demo data
  database.db            Created/updated by database.py
  uploads/leaves/        Uploaded leave documents
  templates/             Student and admin Jinja pages
  static/css/style.css   Glassmorphism UI
  static/js/app.js       Calculator and chart interactions
```

## Database tables

Existing tables: `students`, `admins`, `semesters`, `subjects`, `attendance_records`

Added safely:

- `timetable_entries` — admin-published weekly schedules
- `leave_requests` — student leave submissions and admin responses
- `notices` — announcement board

## Important note

This is an SIH demo application. In production, replace plaintext demo passwords with hashed passwords, use a production secret key, add CSRF protection, and connect attendance data from the institution's authorised source.
