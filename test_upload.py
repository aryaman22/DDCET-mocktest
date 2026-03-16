import openpyxl
import io
import urllib.request
import urllib.parse
from http.cookiejar import CookieJar
import sys
import mimetypes
import uuid

# 1. Create a dummy Excel file
wb = openpyxl.Workbook()
ws = wb.active
ws.append(['qno', 'section', 'topic', 'question', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_ans', 'explanation'])
ws.append([1, 1, 'Math', 'What is 2+2?', '3', '4', '5', '6', 'B', '2+2=4'])
wb.save('test_questions.xlsx')
print("Created test_questions.xlsx")

# 2. Upload it
cj = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
urllib.request.install_opener(opener)
BASE_URL = 'http://127.0.0.1:5050'

def get_csrf(html):
    try:
        return html.split('name="csrf_token" value="')[1].split('"')[0]
    except IndexError:
        print("Could not find CSRF token in HTML!")
        sys.exit(1)

# Login as Admin
print("Logging in as Admin...")
resp = urllib.request.urlopen(f'{BASE_URL}/auth/login')
csrf_token_admin = get_csrf(resp.read().decode('utf-8'))
admin_data = urllib.parse.urlencode({'csrf_token': csrf_token_admin, 'email': 'admin@ddcet.local', 'password': 'Admin@1234'}).encode('utf-8')
urllib.request.urlopen(f'{BASE_URL}/auth/login', data=admin_data)

# Create a bank
print("Creating a Question Bank...")
resp = urllib.request.urlopen(f'{BASE_URL}/admin/banks/create')
csrf_bank = get_csrf(resp.read().decode('utf-8'))
bank_data = urllib.parse.urlencode({'csrf_token': csrf_bank, 'name': 'Test Excel Bank', 'description': 'Testing Excel Upload', 'is_active': 'on'}).encode('utf-8')
urllib.request.urlopen(f'{BASE_URL}/admin/banks/create', data=bank_data)

# Find the bank ID
resp = urllib.request.urlopen(f'{BASE_URL}/admin/banks')
html = resp.read().decode('utf-8')
bank_id = html.split('/admin/banks/')[1].split('/questions')[0]
print(f"Created bank with ID: {bank_id}")

# Upload Excel file
print("Uploading Excel file...")
resp = urllib.request.urlopen(f'{BASE_URL}/admin/banks/{bank_id}/upload')
csrf_upload = get_csrf(resp.read().decode('utf-8'))

# Multipart encoding
boundary = uuid.uuid4().hex
headers = {'Content-Type': f'multipart/form-data; boundary={boundary}'}
body = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="csrf_token"\r\n\r\n'
    f'{csrf_upload}\r\n'
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="test_questions.xlsx"\r\n'
    f'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n'
).encode('utf-8')

with open('test_questions.xlsx', 'rb') as f:
    body += f.read()

body += f'\r\n--{boundary}--\r\n'.encode('utf-8')

req = urllib.request.Request(f'{BASE_URL}/admin/banks/{bank_id}/upload', data=body, headers=headers)
resp = urllib.request.urlopen(req)

# Check if questions were added
resp = urllib.request.urlopen(f'{BASE_URL}/admin/banks/{bank_id}/questions')
html = resp.read().decode('utf-8')
if "What is 2+2?" in html:
    print("SUCCESS: Uploaded Excel questions found in the bank!")
else:
    print("ERROR: Uploaded questions not found.")
    sys.exit(1)
