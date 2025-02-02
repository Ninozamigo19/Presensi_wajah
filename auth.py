from flask import Flask, render_template, request, redirect, url_for, flash, session, Response, jsonify
from decouple import config
from flask_login import LoginManager, logout_user, login_required, current_user
import uuid

from Auth.app import generate_frames, face_match, already_present, create_connection, app
from Auth.register import register
from Auth.login import login , get_db, User

app = Flask(__name__)
app.secret_key=config('SECRET_KEY', default='36bbfeee4f53a83212bbf8a4984e96101983c4b61c39cc19b0d01fead6332272')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.session_protection = "strong"  # Ensures session security
login_manager.login_view = 'signin'


@app.context_processor
def inject_user():
    print(f"🔑 current_user: {current_user}")  # Debugging
    return dict(current_user=current_user)

@app.route('/', methods=['GET', 'POST'])
def signin():
    return login()

@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('signin'))


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login memuat user berdasarkan ID"""
    try:
        user_id = uuid.UUID(user_id)  # Konversi ke UUID sebelum query
    except ValueError:
        return None

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT user_id, username FROM pengguna WHERE user_id = %s", (str(user_id),))  # Cast ke string
    user = cursor.fetchone()
    cursor.close()
    db.close()

    if user:
        print(f"✅ User loaded: ID={user[0]}, Username={user[1]}")
        return User(str(user[0]), user[1])
    else:
        print("⚠️ User not found in database!")
        return None

@app.context_processor
def inject_user():
    return dict(current_user=current_user)

@app.route('/Home')
@login_required
def home():
    if not current_user.is_authenticated:
        flash("You must be logged in to access this page.", "danger")
        return redirect(url_for('signin'))
    
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tanggal_dan_waktu, user_id
                FROM face_matches
                WHERE user_id = %s
                ORDER BY tanggal_dan_waktu DESC
            """, (current_user.id,))
            attendance_records = cursor.fetchall()
            cursor.close()
            conn.close()
            print("✅ Fetched attendance records:", attendance_records)
        except Exception as e:
            print(f"⚠️ Error fetching attendance records: {e}")
            attendance_records = []

    return render_template('Homepage.html', attendance_records=attendance_records, username=current_user.username)

@app.route('/Presensi')
@login_required
def presensi():
    return render_template('facerecog.html')

@app.route('/video_feed')
@login_required
def video_feed():
    user_id = current_user.id  # Ambil user_id sebelum keluar dari request
    return Response(generate_frames(user_id), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    global face_match, already_present
    return jsonify({"detected": face_match, "already_present": already_present})

@app.route('/register', methods=['GET', 'POST'])
def signup():
    return register()
    
@app.route('/success')
@login_required
def success():
    return render_template('Homepage.html')

if __name__ == "__main__":
    app.run(debug=True)