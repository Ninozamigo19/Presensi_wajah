from flask import Flask, render_template, request, redirect, url_for, flash, session, Response, jsonify, make_response
from decouple import config
from flask_login import LoginManager, logout_user, login_required, current_user, login_user
import uuid, secrets
import psycopg2
from Auth.app import generate_frames, face_match, already_present
from Auth.register import register
from Auth.login import login , get_db, User

app = Flask(__name__)
app.secret_key=config('SECRET_KEY', default='36bbfeee4f53a83212bbf8a4984e96101983c4b61c39cc19b0d01fead6332272')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'signin'  # Redirect unauthorized users

@app.route('/', methods=['GET', 'POST'])
def signin():
    return login()  # Simply call the login function from login.py

@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    logout_user()
    response = make_response(redirect(url_for('signin')))
    response.set_cookie('user_id', '', max_age=0)  # Hapus cookie
    return response


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
    # ➕ Ambil user_id dari cookie (jika ada)
    user_id_from_cookie = request.cookies.get('user_id')
    print(f"🍪 Cookie user_id: {user_id_from_cookie}")

    print(f"🏠 Home accessed by: {current_user.username} (ID: {current_user.id})")  # Debugging user login

    # Connect to the database
    conn = get_db()  # Use get_db instead of create_connection
    
    if conn:
        try:
            cursor = conn.cursor()
            # Query to get attendance records for the logged-in user
            cursor.execute("""
                SELECT tanggal_dan_waktu, status
                FROM face_matches
                WHERE user_id = %s
            """, (current_user.id,))
            # Fetch attendance records
            attendance_records = cursor.fetchall()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"⚠️ Error fetching attendance records: {e}")
            attendance_records = []  # Empty list if there's an error fetching data

    # Render the template with attendance records and username
    return render_template('Homepage.html', attendance_records=attendance_records, username=current_user.username)

@app.route('/Presensi')
@login_required
def presensi():
    return render_template('facerecog.html')

def get_user_id_from_token():
    return current_user.id if current_user.is_authenticated else None

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