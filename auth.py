from flask import Flask, render_template, request, redirect, url_for, flash, session, Response, jsonify

from Auth.app import generate_frames, face_match, already_present
from Auth.register import register
from Auth.login import login

app = Flask(__name__)

@app.route('/')
def loginPage():
    print("Navigating to login page")
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def LoginFunction():
    return login

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('Anda telah logout.', 'info')
    return redirect(url_for('loginPage'))


@app.route('/Home')
def home():
    if 'username' in session:
        return render_template('Homepage.html', username=session['username'])
    return redirect(url_for('loginPage'))

@app.route('/Presensi')
def presensi():
    return render_template('facerecog.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    global face_match, already_present
    return jsonify({"detected": face_match, "already_present": already_present})

@app.route('/register', methods=['GET', 'POST'])
def signup():
    return register()
    
@app.route('/success')
def success():
    return "<h1>Registrasi berhasil!</h1>"

if __name__ == "__main__":
    app.run(debug=True)
