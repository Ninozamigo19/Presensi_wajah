import cv2
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import threading
from flask import Flask, render_template, Response, jsonify, redirect, url_for, flash, request, make_response, copy_current_request_context
from deepface import DeepFace
import psycopg2
from datetime import datetime, timedelta
from decouple import config
import numpy as np
from Auth.login import current_user
import os
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = config('SECRET_KEY', default='supersecretkey')

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "signin"

counter = 0
face_match = False
already_present = False
matched_image = None

lock = threading.Lock()
is_verifying = False

# Fungsi koneksi ke PostgreSQL
def create_connection():
    try:
        connection = psycopg2.connect(
            host="localhost",
            database="Presensi_wajah",
            user="postgres",
            password="123"
        )
        return connection
    except Exception as e:
        print(f"⚠️ Error connecting to database: {e}")
        return None

# Model User
class User(UserMixin):
    def __init__(self, user_id, username, password):
        self.id = str(user_id)
        self.username = username
        self.password = password  

    @staticmethod
    def get(user_id):
        """Mengambil user berdasarkan ID"""
        conn = create_connection()
        if not conn:
            return None

        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, password FROM pengguna WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if row:
            return User(str(row[0]), row[1], row[2])
        return None

    @staticmethod
    def get_by_username(username):
        """Mengambil user berdasarkan username"""
        conn = create_connection()
        if not conn:
            return None

        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, password FROM pengguna WHERE username = %s", (username,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if row:
            return User(str(row[0]), row[1], row[2])
        return None

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# Route Login dengan Cookie
@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember_me = request.form.get('remember')

        user = User.get_by_username(username)
        if user and check_password_hash(user.password, password):  # Gunakan hashing
            login_user(user, remember=True)

            response = make_response(redirect(url_for('home')))
            if remember_me:
                response.set_cookie('user_id', user.id, max_age=timedelta(days=7))
            return response
        else:
            flash('Invalid Username or Password', 'danger')

    return render_template('login.html')

# Route Logout dengan Menghapus Cookie
@app.route('/logout')
@login_required
def logout():
    response = make_response(redirect(url_for('signin')))
    response.set_cookie('user_id', '', expires=0)
    logout_user()
    flash('You have been logged out.', 'info')
    return response

# Fungsi mengambil referensi gambar pengguna yang login
def get_reference_images():
    if current_user is None :
        return []
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, photo_front, photo_right, photo_left 
        FROM pengguna 
        WHERE user_id = %s
    """, (current_user.id,))

    rows = cursor.fetchall()
    reference_imgs = []

    for row in rows:
        user_id, photo_front, photo_right, photo_left = row

        for img_path in [photo_front, photo_right, photo_left]:
            print (photo_front)
            print (photo_right)
            print (photo_left)
            if img_path:
                img = cv2.imread(os.path.join("assets/images", img_path))
                if img is not None:
                    reference_imgs.append((user_id, img))

    cursor.close()
    conn.close()
    return reference_imgs

# Fungsi untuk mengecek apakah wajah sudah terdeteksi hari ini
def face_already_present_today(matched_image):
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            today_date = datetime.now().date()
            cursor.execute('''SELECT COUNT(*) FROM face_matches WHERE user_id = %s AND DATE(tanggal_dan_waktu) = %s''',
                           (matched_image, today_date))
            result = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return result > 0
        except Exception as e:
            print(f"⚠️ Error checking face presence in database: {e}")
    return False

# Perbaikan Threading untuk Face Recognition
def run_check_face(frame):
    with app.app_context():
        check_face(frame)

def check_face(frame):
    with app.app_context():
        global face_match, matched_image, already_present, is_verifying
        reference_imgs = get_reference_images()
        
        for img_name, ref_img in reference_imgs:
            if ref_img is None:
                continue

            result = DeepFace.verify(frame, ref_img.copy())
            if result['verified'] and img_name == current_user.id:
                with lock:
                    if face_already_present_today(img_name):
                        already_present = True
                        face_match = False
                    else:
                        face_match = True
                        matched_image = img_name
                        already_present = False

                        conn = create_connection()
                        if conn:
                            cursor = conn.cursor()
                            now = datetime.now()
                            status = "Present" if now.time() <= datetime.strptime("07:30:00", "%H:%M:%S").time() else "Late"
                            cursor.execute(
                                "INSERT INTO face_matches (user_id, tanggal_dan_waktu, status) VALUES (%s, %s, %s)",
                                (matched_image, now, status)
                            )
                            conn.commit()
                            cursor.close()
                            conn.close()
                break
        else:
            with lock:
                face_match = False
                matched_image = None
                already_present = False

# Fungsi menangkap frame kamera
def generate_frames():
    global counter, face_match, matched_image, already_present, is_verifying

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    while True:
        success, frame = cap.read()
        if not success:
            break
        else:
            frame = cv2.flip(frame, 1)

            if counter % 30 == 0 and not is_verifying:
                with lock:
                    is_verifying = True
                threading.Thread(target=run_check_face, args=(frame.copy(),)).start()

                 # Tampilkan hasil verifikasi
            with lock:
                if already_present:
                    cv2.putText(frame, "        SUDAH ABSEN!", (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                elif face_match:
                    cv2.putText(frame, "        COCOK", (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                else:
                    cv2.putText(frame, "        TIDAK COCOK!", (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            counter += 1
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    cap.release()

@app.route('/')
@login_required
def home():
    return render_template('Homepage.html', username=current_user.username)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    return jsonify({"detected": face_match, "already_present": already_present})

if __name__ == "__main__":
    app.run(debug=True)
