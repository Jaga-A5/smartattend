"""SmartAttend: calculation-only student and domain portals."""
import math, sqlite3
from datetime import date, timedelta
from functools import wraps
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from database import add_subject_to_semester, create_student, get_db, init_db

app=Flask(__name__); app.config['SECRET_KEY']='change-this-demo-secret'
init_db()
def percent(a,t): return round(a*100/t,1) if t else 0.0
def status(value): return 'safe' if value>=75 else ('warning' if value>=65 else 'critical')
def predict(a,t,target):
    p=percent(a,t)
    if not t: return {'kind':'neutral','message':'No attendance data has been imported for this selection.'}
    if p>=target:
        n=max(0,math.floor(a*100/target-t)); return {'kind':'positive','message':f'You can miss {n} more class'+('es' if n!=1 else '')+f' and remain at or above {target:g}%.'}
    n=max(0,math.ceil((target*t-100*a)/(100-target))); return {'kind':'warning','message':f'Attend the next {n} class'+('es' if n!=1 else '')+f' to reach {target:g}%.'}
def student_required(f):
    @wraps(f)
    def inner(*a,**k): return f(*a,**k) if session.get('student_id') else redirect(url_for('login'))
    return inner
def admin_required(f):
    @wraps(f)
    def inner(*a,**k): return f(*a,**k) if session.get('admin_id') else redirect(url_for('admin_login'))
    return inner
def stats(conn, subject_id):
    r=conn.execute("SELECT COUNT(*) total, COALESCE(SUM(status='present'),0) attended FROM attendance_records WHERE subject_id=?",(subject_id,)).fetchone(); return r['attended'],r['total']
def subjects(conn, sem_id):
    result=[]
    for s in conn.execute('SELECT * FROM subjects WHERE semester_id=? ORDER BY name',(sem_id,)):
        a,t=stats(conn,s['id']); result.append({**dict(s),'attended':a,'total':t,'absent':t-a,'percentage':percent(a,t),'status':status(percent(a,t)) if t else 'none'})
    return result
def summary(conn, student_id):
    all=[]
    for sem in conn.execute('SELECT * FROM semesters WHERE student_id=? ORDER BY number',(student_id,)):
        ss=subjects(conn,sem['id']); a=sum(x['attended'] for x in ss); t=sum(x['total'] for x in ss); all.append({**dict(sem),'attended':a,'total':t,'percentage':percent(a,t) if t else None,'status':status(percent(a,t)) if t else 'none','subject_count':len(ss)})
    a=sum(x['attended'] for x in all); t=sum(x['total'] for x in all); return all,{'attended':a,'total':t,'absent':t-a,'percentage':percent(a,t)}
def student(conn): return conn.execute('SELECT * FROM students WHERE id=?',(session['student_id'],)).fetchone()

@app.route('/')
def index(): return redirect(url_for('dashboard' if session.get('student_id') else 'admin_dashboard' if session.get('admin_id') else 'login'))
@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        conn=get_db(); row=conn.execute('SELECT * FROM students WHERE student_id=? AND password=?',(request.form.get('student_id','').strip(),request.form.get('password',''))).fetchone(); conn.close()
        if row: session.clear(); session['student_id']=row['id']; return redirect(url_for('dashboard'))
        flash('Invalid Student ID or password.','error')
    return render_template('login.html',portal='Student')
@app.route('/demo-login')
def demo_login():
    conn=get_db(); row=conn.execute("SELECT id FROM students WHERE student_id='IT2026047'").fetchone(); conn.close(); session.clear(); session['student_id']=row['id']; return redirect(url_for('dashboard'))
@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))
@app.route('/dashboard')
@student_required
def dashboard():
    conn=get_db(); s=student(conn); semesters,overall=summary(conn,s['id']); active=next(x for x in semesters if x['is_active']); sub=subjects(conn,active['id']); conn.close()
    return render_template('dashboard.html',student=s,overall=overall,active=active,subjects=sub,insight=predict(overall['attended'],overall['total'],s['target_attendance']))
@app.route('/semesters')
@student_required
def semesters():
    conn=get_db(); s=student(conn); sems,overall=summary(conn,s['id']); conn.close(); return render_template('semesters.html',student=s,semesters=sems,overall=overall)
@app.route('/semester/<int:semester_id>')
@student_required
def semester_detail(semester_id):
    conn=get_db(); s=student(conn); sem=conn.execute('SELECT * FROM semesters WHERE id=? AND student_id=?',(semester_id,s['id'])).fetchone()
    if not sem: conn.close(); return redirect(url_for('semesters'))
    sub=subjects(conn,semester_id); a=sum(x['attended'] for x in sub); t=sum(x['total'] for x in sub); conn.close(); return render_template('semester.html',student=s,semester=sem,subjects=sub,attendance=percent(a,t),attended=a,total=t)
@app.route('/calculator')
@student_required
def calculator():
    conn=get_db(); s=student(conn); _,overall=summary(conn,s['id']); conn.close(); return render_template('calculator.html',student=s,overall=overall)
@app.route('/analytics')
@student_required
def analytics():
    conn=get_db(); s=student(conn); sems,overall=summary(conn,s['id']); active=next(x for x in sems if x['is_active']); data=subjects(conn,active['id']); conn.close(); return render_template('analytics.html',student=s,semesters=sems,overall=overall,subjects=data)
@app.route('/history')
@student_required
def history():
    conn=get_db(); s=student(conn); rows=conn.execute("SELECT ar.*,su.name subject_name,se.label FROM attendance_records ar JOIN subjects su ON su.id=ar.subject_id JOIN semesters se ON se.id=su.semester_id WHERE se.student_id=? ORDER BY record_date DESC LIMIT 100",(s['id'],)).fetchall(); conn.close(); return render_template('history.html',student=s,records=rows)
@app.route('/api/calculate')
def api_calculate():
    a=max(0,request.args.get('attended',type=int) or 0); t=max(a,request.args.get('total',type=int) or 0); target=min(99.9,max(1,request.args.get('target',type=float) or 75)); return jsonify(percentage=percent(a,t),status=status(percent(a,t)),prediction=predict(a,t,target))

@app.route('/admin/login',methods=['GET','POST'])
def admin_login():
    if request.method=='POST':
        conn=get_db(); row=conn.execute('SELECT * FROM admins WHERE domain_id=? AND password=?',(request.form.get('domain_id','').strip(),request.form.get('password',''))).fetchone(); conn.close()
        if row: session.clear(); session['admin_id']=row['id']; return redirect(url_for('admin_dashboard'))
        flash('Invalid Domain ID or password.','error')
    return render_template('admin_login.html')
@app.route('/admin/logout')
def admin_logout(): session.clear(); return redirect(url_for('admin_login'))
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn=get_db(); roster=[]
    for s in conn.execute('SELECT * FROM students ORDER BY name'):
        _,o=summary(conn,s['id']); roster.append({**dict(s),'percentage':o['percentage'] if o['total'] else None,'status':status(o['percentage']) if o['total'] else 'none'})
    conn.close(); return render_template('admin_dashboard.html',roster=roster)
@app.route('/admin/students/new',methods=['GET','POST'])
@admin_required
def admin_new_student():
    if request.method=='POST':
        d=request.form
        if not d.get('student_id') or not d.get('password') or not d.get('name'): flash('Student ID, password and name are required.','error')
        else:
            try:
                new=create_student(d['student_id'].strip(),d['password'],d['name'].strip(),d.get('department',''),d.get('program',''),d.get('year',''),d.get('college',''),int(d.get('current_semester',1))); flash('Student login created. Add subjects next.','success'); return redirect(url_for('admin_subjects',student_id=new))
            except sqlite3.IntegrityError: flash('That Student ID already exists.','error')
    return render_template('admin_new_student.html')
@app.route('/admin/students/<int:student_id>/subjects',methods=['GET','POST'])
@admin_required
def admin_subjects(student_id):
    conn=get_db(); s=conn.execute('SELECT * FROM students WHERE id=?',(student_id,)).fetchone()
    if not s: conn.close(); return redirect(url_for('admin_dashboard'))
    if request.method=='POST':
        add_subject_to_semester(student_id,request.form.get('semester',type=int),request.form.get('name','').strip(),request.form.get('code','').strip(),request.form.get('faculty','').strip(),conn); flash('Subject added.','success'); return redirect(url_for('admin_subjects',student_id=student_id))
    sems,_=summary(conn,student_id); conn.close(); return render_template('admin_subjects.html',student=s,semesters=sems)
@app.route('/admin/students/<int:student_id>')
@admin_required
def admin_student(student_id):
    conn=get_db(); s=conn.execute('SELECT * FROM students WHERE id=?',(student_id,)).fetchone(); sems,overall=summary(conn,student_id); conn.close(); return render_template('admin_student.html',student=s,semesters=sems,overall=overall)

if __name__=='__main__': init_db(); app.run(debug=True)
