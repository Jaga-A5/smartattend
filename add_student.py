"""Optional command-line helper to create a student."""
from database import create_student, init_db
init_db()
sid=input('Student ID: '); name=input('Name: '); password=input('Password: ')
create_student(sid,password,name)
print('Student created. Use the Domain Portal to add subjects.')
