# SmartAttend — Calculation-Only Attendance Portal

SmartAttend is a Flask + SQLite attendance analysis project for an SIH demonstration. It has two independent login portals and an iOS-inspired glassmorphism interface.

## What it does

- **Student portal:** sign in with Student ID; view all eight semesters, subject breakdowns, attendance calculator, prediction, analytics, and read-only history.
- **Domain/Admin portal:** sign in with Domain ID; create student credentials, set up subjects, and review each student's calculated attendance.
- **No attendance marking:** there is no form or API route that creates attendance records. The included SQLite database contains demo/imported records used only for viewing and calculation.
- Semester percentages are calculated correctly: `sum(attended classes) / sum(conducted classes) × 100`.

## Run locally

Requires Python 3.9 or newer.

```bash
cd smartattend
python -m pip install -r requirements.txt
python database.py
python app.py
```

Open http://127.0.0.1:5000.

## Demo credentials

| Portal | ID | Password |
| --- | --- | --- |
| Student | `IT2026047` | `demo123` |
| Domain/Admin | `ADMIN001` | `admin123` |

## Project layout

```text
smartattend/
  app.py                 Flask application and attendance calculations
  database.py            SQLite schema and deterministic demo-data initializer
  database.db            Created by `python database.py`
  templates/             Student and Domain/Admin Jinja pages
  static/css/style.css   Responsive iOS-inspired glassmorphism design
  static/js/app.js       Calculator and analytics chart interactions
```

## Important note

This is an SIH demo application. In a production deployment, replace plaintext demo passwords with hashed passwords, use a production secret key, add CSRF protection, and connect imported attendance data from the institution's authorised source.
