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
login_manager.login_view = 'signin'  # Redirect unauthorized users

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
def load_user(User_id):
    """Flask-Login memuat user berdasarkan ID"""
    try:
        User_id = str(uuid.UUID(User_id))  # Konversi ke string sebelum query
    except ValueError:
        return None

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT user_id, username FROM pengguna WHERE user_id = %s", (User_id,))  # Sudah string
    user = cursor.fetchone()
    cursor.close()
    db.close()

    return User(user[0], user[1]) if user else None



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
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid Username or password.', 'danger')

    return render_template('login.html')


# Logout route
@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('signin'))


# Home route (protected)
@app.route('/Home')
@login_required
def home():
    return render_template('Homepage.html', username=current_user.username)  # `current_user` is automatically available in templates

# Run the app
if __name__ == '__main__':
    app.run(debug=True)
