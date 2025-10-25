from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os, uuid, smtplib, ssl

# -------------------- App Config --------------------
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///creovibe.db'
app.config['SECRET_KEY'] = 'creovibe_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'webm', 'ogg', 'mov'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# -------------------- Gmail Config --------------------
EMAIL_SENDER = "creovibe001@gmail.com"
EMAIL_PASSWORD = "ejem rsiu zzbq lcfx"  # Gmail App Password
EMAIL_RECEIVER = "creovibe001@gmail.com"  # You receive messages here


# -------------------- Database Models --------------------
class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(200))
    media_items = db.relationship('Media', backref='service', lazy=True)


class Media(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(300), nullable=False)
    caption = db.Column(db.String(300))
    media_type = db.Column(db.String(10), nullable=False)  # image or video
    is_hero = db.Column(db.Boolean, default=False)
    page_name = db.Column(db.String(50), default='home')  # home, about, services, portfolio
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=True)


# -------------------- Admin Auth --------------------
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = generate_password_hash("creovibe123")


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return wrapper


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# -------------------- Admin Routes --------------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['logged_in'] = True
            flash('✅ Logged in successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('❌ Invalid credentials!', 'error')
    return render_template('admin_login.html')


@app.route('/admin/logout')
@login_required
def admin_logout():
    session.pop('logged_in', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('home'))


@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    allowed_pages = ['home', 'about', 'services', 'portfolio']
    selected_page = request.args.get('page', 'home')
    if selected_page not in allowed_pages:
        selected_page = 'home'

    services = Service.query.all()
    media_list = Media.query.filter_by(page_name=selected_page).order_by(Media.id.desc()).all()

    if request.method == 'POST':
        f = request.files.get('media')
        caption = request.form.get('caption', '').strip()
        page_name = request.form.get('page_name', selected_page)
        service_id = request.form.get('service_id') or None
        is_hero = bool(request.form.get('is_hero'))

        if page_name not in allowed_pages:
            page_name = selected_page

        if not f or f.filename == '':
            flash('⚠️ Please select a file.', 'error')
            return redirect(url_for('admin_dashboard', page=page_name))
        if not allowed_file(f.filename):
            flash('⚠️ Unsupported file type.', 'error')
            return redirect(url_for('admin_dashboard', page=page_name))

        filename = secure_filename(f.filename)
        ext = os.path.splitext(filename)[1].lower()
        unique_name = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)

        try:
            if is_hero:
                Media.query.filter_by(page_name=page_name).update({Media.is_hero: False})
                db.session.commit()

            f.save(filepath)
            media_type = 'video' if ext in ['.mp4', '.webm', '.ogg', '.mov'] else 'image'

            new_media = Media(
                filename=unique_name,
                caption=caption or None,
                media_type=media_type,
                is_hero=is_hero,
                page_name=page_name,
                service_id=service_id
            )
            db.session.add(new_media)
            db.session.commit()
            flash(f'✅ Media uploaded to {page_name} successfully!', 'success')
        except Exception as e:
            if os.path.exists(filepath):
                os.remove(filepath)
            flash(f'❌ Upload failed: {e}', 'error')

        return redirect(url_for('admin_dashboard', page=page_name))

    return render_template('admin_dashboard.html',
                           services=services,
                           media_list=media_list,
                           selected_page=selected_page)


@app.route('/admin/delete/<int:media_id>', methods=['POST'])
@login_required
def delete_media(media_id):
    media = Media.query.get_or_404(media_id)
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], media.filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        db.session.delete(media)
        db.session.commit()
        flash('🗑️ Media deleted successfully!', 'success')
    except Exception as e:
        flash(f'❌ Error deleting media: {e}', 'error')
    return redirect(request.referrer or url_for('admin_dashboard'))


# -------------------- Public Routes --------------------
@app.route('/')
def home():
    hero = Media.query.filter_by(page_name='home', is_hero=True).first()
    media_list = Media.query.filter_by(page_name='home').all()
    return render_template('home.html', hero=hero, media_list=media_list)


@app.route('/about')
def about():
    hero = Media.query.filter_by(page_name='about', is_hero=True).first()
    about_images = Media.query.filter_by(page_name='about').all()
    return render_template('about.html', hero=hero, about_images=about_images)


@app.route('/services')
def services_page():
    hero = Media.query.filter_by(page_name='services', is_hero=True).first()
    services = Service.query.all()
    return render_template('services.html', hero=hero, services=services)


@app.route('/services/<int:service_id>')
def service_detail(service_id):
    service = Service.query.get_or_404(service_id)
    photos = Media.query.filter_by(service_id=service.id, media_type='image').all()
    videos = Media.query.filter_by(service_id=service.id, media_type='video').all()
    return render_template('service_detail.html', service=service, photos=photos, videos=videos)


# -------------------- Portfolio Page --------------------
@app.route('/portfolio')
def portfolio():
    hero = Media.query.filter_by(page_name='portfolio', is_hero=True).first()
    portfolio_list = Media.query.filter_by(page_name='portfolio').all()
    return render_template('portfolio.html', hero=hero, portfolio_list=portfolio_list)


# -------------------- Contact Page (with Email Sending) --------------------
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', 'Guest')
        email = request.form.get('email', '')
        message = request.form.get('message', '')

        # Send email using Gmail SMTP
        try:
            subject = f"📩 New message from {name}"
            body = f"From: {name}\nEmail: {email}\n\nMessage:\n{message}"
            email_text = f"Subject: {subject}\n\n{body}"

            context = ssl.create_default_context()
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, email_text.encode("utf-8"))

            flash(f"✅ Thanks {name}, your message was sent successfully!", "success")
        except Exception as e:
            flash(f"❌ Failed to send message: {e}", "error")

        return redirect(url_for("contact"))
    return render_template("contact.html")


# -------------------- Utility --------------------
def create_default_admin():
    db.create_all()
    if Service.query.count() == 0:
        s = Service(name='Photography', description='Commercial & brand photography services')
        db.session.add(s)
        db.session.commit()


# -------------------- Run --------------------
if __name__ == '__main__':
    with app.app_context():
        create_default_admin()
    app.run(debug=True)
