import cv2
import threading
from flask import Flask, render_template, Response, jsonify, Blueprint
from deepface import DeepFace
import psycopg2
from datetime import datetime
import uuid
from flask_wtf import FlaskForm

app = Flask(__name__)


# Variabel global untuk verifikasi wajah
counter = 0
face_match = False
already_present = False
matched_image = None
reference_imgs = [
    ("Naufal Nino Shalaah Ma'shuum", cv2.imread("assets/images/nino2.jpg")),
    ("pak anton", cv2.imread("assets/images/pak anton.png")),
    ("Amir", cv2.imread("assets/images/Amir.jpg")),
    ("Aep", cv2.imread("assets/images/aep.jpg"))
]

for img_name, ref_img in reference_imgs:
    if ref_img is None:
        print(f"Error: Could not load image {img_name}")

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

# Fungsi untuk memastikan tabel dan kolom sudah ada
def initialize_database():
    conn = create_connection()
    cursor = conn.cursor()

    # Membuat tabel face_matches jika belum ada
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS face_matches (
            id UUID PRIMARY KEY,
            nama VARCHAR(255) NOT NULL,
            tanggal_dan_waktu TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Menambahkan kolom 'tanggal' jika belum ada
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                           WHERE table_name='face_matches' AND column_name='tanggal') THEN
                ALTER TABLE face_matches ADD COLUMN tanggal DATE;
            END IF;
        END $$;
    ''')

    # Menambahkan constraint unik pada kolom nama dan tanggal jika belum ada
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'unique_name_date') THEN
                ALTER TABLE face_matches ADD CONSTRAINT unique_name_date UNIQUE (nama, tanggal);
            END IF;
        END $$;
    ''')

    conn.commit()
    cursor.close()
    conn.close()

# Fungsi untuk mendapatkan atau membuat UUID berdasarkan nama dan tanggal
def get_or_create_uuid(name):
    conn = create_connection()
    cursor = conn.cursor()

    # Pastikan tabel dan kolom sudah diinisialisasi
    initialize_database()

    # Cek UUID berdasarkan nama dan tanggal
    today_date = datetime.now().date()
    cursor.execute("SELECT id FROM face_matches WHERE nama = %s AND tanggal = %s", (name, today_date))
    result = cursor.fetchone()

    if result:
        existing_uuid = result[0]
        print(f"UUID yang sudah ada untuk {name} pada {today_date}: {existing_uuid}")
        return existing_uuid
    else:
        new_uuid = str(uuid.uuid4())
        try:
            cursor.execute("INSERT INTO face_matches (id, nama, tanggal) VALUES (%s, %s, %s)",
                           (new_uuid, name, today_date))
            conn.commit()
            print(f"UUID baru dibuat untuk {name}: {new_uuid}")
        except Exception as e:
            print(f"Error inserting data into database: {e}")
        finally:
            cursor.close()
            conn.close()

        return new_uuid


# Fungsi untuk mengecek apakah wajah sudah dideteksi hari ini
def face_already_present_today(matched_image):
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            today_date = datetime.now().date()
            cursor.execute('''
                SELECT COUNT(*) FROM face_matches WHERE nama = %s AND DATE(tanggal_dan_waktu) = %s
            ''', (matched_image, today_date))
            result = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return result > 0  # Jika ditemukan 1 atau lebih, wajah sudah pernah terdeteksi hari ini
        except Exception as e:
            print(f"Error checking face presence in database: {e}")
    return False

def check_face(frame):
    global face_match, matched_image, already_present, is_verifying
    try:
        
        for img_name, ref_img in reference_imgs:
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
                        # Simpan ke database dengan UUID dari fungsi get_or_create_uuid
                        unique_id = get_or_create_uuid(matched_image)
                        print(f"ID unik untuk {matched_image}: {unique_id}")
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
                    cv2.putText(frame, "        ALREADY PRESENT!", (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                elif face_match:
                    cv2.putText(frame, "        MATCH", (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                else:
                    cv2.putText(frame, "        NO MATCH!", (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

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
    return render_template('facerecog.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    global face_match, already_present
    return jsonify({"detected": face_match, "already_present": already_present})

if __name__ == "__main__":
    app.run(debug=True)
