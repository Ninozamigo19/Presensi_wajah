import uuid  # Tambahkan library uuid untuk membuat UUID
from flask import Flask, render_template, request, redirect, Blueprint
import os
import psycopg2

app = Flask(__name__)
app.config['UPLOAD_FOLDER_FRONT'] = 'assets/images/depan/'
app.config['UPLOAD_FOLDER_RIGHT'] = 'assets/images/kanan/'
app.config['UPLOAD_FOLDER_LEFT'] = 'assets/images/kiri/'

# Konfigurasi PostgreSQL
DB_CONFIG = {
    'host': 'localhost',
    'database': 'Presensi_wajah',
    'user': 'postgres',
    'password': '123'
}

def get_db_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    return conn


# @app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Ambil data dari form
        username = request.form['username']
        password = request.form['password']
        photofront = request.files['photo_depan']
        photoright = request.files['photo_kanan']
        photoleft = request.files['photo_kiri']

        # Validasi file yang diunggah (hanya PNG)
        ALLOWED_EXTENSIONS = {'jpg'}

        def allowed_file(*filenames):
            """Memeriksa apakah semua file memiliki ekstensi yang diizinkan."""
            for filename in filenames:
                if not ('.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS):
                    return False
            return True

        # Contoh penggunaan
        if not allowed_file(photofront.filename, photoright.filename, photoleft.filename):
            return "Hanya file JPG yang diperbolehkan!", 400

        # Simpan foto ke server
        front_path = os.path.join(app.config['UPLOAD_FOLDER_FRONT'], photofront.filename)
        right_path = os.path.join(app.config['UPLOAD_FOLDER_RIGHT'], photoright.filename)
        left_path = os.path.join(app.config['UPLOAD_FOLDER_LEFT'], photoleft.filename)
        photofront.save(front_path)
        photoright.save(right_path)
        photoleft.save(left_path)

        # Buat UUID sebagai ID unik
        user_id = str(uuid.uuid4())

        # Simpan data ke database
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO pengguna (user_id, username, password, photo_front, photo_right, photo_left) 
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (user_id, username, password, photofront.filename, photoright.filename, photoleft.filename)) #tambah foto samping kanan dan kiri
            conn.commit()
            cursor.close()
            conn.close()
        except psycopg2.IntegrityError:
            return "Kesalahan: Tidak dapat menyimpan data.", 400
        except Exception as e:
            return f"Terjadi kesalahan: {str(e)}", 500

        return redirect('/success')

    return render_template('register.html')

@app.route('/success')
def success():
    return "<h1>Registrasi berhasil!</h1>"

if __name__ == "__main__":
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)