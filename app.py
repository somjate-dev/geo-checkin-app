import os
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

# 1. นำเข้า Cloudinary และ Supabase SDK
import cloudinary
import cloudinary.uploader
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'checkin-super-secret-key-2026')

# 2. เชื่อมต่อ Cloudinary
cloudinary.config(
    # cloud_name = os.environ.get('Root'),
    # api_key = os.environ.get('411612461233476'),
    # api_secret = os.environ.get('911GPlaZWRy-Hax0IVa9SLqHel0'),
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME', 'Root'),
    api_key = os.environ.get('CLOUDINARY_API_KEY', '411612461233476'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET', '911GPlaZWRy-Hax0IVa9SLqHel0'),

    secure = True

)
# 3. เชื่อมต่อ Supabase
# # ดึงค่าจาก Env Var บน Render ถ้าไม่มีให้ใช้ค่าสำรอง (Default Value) ที่กำหนดไว้ข้างหลัง
# SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://xhakpthsysjkwdoptbmy.supabase.c').strip()
# SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhoYWtwdGhzeXNqa3dkb3B0Ym15Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MjQ3NjAyMCwiZXhwIjoyMTA4MDUyMDIwfQ.64qJFSqdUvo9bdafkwyDOnRlfHIUPwGRjzAkb_u0Hgo').strip()
# supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 3. เชื่อมต่อ Supabase
SUPABASE_URL = os.environ.get('https://xhakpthsysjkwdoptbmy.supabase.co')
SUPABASE_KEY = os.environ.get('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhoYWtwdGhzeXNqa3dkb3B0Ym15Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MjQ3NjAyMCwiZXhwIjoyMTA4MDUyMDIwfQ.64qJFSqdUvo9bdafkwyDOnRlfHIUPwGRjzAkb_u0Hgo')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# # ตัดส่วนเกินของ URL อัตโนมัติ (หากเผลอก๊อปปี้เอา /rest/v1/ ติดมา)
# if "/rest/v1" in SUPABASE_URL:
#     SUPABASE_URL = SUPABASE_URL.split("/rest/v1")[0].strip()

# # สร้าง Client
# try:
#     if SUPABASE_URL and SUPABASE_KEY:
#         supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
#         print("✅ SUCCESS: เชื่อมต่อ Supabase Client สำเร็จ!")
#     else:
#         raise ValueError("SUPABASE_URL หรือ SUPABASE_KEY มีค่าว่างเปล่า")
# except Exception as e:
#     print(f"❌ ERROR ในการเชื่อมต่อ Supabase: {str(e)}")
#     supabase = None
    
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

        # ค้นหาผู้ใช้งานจาก Supabase
        response = supabase.table('users').select('*').eq('username', username).execute()
        users = response.data

        if users and check_password_hash(users[0]['password'], password):
            session['username'] = users[0]['username']
            session['role'] = users[0]['role']
            if users[0]['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', username=session['username'])

@app.route('/api/checkin', methods=['POST'])
@login_required
def api_checkin():
    try:
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        file = request.files.get('photo')

        if not latitude or not longitude:
            return jsonify({'success': False, 'message': 'ไม่พบพิกัดตำแหน่ง GPS'}), 400
        if not file or file.filename == '':
            return jsonify({'success': False, 'message': 'กรุณาถ่ายรูปภาพก่อนเช็คอิน'}), 400

        # อัปโหลดรูปขึ้น Cloudinary
        upload_result = cloudinary.uploader.upload(
            file,
            folder="checkin_photos",
            transformation=[
                {'width': 1200, 'crop': "limit"},
                {'quality': "auto"},
                {'fetch_format': "auto"}
            ]
        )
        image_url = upload_result.get('secure_url')

        # บันทึกข้อมูลลง Supabase PostgreSQL
        new_record = {
            'username': session['username'],
            'latitude': float(latitude),
            'longitude': float(longitude),
            'photo_url': image_url
        }
        supabase.table('checkins').insert(new_record).execute()

        return jsonify({'success': True, 'message': 'เช็คอินและบันทึกข้อมูลถาวรสำเร็จ!'})

    except Exception as e:
        return jsonify({'success': False, 'message': f"เกิดข้อผิดพลาด: {str(e)}"}), 500

@app.route('/admin')
@admin_required
def admin_dashboard():
    # ดึงรายการเช็คอินทั้งหมด เรียงจากล่าสุดไปเก่าสุด
    response = supabase.table('checkins').select('*').order('id', desc=True).execute()
    checkins = response.data
    return render_template('admin.html', checkins=checkins, username=session['username'])

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

