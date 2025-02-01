from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import psycopg2
import uuid
from decouple import config

app = Flask(__name__)
app.secret_key = config('SECRET_KEY', default='supersecretkey')

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.session_protection = "strong"  # Ensures session security
login_manager.login_view = 'signin'



# Make `current_user` available in all templates
@app.context_processor
def inject_user():
    return dict(current_user=current_user)

# Database connection
def get_db():
    try:
        return psycopg2.connect(
            host="localhost",
            database="Presensi_wajah",
            user="postgres",
            password="123"
        )
    except psycopg2.Error as e:
        print(f"Error: {e}")
        return None

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
        Username = request.form['username']
        Password = request.form['password']

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT user_id, username, password FROM pengguna WHERE username = %s", (Username,))
        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user and user[2] == Password:  # Ini sebaiknya menggunakan hashing
            user_obj = User(user[0], user[1])  # `user[0]` adalah UUID
            login_user(user_obj)
            print(f"✅ Login success: User ID={user_obj.id}, Username={user_obj.username}")
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            print("❌ Invalid username or password")
            flash('Invalid Username or password.', 'danger')

    return render_template('login.html')

# Logout route
@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    print(f"👋 Logging out user: {current_user.username} (ID: {current_user.id})")
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('signin'))

# Home route (protected)
@app.route('/home')
@login_required
def home():
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