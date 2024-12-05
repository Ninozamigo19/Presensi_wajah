import uuid  # Tambahkan library uuid untuk membuat UUID
from flask import Flask, render_template, request, redirect, Blueprint
import os
import psycopg2

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'assets/images/'

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
        photo = request.files['photo']

        # Validasi file yang diunggah (hanya JPG)
        ALLOWED_EXTENSIONS = {'jpg'}
        def allowed_file(filename):
            return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
        
        if not allowed_file(photo.filename):
            return "Hanya file JPG yang diperbolehkan!", 400

        # Simpan foto ke server
        photo_path = os.path.join(app.config['UPLOAD_FOLDER'], photo.filename)
        photo.save(photo_path)

        # Buat UUID sebagai ID unik
        user_id = str(uuid.uuid4())

        # Simpan data ke database
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (id, username, password, photo) 
                VALUES (%s, %s, %s, %s)
            ''', (user_id, username, password, photo.filename))
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
