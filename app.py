# Import necessary modules from Flask for creating the web application and handling requests.
from flask import Flask, request, jsonify, render_template, send_file, redirect, url_for, flash, abort
# Import YouTubeTranscriptApi for fetching subtitles.
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
# Import os for reading environment variables.
import os
# Import io for handling in-memory files (important for sending text files without saving to disk).
import io
# Import requests for general HTTP handling (для запросов к Telegram API).
import requests

# --- Database imports ---
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime # For timestamps in blog posts

# --- Flask-Admin imports ---
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView

# --- WTForms imports for custom form ---
from flask_admin.model.form import BaseForm
from wtforms import BooleanField, StringField, TextAreaField, PasswordField, SubmitField, SelectField # Added SelectField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError

# --- Flask-Login imports ---
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm # For creating web forms

# --- Flask-Mail imports for password reset ---
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer as Serializer # For generating secure secure tokens

# --- Markdown import for rendering blog content ---
import markdown

print("DEBUG_CHECK: This app.py version is active! (User Types, Admin Panel, and Ads.txt Route)") # <-- Контрольная строка

# Initialize the Flask application.
app = Flask(__name__, static_folder='.', template_folder='.')

# --- Secret Key Configuration ---
# Flask requires a secret key for session management, used by Flask-Admin and Flask-Login.
# In production, this should be a strong, randomly generated key stored as an environment variable.
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a_very_secret_and_unique_key_for_dev')

# --- Database Configuration ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# --- Flask-Login Initialization ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# --- Flask-Mail Configuration ---
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.mailtrap.io')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 2525))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() in ('true', '1', 't')
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', 'your_mailtrap_username')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', 'your_mailtrap_password')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@ytgrowth.com')

mail = Mail(app)

# --- Telegram Bot Configuration (kept for reference, but not used in frontend now) ---
# TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') # Already defined in the incoming app.py
# TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID') # Already defined in the incoming app.py

# --- Register Markdown filter for Jinja2 ---
app.jinja_env.filters['markdown'] = markdown.markdown

# --- User Model Definition ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    user_type = db.Column(db.String(20), nullable=False, default='regular') # 'admin', 'regular', 'paid'

    def __repr__(self):
        return f"User('{self.username}', '{self.email}', '{self.user_type}')"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_reset_token(self, expires_sec=1800):
        s = Serializer(app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id})

    @staticmethod
    def verify_reset_token(token):
        s = Serializer(app.config['SECRET_KEY'])
        try:
            user_id = s.loads(token)['user_id']
        except:
            return None
        return db.session.get(User, user_id)

    @property
    def is_admin(self):
        return self.user_type == 'admin'

    @property
    def is_paid_user(self): # Added for future use, if 'paid' tier becomes relevant
        return self.user_type == 'paid'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- Post Model Definition ---
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_published = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"Post('{self.title}', '{self.date_posted}')"

# --- Flask-Admin Custom ModelView for Post (Protected by Admin only) ---
class ProtectedModelView(ModelView):
    def is_accessible(self):
        # Admin access is now required
        return current_user.is_authenticated and getattr(current_user, 'is_admin', False)

    def inaccessible_callback(self, name, **kwargs):
        flash('You must be logged in as an administrator to access this page.', 'danger')
        return redirect(url_for('login', next=request.url))

class PostAdminForm(BaseForm): # Define PostAdminForm here if it's used by PostAdminView
    title = StringField('Title', validators=[DataRequired()])
    slug = StringField('Slug', validators=[DataRequired()])
    content = TextAreaField('Content')
    is_published = BooleanField('Is Published')

class PostAdminView(ProtectedModelView):
    form = PostAdminForm
    column_list = ('title', 'slug', 'date_posted', 'is_published')
    form_columns = ('title', 'slug', 'content', 'is_published')

# --- Flask-Admin Custom ModelView for User (Protected and Custom Form) ---
class UserAdminForm(FlaskForm): # Changed to FlaskForm for proper WTForms integration
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=64)])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('New Password (leave blank to keep current)', validators=[Length(min=6, max=128)])
    user_type = SelectField('User Type', choices=[('regular', 'Regular User'), ('paid', 'Paid User'), ('admin', 'Administrator')], validators=[DataRequired()])


    def validate_username(self, field):
        # Allow validation to pass if the username is unchanged during an edit
        if User.query.filter_by(username=field.data).first() and \
           (self._obj is None or self._obj.username != field.data): # _obj refers to the model instance being edited
            raise ValidationError('This username is already taken.')

    def validate_email(self, field):
        # Allow validation to pass if the email is unchanged during an edit
        if User.query.filter_by(email=field.data).first() and \
           (self._obj is None or self._obj.email != field.data): # _obj refers to the model instance being edited
            raise ValidationError('This email is already taken.')

class UserAdminView(ProtectedModelView):
    form = UserAdminForm
    column_list = ('username', 'email', 'user_type')
    form_columns = ('username', 'email', 'password', 'user_type')
    form_excluded_columns = ['password_hash']

    def on_model_change(self, form, model, is_created):
        # Hash password only if it's provided in the form
        if form.password.data:
            model.set_password(form.password.data)
        # Ensure user_type is set for new users if not explicitly provided (should be by form, but as a safeguard)
        if is_created and not form.user_type.data:
            model.user_type = 'regular'
        return super().on_model_change(form, model, is_created)

# --- Custom Admin Index View to protect the main admin page (Admin only) ---
class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        # Admin access is now required
        return current_user.is_authenticated and getattr(current_user, 'is_admin', False)

    def inaccessible_callback(self, name, **kwargs):
        flash('You must be logged in as an administrator to access the admin dashboard.', 'danger')
        return redirect(url_for('login', next=request.url))

# --- Flask-Admin Initialization ---
admin = Admin(app, name='Blog Admin', template_mode='bootstrap3', index_view=MyAdminIndexView(url='/admin'))
admin.add_view(PostAdminView(Post, db.session))
admin.add_view(UserAdminView(User, db.session))

# --- Login Form ---
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')

# --- Registration Form ---
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=64)])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField('Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email address.')

# --- Password Reset Forms ---
class RequestResetForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired()])
    submit = SubmitField('Request Password Reset')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is None:
            raise ValidationError('There is no account with that email. You must register first.')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Reset Password')

# --- Proxy Configuration ---
PROXIES_LIST_RAW = os.getenv('PROXIES_LIST', '').split(',')
PROXIES_URLS_CLEANED = [p.strip() for p in PROXIES_LIST_RAW if p.strip()]
current_proxy_index = 0

def set_global_proxy_env(proxy_url):
    """Sets HTTP_PROXY and HTTPS_PROXY environment variables."""
    os.environ['HTTP_PROXY'] = proxy_url
    os.environ['HTTPS_PROXY'] = proxy_url
    print(f"Set environment proxies to: {proxy_url}")

def clear_global_proxy_env():
    """Clears HTTP_PROXY and HTTPS_PROXY environment variables."""
    if 'HTTP_PROXY' in os.environ:
        del os.environ['HTTP_PROXY']
    if 'HTTPS_PROXY' in os.environ:
        del os.environ['HTTPS_PROXY']
    print("Cleared environment proxies.")

# --- Helper function to send Telegram message (not currently used by frontend) ---
# This part was in the previous app.py. Keeping it for consistency if it was intended.
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram bot token or chat ID is not configured. Skipping Telegram notification.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, data=payload, timeout=5)
        response.raise_for_status()
        print(f"Telegram notification sent successfully! Status: {response.status_code}")
        return True
    except requests.exceptions.Timeout:
        print("Telegram API request timed out.")
    except requests.exceptions.RequestException as e:
        print(f"Error sending Telegram notification: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while sending Telegram notification: {e}")
    return False


# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

# NEW: Route to serve ads.txt directly from the root
@app.route('/ads.txt')
def serve_ads_txt():
    # Construct the full path to the ads.txt file
    # os.getcwd() gets the current working directory, which should be your project root
    ads_txt_path = os.path.join(os.getcwd(), 'ads.txt')
    
    # Check if the file exists
    if not os.path.exists(ads_txt_path):
        # If the file doesn't exist, return a 404 error
        print(f"ads.txt not found at: {ads_txt_path}")
        abort(404) # Flask's way to return a 404 Not Found
    
    # Serve the file directly
    return send_file(ads_txt_path, mimetype='text/plain')


# Route for the main tools page
@app.route('/tools')
def tools_list_page():
    return render_template('tools.html')

# Routes for individual tool pages
@app.route('/tools/video-idea-generator')
def video_idea_generator_page():
    return render_template('video_idea_generator.html')


@app.route('/tools/seo-title-description-optimizer')
def seo_title_description_optimizer_page():
    return render_template('seo_title_description_optimizer.html')

@app.route('/tools/youtube-keyword-research')
def youtube_keyword_research_page():
    return render_template('youtube_keyword_research.html')

# New routes for general pages
@app.route('/pricing')
def pricing_page():
    return render_template('pricing.html')

@app.route('/faq')
def faq_page():
    return render_template('faq.html')

@app.route('/contact')
def contact_page():
    return render_template('contact.html')

@app.route('/get-started')
def get_started_page():
    return render_template('get_started.html')


@app.route('/blog')
def blog_list():
    posts = Post.query.filter_by(is_published=True).order_by(Post.date_posted.desc()).all()
    return render_template('blog_list.html', posts=posts, title="Blog")

@app.route('/blog/<slug>')
def blog_post(slug):
    post = Post.query.filter_by(slug=slug, is_published=True).first_or_404()
    return render_template('blog_post.html', post=post, title=post.title)


@app.route('/api/fetch_subtitles', methods=['POST'])
def fetch_subtitles():
    data = request.get_json(silent=True)
    
    print(f"Received data type: {type(data)}")
    print(f"Received data: {data}")

    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "Invalid request payload. Expected a JSON object."}), 400

    video_id = data.get('videoId')

    if not video_id:
        return jsonify({"success": False, "message": "Video ID is required"}), 400

    global current_proxy_index
    selected_proxy = None
    if PROXIES_URLS_CLEANED:
        selected_proxy = PROXIES_URLS_CLEANED[current_proxy_index % len(PROXIES_URLS_CLEANED)]
        current_proxy_index += 1
    
    try:
        if selected_proxy:
            set_global_proxy_env(selected_proxy)
        
        transcript_list_obj = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript_list = list(transcript_list_obj)
        
        available_subtitles = []
        for transcript in transcript_list:
            available_subtitles.append({
                "lang": transcript.language_code,
                "name": transcript.language,
                "is_auto_generated": transcript.is_generated,
                "is_translatable": transcript.is_translatable
            })
        
        return jsonify({"success": True, "subtitles": available_subtitles}), 200

    except TranscriptsDisabled:
        return jsonify({"success": False, "message": "Subtitles are disabled for this video."}), 404
    except NoTranscriptFound:
        return jsonify({"success": False, "message": "No subtitles found for this video (or they are not public/available)."}), 404
    except requests.exceptions.RequestException as e:
        print(f"Network or proxy error fetching subtitles: {e}")
        return jsonify({"success": False, "message": "A network or proxy error occurred. Please try again or check proxy settings."}), 503
    except Exception as e:
        print(f"Error fetching subtitles: {e}")
        return jsonify({"success": False, "message": "An unexpected error occurred while fetching subtitle info."}), 500
    finally:
        clear_global_proxy_env()


@app.route('/api/download_subtitle', methods=['GET'])
def download_subtitle():
    video_id = request.args.get('videoId')
    lang = request.args.get('lang')
    file_format = request.args.get('format', 'srt')

    if not video_id or not lang:
        return jsonify({"success": False, "message": "Video ID and language are required"}), 400

    global current_proxy_index
    selected_proxy = None
    if PROXIES_URLS_CLEANED:
        selected_proxy = PROXIES_URLS_CLEANED[current_proxy_index % len(PROXIES_URLS_CLEANED)]
        current_proxy_index += 1

    try:
        if selected_proxy:
            set_global_proxy_env(selected_proxy)

        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
        
        subtitle_content = ""

        if file_format == 'txt':
            for entry in transcript:
                subtitle_content += f"{entry['text']}\n"
            mimetype = "text/plain"
            filename = f"{video_id}_{lang}.txt"
        elif file_format == 'srt':
            for i, entry in enumerate(transcript):
                start_ms = int(entry['start'] * 1000)
                end_ms = int((entry['start'] + entry['duration']) * 1000)

                def format_timestamp(ms):
                    hours = ms // 3_600_000
                    ms %= 3_600_000
                    minutes = ms // 60_000
                    ms %= 60_000
                    seconds = ms // 1_000
                    milliseconds = ms % 1_000
                    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

                subtitle_content += f"{i + 1}\n"
                subtitle_content += f"{format_timestamp(start_ms)} --> {format_timestamp(end_ms)}\n"
                subtitle_content += f"{entry['text']}\n\n"
            mimetype = "application/x-subrip"
            filename = f"{video_id}_{lang}.srt"
        else:
            return jsonify({"success": False, "message": "Unsupported format. Only 'txt' and 'srt' are supported."}), 400

        buffer = io.BytesIO(subtitle_content.encode('utf-8'))
        
        return send_file(buffer, mimetype=mimetype, as_attachment=True, download_name=filename)

    except NoTranscriptFound:
        return jsonify({"success": False, "message": "No subtitles found for this video (or they are not public/available)."}), 404
    except TranscriptsDisabled:
        return jsonify({"success": False, "message": "Subtitles are disabled for this video."}), 404
    except requests.exceptions.RequestException as e:
        print(f"Network or proxy error downloading subtitle: {e}")
        return jsonify({"success": False, "message": "A network or proxy error occurred during download. Please try again or check proxy settings."}), 503
    except Exception as e:
        print(f"Error downloading subtitle: {e}")
        return jsonify({"success": False, "message": "An unexpected error occurred while downloading the subtitle."}), 500
    finally:
        clear_global_proxy_env()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        flash('You are already logged in!', 'info')
        return redirect(url_for('admin.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))
        login_user(user)
        next_page = request.args.get('next')
        flash(f'Logged in as {user.username}.', 'success')
        return redirect(next_page or url_for('admin.index'))

    return render_template('login.html', form=form, title="Login")

@app.route('/logout')
def logout():
    if not current_user.is_authenticated:
        flash('You are not currently logged in.', 'info')
        return redirect(url_for('index'))
        
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Only allow registration if no users exist.
    if User.query.count() > 0:
        flash('Registration is currently closed.', 'danger')
        return redirect(url_for('login'))

    if current_user.is_authenticated:
        return redirect(url_for('admin.index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data, user_type='regular') # Default new users to 'regular'
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now a registered user! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)


def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password Reset Request',
                  sender=app.config['MAIL_DEFAULT_SENDER'],
                  recipients=[user.email])
    msg.body = f'''To reset your password, visit the following link:
{url_for('reset_token', token=token, _external=True)}

If you did not make this request then simply ignore this email and no changes will be made.
'''
    mail.send(msg)

@app.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('admin.index'))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_reset_email(user)
            flash('An email has been sent with instructions to reset your password.', 'info')
            return redirect(url_for('login'))
        else:
            # For security, do not reveal if email exists or not
            flash('If an account with that email exists, an email has been sent with instructions to reset your password.', 'info')
            return redirect(url_for('login')) # Redirect regardless for security
    return render_template('reset_request.html', title='Reset Password', form=form)

@app.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('admin.index'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('That is an invalid or expired token.', 'danger')
        return redirect(url_for('reset_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been updated! You are now able to log in.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_token.html', title='Reset Password', form=form)


# This ensures the Flask development server runs only when the script is executed directly.
if __name__ == '__main__':
    # Determine debug mode based on environment variable, default to False for production
    # Set FLASK_DEBUG=1 in your development environment to enable debug mode
    debug_mode = os.getenv('FLASK_DEBUG') == '1'

    with app.app_context():
        # IMPORTANT: db.create_all() creates tables, but migrations are preferred for changes.
        # It's here for initial local setup convenience. For production, rely on 'flask db upgrade'.
        db.create_all()

        # Optional: Create an initial admin user if none exists
        # This code will now ONLY create the user, it will NOT automatically log them in.
        if User.query.count() == 0:
            print("No users found. Creating a default admin user.")
            admin_username = os.getenv('ADMIN_DEFAULT_USERNAME', 'admin')
            admin_email = os.getenv('ADMIN_DEFAULT_EMAIL', 'admin@example.com')
            admin_password = os.getenv('ADMIN_DEFAULT_PASSWORD', 'password') # CHANGE THIS IN PRODUCTION!

            new_admin = User(username=admin_username, email=admin_email, user_type='admin') # Set user_type for admin
            new_admin.set_password(admin_password)
            db.session.add(new_admin)
            db.session.commit()
            print(f"Default admin user '{admin_username}' created. Password: '{admin_password}'")
            print("PLEASE LOG IN WITH THESE CREDENTIALS. AND CHANGE THIS PASSWORD IMMEDIATELY AFTER FIRST LOGIN!")
            
    # Run the app. Debug mode is now conditional.
    app.run(debug=debug_mode)
