# Import necessary modules from Flask for creating the web application and handling requests.
from flask import Flask, request, jsonify, render_template, send_file, redirect, url_for, flash, abort, make_response
# Import YouTubeTranscriptApi for fetching subtitles.
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
# Import os for reading environment variables.
import os
# Import io for handling in-memory files (important for sending text files without saving to disk).
import io
# Import requests for general HTTP handling, crucial for downloading thumbnails.
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
from wtforms import BooleanField, StringField, TextAreaField, PasswordField, SubmitField
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

print("DEBUG_CHECK: This app.py version is active! (All Routes Included - Final Check)") # <-- Контрольная строка

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

# --- Register Markdown filter for Jinja2 ---
app.jinja_env.filters['markdown'] = markdown.markdown

# --- User Model Definition ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    def __repr__(self):
        return f"User('{self.username}', '{self.email}')"

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

# --- Flask-Admin Custom ModelView for Post (Protected) ---
class PostAdminForm(BaseForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=120)])
    slug = StringField('Slug', validators=[DataRequired(), Length(max=120)])
    content = TextAreaField('Content', validators=[DataRequired()])
    is_published = BooleanField('Published')

class ProtectedModelView(ModelView):
    def is_accessible(self):
        # Добавляем отладочный вывод
        print(f"DEBUG: ProtectedModelView.is_accessible called. current_user.is_authenticated: {current_user.is_authenticated}")
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        # Добавляем отладочный вывод
        print(f"DEBUG: ProtectedModelView.inaccessible_callback called. Redirecting to login.")
        flash('You must be logged in to access this page.', 'danger')
        return redirect(url_for('login', next=request.url))

class PostAdminView(ProtectedModelView):
    form = PostAdminForm
    column_list = ('title', 'slug', 'date_posted', 'is_published')
    form_columns = ('title', 'slug', 'content', 'is_published')

# --- Flask-Admin Custom ModelView for User (Protected and Custom Form) ---
class UserAdminForm(BaseForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=64)])
    email = StringField('Email', validators=[DataRequired(), Length(min=6, max=120)])
    password = PasswordField('New Password (leave blank to keep current)', validators=[Length(min=6, max=128)])

    def validate_username(self, field):
        if field.data and User.query.filter_by(username=field.data).first() and \
           (self._obj is None or self._obj.username != field.data):
            raise ValidationError('This username is already taken.')

    def validate_email(self, field):
        if field.data and User.query.filter_by(email=field.data).first() and \
           (self._obj is None or self._obj.email != field.data):
            raise ValidationError('This email is already taken.')

class UserAdminView(ProtectedModelView):
    form = UserAdminForm
    column_list = ('username', 'email')
    form_columns = ('username', 'email', 'password')
    form_excluded_columns = ['password_hash'] # Ensure password_hash is not directly editable

    def on_model_change(self, form, model, is_created):
        if form.password.data:
            model.set_password(form.password.data)
        return super().on_model_change(form, model, is_created)

# --- Custom Admin Index View to protect the main admin page ---
class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        # Добавляем отладочный вывод
        print(f"DEBUG: MyAdminIndexView.is_accessible called. current_user.is_authenticated: {current_user.is_authenticated}")
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        # Добавляем отладочный вывод
        print(f"DEBUG: MyAdminIndexView.inaccessible_callback called. Redirecting to login.")
        flash('You must be logged in to access the admin dashboard.', 'danger')
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

# NEW ROUTE: YouTube Subtitle Downloader page
@app.route('/tools/youtube-subtitle-downloader')
def youtube_subtitle_downloader_page():
    return render_template('subtitle_downloader.html')

# NEW ROUTE: YouTube Thumbnail Downloader page
@app.route('/tools/youtube-thumbnail-downloader')
def youtube_thumbnail_downloader_page():
    return render_template('youtube_thumbnail_downloader.html')

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

@app.route('/sitemap.xml', methods=['GET'])
def sitemap():
    """Generates the sitemap.xml file."""
    # List of static pages to include in the sitemap
    pages = [
        ('index', 0.9),  # Homepage, high priority
        ('tools_list_page', 0.8),
        ('pricing_page', 0.7),
        ('faq_page', 0.6),
        ('contact_page', 0.5),
        ('get_started_page', 0.7),
        ('blog_list', 0.8),
        ('login', 0.3), # Low priority for login/register pages
        ('register', 0.3),
        ('reset_request', 0.2),
    ]
    
    # Generate dynamic URLs for blog posts
    posts = Post.query.filter_by(is_published=True).order_by(Post.date_posted.desc()).all()
    
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    # Add static pages
    for page, priority in pages:
        xml_content += '  <url>\n'
        xml_content += f'    <loc>{request.url_root.rstrip("/")}{url_for(page)}</loc>\n'
        xml_content += f'    <lastmod>{datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}</lastmod>\n' # Use current time or a specific update time
        xml_content += f'    <priority>{priority}</priority>\n'
        xml_content += '  </url>\n'

    # Add dynamic pages for AI Tools (placeholders for now, will become actual routes later)
    tool_pages = [
        'video_idea_generator_page',
        'seo_title_description_optimizer_page',
        'youtube_keyword_research_page',
        'youtube_subtitle_downloader_page',
        'youtube_thumbnail_downloader_page' # ADDED THIS LINE
    ]
    for tool_page in tool_pages:
        xml_content += '  <url>\n'
        xml_content += f'    <loc>{request.url_root.rstrip("/")}{url_for(tool_page)}</loc>\n'
        xml_content += f'    <lastmod>{datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}</lastmod>\n'
        xml_content += f'    <priority>0.7</priority>\n' # Medium priority for tools
        xml_content += '  </url>\n'


    # Add blog posts
    for post in posts:
        xml_content += '  <url>\n'
        xml_content += f'    <loc>{request.url_root.rstrip("/")}{url_for("blog_post", slug=post.slug)}</loc>\n'
        xml_content += f'    <lastmod>{post.date_posted.strftime("%Y-%m-%dT%H:%M:%SZ")}</lastmod>\n'
        xml_content += '    <priority>0.8</priority>\n' # Blog posts are usually high priority
        xml_content += '  </url>\n'

    xml_content += '</urlset>\n'

    response = make_response(xml_content)
    response.headers["Content-Type"] = "application/xml"
    return response

@app.route('/robots.txt')
def robots():
    """Generates the robots.txt file."""
    robots_content = "User-agent: *\n"
    robots_content += "Allow: /\n" # Allow all crawlers
    # Disallow admin panel and password reset flows
    robots_content += "Disallow: /admin\n"
    robots_content += "Disallow: /reset_password\n" # Disallow reset request token pages
    robots_content += f"Sitemap: {request.url_root.rstrip('/')}/sitemap.xml\n" # Point to the sitemap

    response = make_response(robots_content)
    response.headers["Content-Type"] = "text/plain"
    return response

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
    except Exception as e: # Corrected: 'a' changed to 'as e'
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

@app.route('/api/download_thumbnail', methods=['GET'])
def download_thumbnail():
    video_id = request.args.get('videoId')
    resolution = request.args.get('resolution', 'maxresdefault') # Default to highest quality
    
    if not video_id:
        return jsonify({"success": False, "message": "Video ID is required"}), 400

    # Base URL for YouTube thumbnails.
    # Common resolutions: 'maxresdefault', 'hqdefault', 'mqdefault', 'sddefault', 'default'
    # 'maxresdefault' is generally 1280x720, 'hqdefault' is 480x360.
    thumbnail_url = f"https://img.youtube.com/vi/{video_id}/{resolution}.jpg"

    global current_proxy_index
    selected_proxy = None
    if PROXIES_URLS_CLEANED:
        selected_proxy = PROXIES_URLS_CLEANED[current_proxy_index % len(PROXIES_URLS_CLEANED)]
        current_proxy_index += 1

    try:
        proxies = {'http': selected_proxy, 'https': selected_proxy} if selected_proxy else None
        
        # Make a request to the thumbnail URL
        response = requests.get(thumbnail_url, stream=True, proxies=proxies)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)

        # Check if the response content is likely a valid image (not a placeholder "no image" file)
        # YouTube returns a 120x90 default.jpg if maxresdefault doesn't exist.
        # We can check content length or response header for content-type.
        if response.headers.get('Content-Type') != 'image/jpeg':
            # This might indicate a placeholder image or an error from YouTube's side
            # For simplicity, we'll proceed, but a more robust check could be added
            # to differentiate between valid low-res and "not found" images.
            pass

        # Use BytesIO to keep the image in memory and send it as a file
        image_buffer = io.BytesIO(response.content)
        
        # Set filename for download
        filename = f"{video_id}_{resolution}_thumbnail.jpg"

        return send_file(image_buffer, mimetype='image/jpeg', as_attachment=True, download_name=filename)

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            # This happens if a specific resolution (like maxresdefault) isn't available.
            # You might want to fall back to a lower resolution or return a specific message.
            print(f"Thumbnail not found for resolution {resolution}: {e}")
            return jsonify({"success": False, "message": f"Thumbnail not found for the requested resolution '{resolution}'. Try 'hqdefault' or 'default'."}), 404
        else:
            print(f"HTTP error downloading thumbnail: {e}")
            return jsonify({"success": False, "message": f"HTTP error occurred: {e.response.status_code}."}), 500
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error downloading thumbnail: {e}")
        return jsonify({"success": False, "message": "Failed to connect to YouTube's thumbnail service. Please check your network or proxy."}), 503
    except requests.exceptions.Timeout as e:
        print(f"Timeout error downloading thumbnail: {e}")
        return jsonify({"success": False, "message": "Request to YouTube's thumbnail service timed out."}), 504
    except Exception as e:
        print(f"Error downloading thumbnail: {e}")
        return jsonify({"success": False, "message": "An unexpected error occurred while downloading the thumbnail."}), 500
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
        user = User(username=form.username.data, email=form.email.data)
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

            new_admin = User(username=admin_username, email=admin_email)
            new_admin.set_password(admin_password)
            db.session.add(new_admin)
            db.session.commit()
            print(f"Default admin user '{admin_username}' created. Password: '{admin_password}'")
            print("PLEASE LOG IN WITH THESE CREDENTIALS. AND CHANGE THIS PASSWORD IMMEDIATELY AFTER FIRST LOGIN!")
            
    # Run the app. Debug mode is now conditional.
    app.run(debug=debug_mode)