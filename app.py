import os
import io
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import pandas as pd

# 1. นำเข้า Cloudinary และ Supabase SDK
import cloudinary
import cloudinary.uploader
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'checkin-super-secret-key-2026')

# 2. เชื่อมต่อ Cloudinary
cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME', 't6gzttll'),
    api_key = os.environ.get('CLOUDINARY_API_KEY', '411612461233476'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET', '911GPlaZWRy-Hax0IVa9SLqHel0'),
    secure = True
)

# 3. เชื่อมต่อ Supabase
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://xhakpthsysjkwdoptbmy.supabase.co').strip()
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhoYWtwdGhzeXNqa3dkb3B0Ym15Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MjQ3NjAyMCwiZXhwIjoyMTA4MDUyMDIwfQ.64qJFSqdUvo9bdafkwyDOnRlfHIUPwGRjzAkb_u0Hgo').strip()

# ตัดส่วนเกินของ URL อัตโนมัติ (หากเผลอก๊อปปี้เอา /rest/v1/ ติดมา)
if "/rest/v1" in SUPABASE_URL:
    SUPABASE_URL = SUPABASE_URL.split("/rest/v1")[0].strip()

# สร้าง Client เชื่อมต่อ Supabase
try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ SUCCESS: เชื่อมต่อ Supabase Client สำเร็จ!")
    else:
        raise ValueError("SUPABASE_URL หรือ SUPABASE_KEY มีค่าว่างเปล่า")
except Exception as e:
    print(f"❌ ERROR ในการเชื่อมต่อ Supabase: {str(e)}")
    supabase = None

# ⏰ กำหนด Timezone ประเทศไทย (UTC+7)
THAILAND_TZ = timezone(timedelta(hours=7))

# 💡 ฟังก์ชันแปลง Format วันเวลาเป็นเวลาประเทศไทย (UTC+7) รูปแบบ "yyyy-MM-dd : HH:mm:ss"
def format_timestamp(iso_str):
    if not iso_str:
        return ""
    try:
        clean_str = str(iso_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        # หากไม่มีข้อมูล timezone ฝังมา ให้ระบุเป็น UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # ปรับเวลาให้เป็นเวลาประเทศไทย (บวก 7 ชั่วโมงอัตโนมัติ)
        dt_th = dt.astimezone(THAILAND_TZ)
        return dt_th.strftime("%Y-%m-%d : %H:%M:%S")
    except Exception:
        return str(iso_str)

# Decorators สิทธิ์การใช้งาน
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session or session.get('role') != 'admin':
            return "คุณไม่มีสิทธิ์เข้าถึงหน้านี้", 403
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not supabase:
            return render_template('login.html', error='ระบบฐานข้อมูลยังไม่พร้อมใช้งาน (กรุณาตรวจสอบการเชื่อมต่อ)')
            
        try:
            # ค้นหาผู้ใช้งานจาก Supabase
            response = supabase.table('users').select('*').eq('username', username).execute()
            users = response.data
            
            # ตรวจสอบรหัสผ่านแบบตรง ๆ ไม่เข้ารหัส (Plaintext)
            if users and users[0]['password'] == password:
                session['username'] = users[0]['username']
                session['role'] = users[0].get('role', 'user') # ป้องกัน KeyError 'role'
                
                if session['role'] == 'admin':
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('index'))
            else:
                return render_template('login.html', error='ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง')
        except Exception as e:
            return render_template('
