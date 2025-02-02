import cv2
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import threading
from flask import Flask, render_template, Response, jsonify, redirect, url_for, flash, request, make_response, session
from deepface import DeepFace
import psycopg2
from datetime import datetime, timedelta
from decouple import config
import numpy as np
from Auth.login import current_user, login, get_db
import os
import secrets
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = config('SECRET_KEY', default='36bbfeee4f53a83212bbf8a4984e96101983c4b61c39cc19b0d01fead6332272')

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

# Model User
class User(UserMixin):
    def __init__(self, user_id, username, password):
        self.id = str(user_id)
        self.username = username
        self.password = password  

    @staticmethod
    def get(user_id):
        """Fetch user based on user_id"""
        conn = get_db()  # Use get_db() instead of psycopg2.connect()
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
        """Fetch user based on username"""
        conn = get_db()  # Use get_db() instead of psycopg2.connect()
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
@app.route('/', methods=['GET', 'POST'])
def signin():
    return login()  # Simply call the login function from login.py

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
def get_reference_images(user_id):
    """Fetches the front image filename from the database for face matching."""
    conn = get_db()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        # Assume the column storing the front image filename is named 'depan'
        cursor.execute("SELECT photo_front FROM pengguna WHERE user_id = %s", (user_id,))
        reference_imgs = cursor.fetchall()  # Each row is a one-element tuple
        return reference_imgs
    finally:
        cursor.close()
        conn.close()

# Fungsi untuk mengecek apakah wajah sudah terdeteksi hari ini
def face_already_present_today(user_id):
    """Checks if the user has already been marked present today."""
    conn = get_db()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        today = datetime.now().date()
        cursor.execute(
            "SELECT COUNT(*) FROM face_matches WHERE user_id = %s AND DATE(tanggal_dan_waktu) = %s",
            (user_id, today)
        )
        count = cursor.fetchone()[0]
        return count > 0
    finally:
        cursor.close()
        conn.close()
        
def get_user_id_from_token():
    return current_user.id if current_user.is_authenticated else None

# Perbaikan Threading untuk Face Recognition
def run_check_face(frame, user_id):
    """Starts face verification, passing user_id explicitly."""
    threading.Thread(target=check_face, args=(frame, user_id), daemon=True).start()

# Function to check if a face matches and update the state
def check_face(frame, user_id, max_attempts=3):
    """Compares captured face with stored images and records attendance, retrying if no match is found."""
    global face_match, matched_image, already_present, is_verifying

    if not user_id:
        print("⚠️ No user_id provided!")
        return

    reference_imgs = get_reference_images(user_id)
    print(f"✅ Found {len(reference_imgs)} reference images for user {user_id}")

    attempts = 0
    while attempts < max_attempts:
        for (ref_img,) in reference_imgs:
            if not ref_img:
                print("❌ Reference image is None, skipping")
                continue

            try:
                # Load image from assets folder
                ref_img_path = os.path.join("assets/images/depan", ref_img)  
                print(f"🔍 Attempt {attempts+1}: Verifying face with image: {ref_img_path}")

                result = DeepFace.verify(frame, ref_img_path, enforce_detection=False)
                print(f"✅ DeepFace result: {result}")

                if result['verified']:
                    with lock:
                        if face_already_present_today(user_id):
                            already_present = True
                            face_match = False
                        else:
                            face_match = True
                            matched_image = user_id
                            already_present = False

                            # Record the face match in the database
                            conn = get_db()
                            if conn:
                                try:
                                    cursor = conn.cursor()
                                    now = datetime.now()
                                    status = "Present" if now.time() <= datetime.strptime("07:30:00", "%H:%M:%S").time() else "Late"
                                    cursor.execute(
                                        "INSERT INTO face_matches (user_id, tanggal_dan_waktu, status) VALUES (%s, %s, %s)",
                                        (matched_image, now, status)
                                    )
                                    conn.commit()
                                    print("✅ Attendance recorded in database.")
                                except Exception as e:
                                    print(f"⚠️ Database error: {e}")
                                finally:
                                    cursor.close()
                                    conn.close()
                    return  # Stop scanning once a match is found
            except Exception as e:
                print(f"⚠️ DeepFace verification failed: {e}")

        attempts += 1
        print(f"🔄 Retrying... ({attempts}/{max_attempts})")

    print("❌ No match found after multiple attempts.")
    with lock:
        face_match = False
        matched_image = None
        already_present = False
            
# Fungsi menangkap frame kamera
# Function to capture frames from the camera and process them
def generate_frames(user_id):
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

            # Limit frame processing to once every 30 frames
            if counter % 30 == 0 and not is_verifying:
                with lock:
                    is_verifying = True
                threading.Thread(target=run_check_face, args=(frame.copy(), user_id), daemon=True).start()

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
    # Ensure the user is logged in; current_user is available here
    if not current_user.is_authenticated:
        return jsonify({"error": "Not authenticated"}), 401

    user_id = current_user.id  # Get the user_id from the main request context
    print(f"User ID from main context: {user_id}")

    return Response(generate_frames(user_id), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    return jsonify({"detected": face_match, "already_present": already_present})

if __name__ == "__main__":
    app.run(debug=True)
