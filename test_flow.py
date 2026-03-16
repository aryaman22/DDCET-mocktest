import urllib.request
import urllib.parse
from http.cookiejar import CookieJar
import sys

# Setup opener with cookie jar to maintain session
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

# 1. Get Register Page
print("1. Getting Register Page...")
try:
    resp = urllib.request.urlopen(f'{BASE_URL}/auth/register')
    html = resp.read().decode('utf-8')
    csrf_token = get_csrf(html)
    print(f"CSRF Token: {csrf_token}")
except Exception as e:
    print(f"Failed to load register page: {e}")
    sys.exit(1)

# 2. Register User
print("\n2. Registering new user...")
data = urllib.parse.urlencode({
    'csrf_token': csrf_token,
    'name': 'Test User',
    'enrollment_number': 'TEST999',
    'engineering_branch': 'Computer Engineering',
    'email': 'test999@ddcet.local',
    'password': 'Password123!',
    'confirm_password': 'Password123!'
}).encode('utf-8')

try:
    resp = urllib.request.urlopen(f'{BASE_URL}/auth/register', data=data)
    html = resp.read().decode('utf-8')
    # Successful login redirects to login, so we might get the login page back
    if "Registration successful" in html or "Sign in" in html:
        print("Registration flow seemed to work (redirected to login).")
    else:
        print("Warning: Registration success message not found.")
except Exception as e:
    print(f"Registration request failed: {e}")

# 3. Login as Admin
print("\n3. Logging in as Admin...")
try:
    resp = urllib.request.urlopen(f'{BASE_URL}/auth/login')
    html = resp.read().decode('utf-8')
    csrf_token_admin = get_csrf(html)
    
    admin_data = urllib.parse.urlencode({
        'csrf_token': csrf_token_admin,
        'email': 'admin@ddcet.local',
        'password': 'Admin@1234'
    }).encode('utf-8')
    
    resp = urllib.request.urlopen(f'{BASE_URL}/auth/login', data=admin_data)
    html = resp.read().decode('utf-8')
    
    if 'Dashboard' in html or 'Admin' in html:
        print("Admin login successful!")
    else:
        print("Admin login failed.")
        sys.exit(1)
except Exception as e:
    print(f"Admin login request failed: {e}")
    sys.exit(1)

# 4. Check Users Page
print("\n4. Checking Users Page...")
try:
    resp = urllib.request.urlopen(f'{BASE_URL}/admin/users')
    html = resp.read().decode('utf-8')
    
    if 'TEST999' in html and 'Computer Engineering' in html:
        print("SUCCESS: TEST999 and Computer Engineering found in admin users list!")
    else:
        print("ERROR: New user not found in admin users list.")
        sys.exit(1)
except Exception as e:
    print(f"Users page request failed: {e}")
    sys.exit(1)

print("\nAll integration tests passed successfully.")
