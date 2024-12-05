from flask import Flask , render_template, Response, jsonify

from Auth.app import generate_frames, face_match, already_present
from Auth.register import register

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('Homepage.html')

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
