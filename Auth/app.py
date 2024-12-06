import cv2
import threading
from flask import Flask, render_template, Response, jsonify
from deepface import DeepFace
import psycopg2
from datetime import datetime

app = Flask(__name__)

# Variabel global untuk verifikasi wajah
counter = 0
face_match = False
already_present = False
matched_image = None
reference_imgs = []

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


# Fungsi untuk memuat referensi gambar dari database
def fetch_reference_images():
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Query untuk mendapatkan nama pengguna dan nama file gambar
            cursor.execute("SELECT username, photo FROM pengguna")
            user_data = cursor.fetchall()

            reference_images = []
            for name, photo in user_data:
                if photo:
                    image_path = f"assets/images/{photo}"  # Path file gambar
                    img = cv2.imread(image_path)
                    if img is not None:
                        reference_images.append((name, img))
                    else:
                        print(f"Error: Unable to load image {image_path}")
            return reference_images
        except Exception as e:
            print(f"Error fetching reference images: {e}")
        finally:
            conn.close()
    return []

    #         images = []
    #         for name, photo_path in rows:
    #             image = cv2.imread(photo_path)
    #             if image is not None:
    #                 images.append((name, image))
    #             else:
    #                 print(f"Error: Could not load image for {name} from {photo_path}")
    #         return images
    #     except Exception as e:
    #         print(f"Error fetching reference images: {e}")
    #         return []
    # return []


# Fungsi untuk mendapatkan ID pengguna berdasarkan nama
def get_user_id_by_name(name):
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM pengguna WHERE username = %s", (name,))
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            if result:
                return result[0]  # ID pengguna
            else:
                print(f"User with name '{name}' not found in database.")
        except Exception as e:
            print(f"Error fetching user ID: {e}")
    return None


# Fungsi untuk memeriksa apakah wajah sudah presensi hari ini
def face_already_present_today(user_id):
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            today_date = datetime.now().date()
            cursor.execute("SELECT COUNT(*) FROM face_matches WHERE id = %s AND tanggal = %s", (user_id, today_date))
            result = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return result > 0  # Jika ditemukan, berarti sudah presensi
        except Exception as e:
            print(f"Error checking face presence in database: {e}")
    return False


# Fungsi untuk memverifikasi wajah
def check_face(frame):
    global face_match, matched_image, already_present, is_verifying
    try:
        for img_name, ref_img in reference_imgs:
            result = DeepFace.verify(frame, ref_img.copy())['verified']
            if result:
                with lock:
                    # Ambil ID pengguna berdasarkan nama
                    user_id = get_user_id_by_name(img_name)
                    if not user_id:
                        print(f"User ID not found for {img_name}. Skipping record.")
                        continue

                    # Periksa apakah sudah presensi hari ini
                    if face_already_present_today(user_id):
                        already_present = True
                        face_match = False
                    else:
                        face_match = True
                        matched_image = img_name
                        already_present = False
                        # Simpan presensi ke database
                        save_face_match(user_id, img_name)
                    break
        else:
            with lock:
                face_match = False
                matched_image = None
                already_present = False
    except Exception as e:
        print(f"Error during face verification: {e}")
        with lock:
            face_match = False
            matched_image = None
            already_present = False
    finally:
        with lock:
            is_verifying = False


# Fungsi untuk menyimpan data presensi ke database
def save_face_match(user_id, name):
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            today_date = datetime.now().date()
            cursor.execute("INSERT INTO face_matches (id, nama, tanggal) VALUES (%s, %s, %s)", (user_id, name, today_date))
            conn.commit()
            cursor.close()
            conn.close()
            print(f"Presence saved for {name} with ID {user_id}.")
        except Exception as e:
            print(f"Error saving face match: {e}")


# Fungsi untuk menghasilkan frame dari webcam
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
                    cv2.putText(frame, "ALREADY PRESENT!", (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                elif face_match:
                    cv2.putText(frame, f"MATCH: {matched_image}", (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                else:
                    cv2.putText(frame, "NO MATCH!", (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            counter += 1

            # Encode frame menjadi format byte untuk streaming
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    cap.release()
# Memuat referensi gambar dari database
    reference_imgs = fetch_reference_images()

# Route untuk halaman utama
@app.route('/')
def index():
    return render_template('facerecog.html')


# Route untuk video streaming
@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


# Route untuk status deteksi
@app.route('/status')
def status():
    global face_match, already_present
    return jsonify({"detected": face_match, "already_present": already_present})


if __name__ == "__main__":
    app.run(debug=True)
