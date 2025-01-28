from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg2
from decouple import config

app = Flask(__name__)
app.secret_key = config('SECRET_KEY', default='36bbfeee4f53a83212bbf8a4984e96101983c4b61c39cc19b0d01fead6332272')

# Konfigurasi Database
def get_db():
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="Presensi_wajah",
            user="postgres",
            password="123"
        )
        return conn
    except psycopg2.Error as e:
        print(f"Error: {e}")
        return None

# Route Halaman Utama
@app.route('/')
def home():
    user_logged_in = 'username' in session
    if user_logged_in:
        return render_template('Homepage.html', username=session['username'], user_logged_in=user_logged_in)
    return redirect(url_for('loginPage'))

# Route Halaman Login
# @app.route('/login', methods=['GET', 'POST'])
def login():
    print(f"Request method: {request.method}")
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        print(f"Username: {username}, Password: {password}")

        db = get_db()
        if db:
            cursor = db.cursor()
            cursor.execute("SELECT * FROM pengguna WHERE username = %s AND password = %s", (username, password))
            user = cursor.fetchone()
            cursor.close()
            db.close()

            if user:
                session['username'] = user[1]
                flash('Login berhasil!', 'success')
                return redirect(url_for('home'))
            else:
                flash('Username atau password salah.', 'danger')
        else:
            flash('Koneksi database gagal.', 'danger')

    return render_template('login.html')

# Route Logout
@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))

# Jalankan Aplikasi
if __name__ == '__main__':
    app.run(debug=True)