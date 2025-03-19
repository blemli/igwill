import os
import datetime
import random
import string
import arrow
import re
from flask import (
    Flask,
    request,
    redirect,
    send_from_directory,
    url_for,
    render_template,
    flash
)
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = 'seckey'

limiter = Limiter(key_func=get_remote_address)
limiter.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('ADMIN_PASS', 'secret')

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'storage')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

class User(UserMixin):
    def __init__(self, id, name):
        self.id = id
        self.name = name

@login_manager.user_loader
def load_user(user_id):
    if user_id == 'admin':
        return User('admin', 'Admin')
    return None

def human_age(t):
    dt = arrow.get(t, 'YYYYMMDDHHmmss')
    return dt.humanize(locale='de')

def clean_files():
    for f in os.listdir(UPLOAD_FOLDER):
        parts = f.split('-', 3)
        if len(parts) < 4:
            os.remove(os.path.join(UPLOAD_FOLDER, f))
            continue
        t = parts[0]
        dt = datetime.datetime.strptime(t, '%Y%m%d%H%M%S')
        if datetime.datetime.now() - dt > datetime.timedelta(hours=24):
            os.remove(os.path.join(UPLOAD_FOLDER, f))

@app.before_request
def before_request():
    clean_files()

def file_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))


@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/', methods=['GET', 'POST'])
@limiter.limit("250 per minute")
def index():
    if request.method == 'POST' and 'code' in request.form:
        code = request.form.get('code', '').upper()
        for f in os.listdir(UPLOAD_FOLDER):
            parts = f.split('-', 3)
            if len(parts) >= 3 and parts[1] == code:
                pattern = re.compile(r'^(\d{14})-([A-Z0-9]{4})-(adm|ano)-(.*)$')
                match = pattern.match(f)
                original_filename = match.group(4) if match else f
                flash(f"Datei {original_filename} ladet herunter! Check deinen Download-Ordner.")
                return send_from_directory(
                    UPLOAD_FOLDER,
                    f,
                    as_attachment=True,
                    download_name=original_filename
                )
        flash("Falscher Code!")

    files = []
    if current_user.is_authenticated:
        for f in os.listdir(UPLOAD_FOLDER):
            parts = f.split('-', 3)
            if len(parts) < 4:
                continue
            t, code, who, orig = parts
            age = human_age(t)
            files.append({
                'name': f,
                'orig': orig,
                'age': age,
                'code': code,
                'timestamp': t
            })
        files.sort(key=lambda x: x['timestamp'], reverse=True)

    return render_template('index.html', files=files)

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return redirect(url_for('index'))
    file = request.files['file']
    if not file.filename:
        return redirect(url_for('index'))

    stamp = arrow.utcnow().strftime('%Y%m%d%H%M%S')
    code = file_code()
    who = 'adm' if current_user.is_authenticated else 'ano'
    savename = f"{stamp}-{code}-{who}-{file.filename}"
    file.save(os.path.join(UPLOAD_FOLDER, savename))

    if who == 'adm':
        flash(f"Upload OK. Code: {code}")
    else:
        flash(f"Datei {file.filename} hochgeladen!")

    return redirect(url_for('index'))

@app.route('/admin', methods=['GET', 'POST'])
@limiter.limit("250 per minute")
def login():
    if request.method == 'POST':
        if (request.form.get('user') == ADMIN_USER and
                request.form.get('pw') == ADMIN_PASS):
            login_user(User('admin', 'Admin'))
            return redirect(url_for('index'))
        flash("Falsche Logindaten!")
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/get/<path:fname>')
@limiter.limit("250 per minute")
@login_required
def get_file(fname):
    pattern = re.compile(r'^(\d{14})-([A-Z0-9]{4})-(adm|ano)-(.*)$')
    match = pattern.match(fname)
    original_filename = match.group(4) if match else fname
    return send_from_directory(
        UPLOAD_FOLDER,
        fname,
        as_attachment=True,
        download_name=original_filename
    )

@app.route('/del/<path:fname>')
@limiter.limit("250 per minute")
@login_required
def del_file(fname):
    path = os.path.join(UPLOAD_FOLDER, fname)
    if os.path.exists(path):
        os.remove(path)
    return redirect(url_for('index'))


@app.route('/share', methods=['POST'])
def share():
    # Falls die Share-Funktion ohne Datei kommt
    if 'file' not in request.files:
        flash("Keine Datei übertragen.")
        return redirect(url_for('index'))

    file = request.files['file']
    if not file.filename:
        flash("Leere Datei.")
        return redirect(url_for('index'))

    # Optional: title/text/url auslesen
    incoming_title = request.form.get("title", "")
    incoming_text = request.form.get("text", "")
    incoming_url = request.form.get("url", "")

    # Gleiche Logik wie bei /upload
    stamp = arrow.utcnow().strftime('%Y%m%d%H%M%S')
    code = file_code()
    who = 'ano'
    if current_user.is_authenticated:
        who = 'adm'

    savename = f"{stamp}-{code}-{who}-{file.filename}"
    file.save(os.path.join(UPLOAD_FOLDER, savename))

    flash(f"Datei {file.filename} via Share hochgeladen!")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run('0.0.0.0', 5000)
