from flask import Flask, render_template, request, redirect, url_for, flash, make_response, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import psycopg2
import uuid
from decouple import config

app = Flask(__name__)
app.secret_key = config('SECRET_KEY', default='36bbfeee4f53a83212bbf8a4984e96101983c4b61c39cc19b0d01fead6332272')

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'signin'  # Redirect unauthorized users

# Make `current_user` available in all templates
@app.context_processor
def inject_user():
    return dict(current_user=current_user)

# Database connection
def get_db():
    try:
        conn = psycopg2.connect(
        host=config('DB_HOST'),
        port=config('DB_PORT', default=5432),
        database=config('DB_NAME'),
        user=config('DB_USER'),
        password=config('DB_PASSWORD')
        )
        print("Connection successful!")
        return conn  # Return the connection so it can be used
    except Exception as e:
        print(f"Connection error: {str(e)}")
        return None  # Return None if the connection fails

class User(UserMixin):
    def __init__(self, user_id, username):
        self.id = str(user_id)  # Pastikan ID dalam bentuk string
        self.username = username

    def get_id(self):
        return self.id  # Flask-Login mengharapkan string

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

# Login route
# @app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Connect to the database and get the user info
        conn = get_db()  # or use psycopg2.connect(...) directly if preferred
        cursor = conn.cursor()

        cursor.execute("SELECT user_id, username, password FROM pengguna WHERE username = %s", (username,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user and user[2] == password:  # Check the password directly (plaintext comparison)
            # If the password matches, log the user in
            user_obj = User(str(user[0]), user[1])  # Assuming user[0] is the UUID (string)
            login_user(user_obj)

            # Generate a session token (or you can use a cookie)
            session_token = uuid.uuid4().hex  # Using UUID for the session token
            session["token"] = session_token  # Store the token in Flask session

            # Optionally save the session token to the database
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO sessions (user_id, token) VALUES (%s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET token = EXCLUDED.token",
                (user[0], session_token)
            )
            conn.commit()
            cursor.close()
            conn.close()

            # Redirect to home
            response = make_response(redirect(url_for('home')))
            return response
        else:
            flash('Invalid Username or Password', 'danger')

    return render_template('login.html')

# Logout route
@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    print(f"👋 Logging out user: {current_user.username} (ID: {current_user.id})")
    logout_user()
    flash('You have been logged out.', 'info')

    # ➖ Hapus Cookie
    response = make_response(redirect(url_for('signin')))
    response.set_cookie('user_id', '', max_age=0)  # Set max_age=0 untuk menghapus cookie
    return response

# Home route (protected)
@app.route('/home')
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
                SELECT user_id, username, email
                FROM pengguna
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

# Run the app
if __name__ == '__main__':
    app.run(debug=True)
