import cv2
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import threading
from flask import Flask, render_template, Response, jsonify, redirect, url_for, flash
from deepface import DeepFace
import psycopg2
from datetime import datetime
from decouple import config
import numpy as np
import os
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = config('SECRET_KEY')

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
        self.id = user_id
        self.username = username
        self.password = password  # ⚠️ Jangan gunakan plaintext password di produksi

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
            return User(row[0], row[1], row[2])
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
            return User(row[0], row[1], row[2])
        return None

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)  # Memuat user berdasarkan ID

# Fungsi untuk memuat gambar
def load_image(path_or_url, subfolder=None):
    if subfolder:
        img_path = os.path.join("assets", "images", subfolder, path_or_url)
    else:
        img_path = os.path.join("assets", "images", path_or_url)

    img = cv2.imread(img_path)
    if img is None:
        print(f"❌ Gagal memuat gambar dari: {img_path}")
    return img

# Fungsi mengambil referensi gambar pengguna yang login
def get_reference_images():
    print(f"🟢 Debug: current_user = {current_user}")
    print(f"🟢 Debug: current_user.is_authenticated = {current_user.is_authenticated if current_user else 'None'}")

    if not current_user or not hasattr(current_user, "id") or not current_user.is_authenticated:
        print("⚠️ Error: current_user tidak tersedia atau belum login!")
        return []

    conn = create_connection()
    print(f"✅ Mengambil referensi gambar untuk user_id: {current_user.id}")

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
        print(f"📷 Gambar ditemukan untuk user_id {user_id}:")
        print(f"   - Depan: {photo_front}")
        print(f"   - Kanan: {photo_right}")
        print(f"   - Kiri: {photo_left}")

        for subfolder, img_path in {'depan': photo_front, 'kanan': photo_right, 'kiri': photo_left}.items():
            if img_path:
                img = load_image(img_path, subfolder=subfolder)
                if img is not None:
                    reference_imgs.append((user_id, img))
                else:
                    print(f"❌ Gagal membaca gambar {subfolder} untuk user_id {user_id}: {img_path}")

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

# Fungsi memeriksa kecocokan wajah dengan akun yang login
def check_face(frame):
    global face_match, matched_image, already_present, is_verifying
    reference_imgs = get_reference_images()
    
    try:
        for img_name, ref_img in reference_imgs:
            if ref_img is None:
                continue

            print(f"🔍 Memeriksa wajah dengan referensi user_id: {img_name}")

            result = DeepFace.verify(frame, ref_img.copy())
            print(f"🔍 DeepFace result: {result}")
            if result['verified'] and img_name == current_user.id:  # Pastikan wajah sesuai dengan pengguna yang login
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
                            try:
                                now = datetime.now()
                                status = "Present" if now.time() <= datetime.strptime("07:30:00", "%H:%M:%S").time() else "Late"
                                cursor.execute(
                                    "INSERT INTO face_matches (user_id, tanggal_dan_waktu, status) VALUES (%s, %s, %s)",
                                    (matched_image, now, status)
                                )
                                conn.commit()
                                print(f"✅ Absensi disimpan untuk user_id: {matched_image}, waktu: {now}, status: {status}")
                            except Exception as e:
                                print(f"⚠️ Error inserting data into database: {e}")
                            finally:
                                cursor.close()
                                conn.close()
                    break
        else:
            with lock:
                face_match = False
                matched_image = None
                already_present = False
    except ValueError as e:
        print(f"⚠️ Error during face verification: {e}")
        with lock:
            face_match = False
            matched_image = None
            already_present = False
    finally:
        with lock:
            is_verifying = False

# Fungsi untuk menangkap frame kamera
def generate_frames():
    global counter, face_match, matched_image, already_present, is_verifying

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
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
                threading.Thread(target=check_face, args=(frame.copy(),)).start()

            # Tampilkan hasil verifikasi
            with lock:
                if already_present:
                    cv2.putText(frame, "        SUDAH ABSEN!", (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                elif face_match:
                    cv2.putText(frame, "        COCOK", (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                else:
                    cv2.putText(frame, "        TIDAK COCOK!", (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            counter += 1

            # Encode frame jadi format byte untuk streaming
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()

            # Kirim frame sebagai respon byte stream
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    cap.release()

@app.route('/')
@login_required
def home():
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, username, password
                FROM pengguna
                WHERE user_id = %s
            """, (current_user.id,))
            attendance_records = cursor.fetchall()
            cursor.close()
            conn.close()
            print("✅ Fetched attendance records:", attendance_records)  # Debugging
        except Exception as e:
            print(f"⚠️ Error fetching attendance records: {e}")
            attendance_records = []

    return render_template('Homepage.html', attendance_records=attendance_records, username=current_user.username)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    global face_match, already_present
    return jsonify({"detected": face_match, "already_present": already_present})


if __name__ == "__main__":
    app.run(debug=True)
