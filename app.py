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
    user_response = supabase.table('users').select('id, username, firstname, lastname, role').execute()
    users_for_checklist = [u for u in user_response.data if u.get('role') != 'admin']
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
        item['formatted_time'] = thai_time_str
        item['created_at'] = thai_time_str  # รองรับทุกตัวแปรในเทมเพลต

    # ทำการกรอง (Filter) ข้อมูล
    filtered_checkins = []
    for item in checkins_data:
        # 1. กรองตามช่วงวันที่ ( start_date <= วันที่เช็คอิน <= end_date )
        if item['created_date_obj']:
            if not (start_date <= item['created_date_obj'] <= end_date):
                continue

        # 2. กรองตามรายชื่อพนักงานแบบ Checklist
        if selected_users:
            if item['username'] not in selected_users:
                continue

        # 3. กรองตามข้อความค้นหา (Search Query)
        if search_query:
            sq_lower = search_query.lower()
            if not (sq_lower in item['username'].lower() or 
                    sq_lower in item['fullname'].lower() or
                    sq_lower in str(item['latitude']) or
                    sq_lower in str(item['longitude']) or
                    sq_lower in item['formatted_time'].lower()):
                continue

        filtered_checkins.append(item)

    checkins_data = filtered_checkins

    # จัดเรียงข้อมูล (Sort)
    reverse_order = (sort_order == 'desc')
    if sort_col in ['id', 'username', 'created_at']:
        checkins_data.sort(key=lambda x: x.get(sort_col, ''), reverse=reverse_order)

    # แบ่งหน้า (Pagination 10 รายการ)
    total_records = len(checkins_data)
    total_pages = (total_records + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_checkins = checkins_data[start_idx:end_idx]

    return render_template(
        'admin.html', 
        checkins=paginated_checkins, 
        username=session['username'],
        users_list=users_for_checklist,  # ⬅️ ส่งเฉพาะ user ที่ไม่ใช่ admin
        # users_list=users_list,
        selected_users=selected_users,
        start_date=start_date_str,
        end_date=end_date_str,
        search_query=search_query,
        sort_col=sort_col,
        sort_order=sort_order,
        page=page,
        total_pages=total_pages
    )

# 1. admin_manage หน้าจัดการผู้ใช้งาน
@app.route('/admin/manage')
@admin_required
def admin_manage():
    search_query = request.args.get('search', '').strip()
    sort_col = request.args.get('sort', 'id')
    sort_order = request.args.get('order', 'asc')
    page = int(request.args.get('page', 1))
    per_page = 10

    # ดึงรายการผู้ใช้งานทั้งหมด
    response = supabase.table('users').select('*').execute()
    users_data = response.data

    # ค้นหาผู้ใช้งาน (Search)
    if search_query:
        sq_lower = search_query.lower()
        filtered_users = []
        for u in users_data:
            fname = (u.get('firstname') or '').lower()
            lname = (u.get('lastname') or '').lower()
            uname = u['username'].lower()
            if sq_lower in uname or sq_lower in fname or sq_lower in lname:
                filtered_users.append(u)
        users_data = filtered_users

    # จัดเรียง (Sort)
    reverse_order = (sort_order == 'desc')
    if sort_col in ['id', 'username', 'role']:
        users_data.sort(key=lambda x: x.get(sort_col, ''), reverse=reverse_order)

    # แบ่งหน้า (Pagination)
    total_records = len(users_data)
    total_pages = (total_records + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_users = users_data[start_idx:end_idx]

    return render_template(
        'admin_manage.html',
        users=paginated_users,
        username=session['username'],
        search_query=search_query,
        sort_col=sort_col,
        sort_order=sort_order,
        page=page,
        total_pages=total_pages
    )

# เพิ่มผู้ใช้งาน
@app.route('/admin/manage/add', methods=['POST'])
@admin_required
def admin_add_user():
    username = request.form.get('username', '').strip()
    firstname = request.form.get('firstname', '').strip()
    lastname = request.form.get('lastname', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'user')

    if not username or not password:
        return "กรุณากรอกข้อมูล Username และ Password", 400

    new_user = {
        'username': username,
        'firstname': firstname,
        'lastname': lastname,
        'password': password,
        'role': role
    }

    try:
        supabase.table('users').insert(new_user).execute()
        return redirect(url_for('admin_manage'))
    except Exception as e:
        return f"เกิดข้อผิดพลาดในการเพิ่มผู้ใช้งาน: {str(e)}", 500

# แก้ไขผู้ใช้งาน
@app.route('/admin/manage/edit/<int:user_id>', methods=['POST'])
@admin_required
def admin_edit_user(user_id):
    firstname = request.form.get('firstname', '').strip()
    lastname = request.form.get('lastname', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'user')

    updated_data = {
        'firstname': firstname,
        'lastname': lastname,
        'password': password,
        'role': role
    }

    try:
        supabase.table('users').update(updated_data).eq('id', user_id).execute()
        return redirect(url_for('admin_manage'))
    except Exception as e:
        return f"เกิดข้อผิดพลาดในการแก้ไขข้อมูล: {str(e)}", 500

# ลบผู้ใช้งาน
@app.route('/admin/manage/delete/<int:user_id>')
@admin_required
def admin_delete_user(user_id):
    try:
        supabase.table('users').delete().eq('id', user_id).execute()
        return redirect(url_for('admin_manage'))
    except Exception as e:
        return f"เกิดข้อผิดพลาดในการลบผู้ใช้งาน: {str(e)}", 500

# ดาวน์โหลดข้อมูลเช็คอินเป็น Excel (รองรับการกรองตามเงื่อนไขเดียวกับแดชบอร์ด)
@app.route('/admin/export')
@admin_required
def admin_export_excel():
    try:
        search_query = request.args.get('search', '').strip()
        selected_users = request.args.getlist('selected_users')
        start_date_str = request.args.get('start_date', '')
        end_date_str = request.args.get('end_date', '')

        # ดึงข้อมูลมาสร้าง map ชื่อจริง-นามสกุล
        user_response = supabase.table('users').select('username, firstname, lastname').execute()
        user_map = {}
        for u in user_response.data:
            fname = u.get('firstname') or ''
            lname = u.get('lastname') or ''
            fullname = f"{fname} {lname}".strip()
            user_map[u['username']] = fullname if fullname else u['username']

        # ดึงประวัติเช็คอิน
        response = supabase.table('checkins').select('*').execute()
        checkins_data = response.data

        # วิเคราะห์คัดกรองช่วงเวลา
        start_date = None
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except Exception:
                pass
        end_date = None
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except Exception:
                pass

        filtered_checkins = []
        for item in checkins_data:
            original_created_at = item.get('created_at')
            item['Fullname'] = user_map.get(item['username'], item['username'])
            item['formatted_time'] = format_timestamp(original_created_at)
            item['created_date_obj'] = get_thailand_date(original_created_at)

            # กรองช่วงเวลา
            if item['created_date_obj']:
                if start_date and item['created_date_obj'] < start_date:
                    continue
                if end_date and item['created_date_obj'] > end_date:
                    continue

            # กรองตามผู้ใช้แบบ Checklist
            if selected_users:
                if item['username'] not in selected_users:
                    continue

            # กรองตามคำค้นหา
            if search_query:
                sq_lower = search_query.lower()
                if not (sq_lower in item['username'].lower() or 
                        sq_lower in item['Fullname'].lower() or
                        sq_lower in str(item['latitude']) or
                        sq_lower in str(item['longitude']) or
                        sq_lower in item['formatted_time'].lower()):
                    continue

            filtered_checkins.append(item)

        checkins_data = filtered_checkins

        # จัดประวัติเวลาไทยลง Excel
        for item in checkins_data:
            item['created_at'] = item['formatted_time']

        # แปลงเป็น DataFrame และปรับแต่งหัวข้อ
        df = pd.DataFrame(checkins_data)
        
        # จัดการเลือกเฉพาะคอลัมน์ที่ต้องการเพื่อความสวยงาม
        export_columns = {
            'id': 'ลำดับ',
            'username': 'ชื่อผู้ใช้งาน (Username)',
            'Fullname': 'ชื่อ - นามสกุล',
            'latitude': 'ละติจูด (Latitude)',
            'longitude': 'ลองจิจูด (Longitude)',
            'photo_url': 'ลิงก์รูปถ่าย (Photo Link)',
            'created_at': 'วัน/เวลา (Date/Time)'
        }
        
        # คัดกรองและเรียงสลับคอลัมน์ใหม่ตามโครงสร้างที่ต้องการ
        df = df.rename(columns=export_columns)
        df_final = df[[val for val in export_columns.values() if val in df.columns]]

        # บันทึกเป็นไบนารี Excel stream
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_final.to_excel(writer, index=False, sheet_name='Checkin_Reports')
        output.seek(0)

        filename = f"Checkin_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            output, 
            as_attachment=True, 
            download_name=filename, 
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        return f"เกิดข้อผิดพลาดในการดาวน์โหลด Excel: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
