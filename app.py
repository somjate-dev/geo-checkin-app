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

# 2. เชื่อมต่อ Cloudinary (ดึงจาก Environment Variables ทั้งหมด ไม่มี Hardcoded เพื่อความปลอดภัย)
cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key = os.environ.get('CLOUDINARY_API_KEY'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET'),
    secure = True
)

# 3. เชื่อมต่อ Supabase (ดึงจาก Environment Variables ทั้งหมด ไม่มี Hardcoded เพื่อความปลอดภัย)
SUPABASE_URL = (os.environ.get('SUPABASE_URL') or '').strip()
SUPABASE_KEY = (os.environ.get('SUPABASE_KEY') or '').strip()

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

# ฟังก์ชันแปลงและวิเคราะห์วันเวลาแบบยืดหยุ่นสูง (Robust DateTime Parser)
def robust_parse_datetime(iso_str):
    if not iso_str:
        return None
    iso_str = str(iso_str).strip()
    if iso_str.endswith('Z'):
        iso_str = iso_str[:-1] + '+00:00'
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(THAILAND_TZ)
    except Exception:
        pass

    # วิธีสำรองในกรณีข้อมูลมาเป็น Format อื่นๆ
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(iso_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(THAILAND_TZ)
        except Exception:
            continue
    return None

# แปลง Format วันเวลาเป็นเวลาประเทศไทย (UTC+7) รูปแบบ "yyyy-MM-dd : HH:mm:ss"
def format_timestamp(iso_str):
    dt = robust_parse_datetime(iso_str)
    if dt:
        return dt.strftime("%Y-%m-%d : %H:%M:%S")
    return str(iso_str) if iso_str else ""

# ดึงเฉพาะวันที่เป็น Date object (เวลาไทย) เพื่อใช้ในการคัดกรองช่วงเวลา
def get_thailand_date(iso_str):
    dt = robust_parse_datetime(iso_str)
    if dt:
        return dt.date()
    return None

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
            
            # ตรวจสอบรหัสผ่านแบบตรง ๆ ไม่เข้ารหัส (Plaintext) ด้วยเครื่องหมาย ==
            if users and users[0]['password'] == password:
                session['username'] = users[0]['username']
                session['role'] = users[0].get('role', 'user') # ป้องกัน KeyError 'role'
                
                if session['role'] == 'admin':
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('index'))
            else:
                return render_template('login.html', error='ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง')
        except Exception as e:
            return render_template('login.html', error=f'เกิดข้อผิดพลาดในการเชื่อมต่อฐานข้อมูล: {str(e)}')
            
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

# 2. admin_dashboard (หน้า admin.html ค้นหาด้วย Checklist และ ช่วงระยะเวลา เริ่มต้น-สิ้นสุด)
@app.route('/admin')
@admin_required
def admin_dashboard():
    search_query = request.args.get('search', '').strip()
    sort_col = request.args.get('sort', 'id')
    sort_order = request.args.get('order', 'desc')
    page = int(request.args.get('page', 1))
    per_page = 10

    # คัดกรองรายชื่อแบบ Checklist
    selected_users = request.args.getlist('selected_users')

    # ดึงข้อมูลผู้ใช้ทั้งหมดเพื่อนำมาสร้าง checklist และ map ชื่อจริง-นามสกุล
    user_response = supabase.table('users').select('id, username, firstname, lastname').execute()
    users_list = user_response.data
    user_map = {}
    for u in users_list:
        fname = u.get('firstname') or ''
        lname = u.get('lastname') or ''
        fullname = f"{fname} {lname}".strip()
        user_map[u['username']] = fullname if fullname else u['username']

    # ดึงรายการเช็คอินทั้งหมด
    response = supabase.table('checkins').select('*').execute()
    checkins_data = response.data

    # หาช่วงเวลาที่ล่าสุดในระบบ เพื่อใช้คำนวณวันเริ่มต้นแบบไดนามิก (ย้อนหลัง 1 เดือนจากข้อมูลล่าสุด)
    all_dates = [get_thailand_date(c.get('created_at')) for c in checkins_data if c.get('created_at')]
    all_dates = [d for d in all_dates if d is not None]
    
    if all_dates:
        latest_date = max(all_dates)
    else:
        latest_date = datetime.now(THAILAND_TZ).date()

    # ค่าเริ่มต้นย้อนหลัง 1 เดือนจากวันที่ล่าสุดในฐานข้อมูล
    default_start_date_str = (latest_date - timedelta(days=30)).strftime('%Y-%m-%d')
    default_end_date_str = latest_date.strftime('%Y-%m-%d')

    start_date_str = request.args.get('start_date', default_start_date_str)
    end_date_str = request.args.get('end_date', default_end_date_str)

    # แปลงเปรียบเทียบเป็นวันที่ (Date Object) เพื่อความถูกต้องแม่นยำ 100%
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    except Exception:
        start_date = latest_date - timedelta(days=30)
        start_date_str = start_date.strftime('%Y-%m-%d')
        
    try:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except Exception:
        end_date = latest_date
        end_date_str = end_date.strftime('%Y-%m-%d')

    # ผสมและเสริมข้อมูลพนักงาน รวมถึงแปลงเวลาประเทศไทยให้สมบูรณ์
    for item in checkins_data:
        original_created_at = item.get('created_at')
        item['fullname'] = user_map.get(item['username'], item['username'])
        item['created_date_obj'] = get_thailand_date(original_created_at)
        
        thai_time_str = format_timestamp(original_created_at)
        item['formatted_time'] = thai_time_s
