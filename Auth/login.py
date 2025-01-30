from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import psycopg2
from decouple import config

app = Flask(__name__)
app.secret_key = config('SECRET_KEY', default='supersecretkey')

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Redirect unauthorized users

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

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, username):
        self.username = username
    
    def get_id(self):
        """Override Flask-Login's default ID retrieval method."""
        return self.username  # Use username as the unique identifier

# Load user from DB
@login_manager.user_loader
def load_user(username):
    """Flask-Login loads a user based on their username."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT username FROM pengguna WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    db.close()
    
    return User(user[0]) if user else None

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT username, password FROM pengguna WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user and user[1] == password:  # Compare plain text passwords directly
            user_obj = User(user[0])  # Create user object with only the username
            login_user(user_obj)
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')

# Logout route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# Home route (protected)
@app.route('/')
@login_required
def home():
    return render_template('Homepage.html', username=current_user.username)

# Run the app
if __name__ == '__main__':
    app.run(debug=True)
