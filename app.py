import os
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'checkin-super-secret-key-2026')

UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
DATABASE = 'checkin.db'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ฟังก์ชันจัดการ Database
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        # ตารางผู้ใช้งาน
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user'
            )
        ''')
        # ตารางบันทึกการเช็คอิน
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS checkins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                photo_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        # สร้างบัญชีตั้งต้น (Admin: admin / admin123, User: staff01 / pass123)
        cursor.execute("SELECT * FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                           ('admin', generate_password_hash('admin123'), 'admin'))
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                           ('staff01', generate_password_hash('pass123'), 'user'))
        conn.commit()

init_db()

# Decorators ตรวจสอบสิทธิ์การเข้าใช้งาน
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

# Routes
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
                if user['role'] == 'admin':
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
            
        # บันทึกไฟล์รูปภาพ
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        new_filename = f"{session['username']}_{timestamp_str}.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(new_filename))
        file.save(filepath)
        
        # บันทึกลง Database
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO checkins (username, latitude, longitude, photo_path, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (session['username'], float(latitude), float(longitude), new_filename, current_time))
            conn.commit()
            
        return jsonify({'success': True, 'message': 'เช็คอินสำเร็จเรียบร้อยแล้ว!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

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
