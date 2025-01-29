import cv2
import threading
from flask import Flask, render_template, Response, jsonify
from deepface import DeepFace
import psycopg2
from datetime import datetime
from decouple import config
import numpy as np
import os

app = Flask(__name__)
app.secret_key=config('SECRET_KEY')

# Variabel global untuk verifikasi wajah
counter = 0
face_match = False
already_present = False
matched_image = None

lock = threading.Lock()
is_verifying = False

# Fungsi untuk koneksi ke PostgreSQL
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
        print(f"Error connecting to database: {e}")
        return None

# Fungsi untuk memuat gambar dari jalur lokal atau URL
def load_image(path_or_url, subfolder=None):
    if subfolder:
        img_path = os.path.join("assets", "images", subfolder, path_or_url)
    else:
        img_path = os.path.join("assets", "images", path_or_url)

    img = cv2.imread(img_path)
    
    if img is None:
        print(f"Failed to load image from path: {img_path}")
    return img

# Fungsi untuk mengambil referensi gambar dari database
def get_reference_images():
    conn = create_connection()
    if not conn:
        return []

    cursor = conn.cursor()
    cursor.execute("SELECT user_id, photo_front, photo_right, photo_left FROM pengguna")
    rows = cursor.fetchall()

    reference_imgs = []
    for row in rows:
        try:
            user_id = row[0]  # user_id
            photo_front = row[1]  # photo_front
            photo_right = row[2]  # photo_right
            photo_left = row[3]  # photo_left

            # Proses gambar-gambar (kanan, depan, kiri)
            for subfolder, img_path in {'depan': photo_front, 'kanan': photo_right, 'kiri': photo_left}.items():
                if img_path:
                    img = load_image(img_path, subfolder=subfolder)
                    if img is not None:
                        reference_imgs.append((user_id, img))
                    else:
                        print(f"Image for {user_id} ({subfolder}) could not be loaded.")
        except IndexError as e:
            print(f"Error accessing tuple elements: {e}")

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
            print(f"Error checking face presence in database: {e}")
    return False

# Fungsi untuk memeriksa kecocokan wajah
def check_face(frame):
    global face_match, matched_image, already_present, is_verifying
    reference_imgs = get_reference_images()
    try:
        for img_name, ref_img in reference_imgs:
            if ref_img is None:
                print(f"Skipping {img_name} due to invalid image.")
                continue

            result = DeepFace.verify(frame, ref_img.copy())['verified']
            if result:
                with lock:
                    # Cek apakah wajah sudah terdeteksi hari ini
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
                                today_date = datetime.now().date()
                                cursor.execute("INSERT INTO face_matches (user_id, tanggal) VALUES (%s, %s)",
                                               (matched_image, today_date))
                                conn.commit()
                                print(f"Data tersimpan untuk {matched_image} pada {today_date}")
                            except Exception as e:
                                print(f"Error inserting data into database: {e}")
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
        print(f"Error during face verification: {e}")
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
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    global face_match, already_present
    return jsonify({"detected": face_match, "already_present": already_present})

if __name__ == "__main__":
    app.run(debug=True)
