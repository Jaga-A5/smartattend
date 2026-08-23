"""Optional command-line helper to add a subject by student database id."""
from database import add_subject_to_semester, init_db
init_db()
print('Use the Domain Portal for the easiest subject setup.')
student_id=int(input('Student database ID: ')); semester=int(input('Semester (1-8): ')); name=input('Subject name: '); code=input('Code: ')
add_subject_to_semester(student_id,semester,name,code)
print('Subject added.')
