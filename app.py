import os
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

# 1. นำเข้า Cloudinary SDK
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'checkin-super-secret-key-2026')
DATABASE = 'checkin.db'

# 2. ตั้งค่าการเชื่อมต่อ Cloudinary ผ่าน Environment Variables
cloudinary.config(
    cloud_name = os.environ.get('Root'),
    api_key = os.environ.get('411612461233476'),
    api_secret = os.environ.get('911GPlaZWRy-Hax0IVa9SLqHel0'),
    secure = True
)

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user'
            )
        ''')
        # ตาราง checkins: photo_url จะเก็บ Full HTTPS URL ของ Cloudinary
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS checkins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                photo_url TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        cursor.execute("SELECT * FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                           ('admin', generate_password_hash('admin123'), 'admin'))
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                           ('staff01', generate_password_hash('pass123'), 'user'))
        conn.commit()

init_db()

# --- Decorators สิทธิ์การใช้งานคงเดิม ---
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

# --- API Check-in อัปโหลดขึ้น Cloudinary ---
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

        # 3. อัปโหลดรูปขึ้น Cloudinary พร้อมเทคนิค Optimization
        # - จัดเก็บในโฟลเดอร์ 'checkin_photos'
        # - แปลงคุณภาพและฟอร์แมตอัตโนมัติ (auto-quality / auto-format) ช่วยประหยัดพื้นที่
        upload_result = cloudinary.uploader.upload(
            file,
            folder = "checkin_photos",
            public_id = f"{session['username']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            transformation = [
                {'width': 1200, 'crop': "limit"},  # ปรับขนาดไม่ให้เกิน 1200px
                {'quality': "auto"},               # บีบอัดคุณภาพรูปภาพอัตโนมัติ
                {'fetch_format': "auto"}           # แปลงเป็น WebP ให้อัตโนมัติถ้าเบราว์เซอร์รองรับ
            ]
        )
        
        # ดึง URL รูปภาพที่เป็น HTTPS
        image_url = upload_result.get('secure_url')
        
        # 4. บันทึกข้อมูลและ Cloudinary URL ลง Database
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO checkins (username, latitude, longitude, photo_url, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (session['username'], float(latitude), float(longitude), image_url, current_time))
            conn.commit()
            
        return jsonify({'success': True, 'message': 'เช็คอินและอัปโหลดรูปภาพถาวรสำเร็จ!'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f"เกิดข้อผิดพลาด: {str(e)}"}), 500

# Route อื่น ๆ (login, logout, index, admin) คงเดิม...
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            if user and check_password_hash(user['password'], password):
                session['username'] = user['username']
                session['role'] = user['role']
                return redirect(url_for('admin_dashboard') if user['role'] == 'admin' else url_for('index'))
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

@app.route('/admin')
@admin_required
def admin_dashboard():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM checkins ORDER BY id DESC")
        checkins = cursor.fetchall()
    return render_template('admin.html', checkins=checkins, username=session['username'])

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
