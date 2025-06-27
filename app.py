# Import necessary modules from Flask for creating the web application and handling requests.
from flask import Flask, request, jsonify, render_template, send_file, redirect, url_for, flash
# Import YouTubeTranscriptApi for fetching subtitles.
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
# Import os for reading environment variables.
import os
# Import io for handling in-memory files (important for sending text files without saving to disk).
import io
# Import requests for general HTTP handling, though youtube_transcript_api uses it internally.
import requests

# --- NEW: Database imports ---
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime # For timestamps in blog posts
# --- NEW: Flask-Admin imports ---
from flask_admin import Admin, AdminIndexView # Import AdminIndexView
from flask_admin.contrib.sqla import ModelView
# --- NEW: WTForms imports for custom form ---
from flask_admin.model.form import BaseForm
from wtforms import BooleanField, StringField, TextAreaField, PasswordField, SubmitField # Added PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError # Added EqualTo, ValidationError
# --- END NEW ---

# --- NEW: Flask-Login imports ---
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm # For creating web forms
# --- END NEW ---

# --- NEW: Flask-Mail imports for password reset ---
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer as Serializer # For generating secure tokens
# --- END NEW ---

# --- NEW: Markdown import for rendering blog content ---
import markdown
# --- END NEW ---

print("DEBUG_CHECK: This app.py version is active!") # <-- Контрольная строка

# Initialize the Flask application.
app = Flask(__name__, static_folder='.', template_folder='.')

# --- NEW: Secret Key Configuration ---
# Flask requires a secret key for session management, used by Flask-Admin and Flask-Login.
# In production, this should be a strong, randomly generated key stored as an environment variable.
# For local development, you can use a simple string, but NEVER use this in production.
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a_very_secret_and_unique_key_for_dev') # Replace with env var in prod!
# --- END NEW ---

# --- NEW: Database Configuration ---
# Render automatically provides DATABASE_URL for PostgreSQL.
# For local development, use SQLite.
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Disables object modification tracking, which consumes memory

db = SQLAlchemy(app)
migrate = Migrate(app, db) # Initialize Flask-Migrate
# --- END NEW ---

# --- NEW: Flask-Login Initialization ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Route to redirect to if login is required
login_manager.login_message_category = 'info' # Flash message category
# --- END NEW ---

# --- NEW: Flask-Mail Configuration ---
# You need to set these environment variables (MAIL_SERVER, MAIL_PORT, MAIL_USE_TLS, MAIL_USERNAME, MAIL_PASSWORD)
# when deploying to Render. For local testing, you can hardcode them or use a local SMTP server.
# Using Mailtrap.io or a real email service (Gmail, SendGrid, Mailgun) is recommended for testing/production.
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.mailtrap.io') # e.g., 'smtp.gmail.com'
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 2525)) # e.g., 587 for TLS, 465 for SSL
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() in ('true', '1', 't') # Use TLS encryption
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', 'your_mailtrap_username') # Your email account username
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', 'your_mailtrap_password') # Your email account password
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@ytgrowth.com') # Sender email address

mail = Mail(app)
# --- END NEW ---

# --- NEW: Register Markdown filter for Jinja2 (using direct assignment) ---
# This is a more direct way to register the filter with Flask's Jinja2 environment.
app.jinja_env.filters['markdown'] = markdown.markdown
# --- END NEW ---

# --- NEW: User Model Definition ---
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

    # Method to get a reset token for password recovery
    def get_reset_token(self, expires_sec=1800): # Token expires in 30 minutes
        s = Serializer(app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id})

    # Static method to verify reset token
    @staticmethod
    def verify_reset_token(token):
        s = Serializer(app.config['SECRET_KEY'])
        try:
            user_id = s.loads(token)['user_id']
        except:
            return None # Token is invalid or expired
        return db.session.get(User, user_id)

# Flask-Login user loader callback
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
# --- END NEW ---

# --- NEW: Post Model Definition (No changes here, just for context) ---
# Define the database model for blog posts
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False) # Unique "slug" for pretty article URLs
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_published = db.Column(db.Boolean, default=False) # Flag for published/drafts

    def __repr__(self):
        return f"Post('{self.title}', '{self.date_posted}')"
# --- END NEW ---

# --- NEW: Flask-Admin Custom ModelView for Post (Protected) ---
# Define a custom form for the Post model to explicitly set field types
class PostAdminForm(BaseForm):
    # Field definitions that match your Post model columns
    title = StringField('Title', validators=[DataRequired(), Length(max=120)])
    slug = StringField('Slug', validators=[DataRequired(), Length(max=120)])
    content = TextAreaField('Content', validators=[DataRequired()])
    is_published = BooleanField('Published') # Explicitly define as BooleanField

# Create a custom ModelView for the Post model, using our custom form
class ProtectedModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated # Only authenticated users can access

    def inaccessible_callback(self, name, **kwargs):
        # Redirect to login page if user doesn't have access
        flash('You must be logged in to access this page.', 'danger')
        return redirect(url_for('login', next=request.url))

class PostAdminView(ProtectedModelView): # Inherit from ProtectedModelView
    form = PostAdminForm # Tell Flask-Admin to use our custom form

    # Optional: Customize column display in the list view
    column_list = ('title', 'slug', 'date_posted', 'is_published')
    # Optional: Customize the order of fields in the form (matches PostAdminForm)
    form_columns = ('title', 'slug', 'content', 'is_published')

# --- NEW: Flask-Admin Custom ModelView for User (Protected and Custom Form) ---
# Define a custom form for the User model to explicitly set field types for admin
class UserAdminForm(BaseForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=64)])
    email = StringField('Email', validators=[DataRequired(), Length(min=6, max=120)])
    # For setting password in admin, we don't expose password_hash directly.
    # We'll handle password setting via methods.
    # Add a temporary password field for creation/reset.
    password = PasswordField('New Password (leave blank to keep current)', validators=[Length(min=6, max=128)])

    # Custom validator to ensure unique username/email during admin edits/creates
    def validate_username(self, field):
        if User.query.filter_by(username=field.data).first() and self._obj.username != field.data:
            raise ValidationError('This username is already taken.')

    def validate_email(self, field):
        if User.query.filter_by(email=field.data).first() and self._obj.email != field.data:
            raise ValidationError('This email is already taken.')

class UserAdminView(ProtectedModelView): # Inherit from ProtectedModelView
    form = UserAdminForm # Tell Flask-Admin to use our custom form

    # Customize the columns shown in the list view
    column_list = ('username', 'email')
    # Customize the fields in the create/edit form
    form_columns = ('username', 'email', 'password') # 'password' is our custom WTForms field

    # Override on_model_change to hash the password before saving
    def on_model_change(self, form, model, is_created):
        if form.password.data: # Only update password if a new one is provided
            model.set_password(form.password.data)
        return super().on_model_change(form, model, is_created)

    # Make password_hash not directly editable in the form if it was automatically added
    # This might not be strictly necessary if form = UserAdminForm is used
    form_excluded_columns = ['password_hash']
# --- END NEW ---

# --- NEW: Custom Admin Index View to protect the main admin page ---
class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        flash('You must be logged in to access the admin dashboard.', 'danger')
        return redirect(url_for('login', next=request.url))
# --- END NEW ---

# --- Flask-Admin Initialization ---
# Setup Flask-Admin
# Use our custom MyAdminIndexView to protect the main /admin route
admin = Admin(app, name='Blog Admin', template_mode='bootstrap3', index_view=MyAdminIndexView(url='/admin')) # MODIFIED LINE

# Add the Post model to Flask-Admin using our custom view
admin.add_view(PostAdminView(Post, db.session))
# Add User model to Admin using our new custom UserAdminView
admin.add_view(UserAdminView(User, db.session)) # MODIFIED LINE
# --- END NEW ---

# --- NEW: Login Form ---
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')

# --- NEW: Registration Form (for initial user creation) ---
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=64)])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email address.')
# --- END NEW ---

# --- NEW: Password Reset Forms ---
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
# --- END NEW ---


# --- Proxy Configuration (No changes here, just for context) ---
# Read proxy settings from environment variables.
PROXIES_LIST_RAW = os.getenv('PROXIES_LIST', '').split(',')
# Clean up any empty strings from the split and ensure they are valid.
PROXIES_URLS_CLEANED = [p.strip() for p in PROXIES_LIST_RAW if p.strip()]

# Counter to cycle through proxies
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


# Define a route for the homepage.
@app.route('/')
def index():
    """
    Renders the main index.html page when the root URL is accessed.
    """
    return render_template('index.html')

# Define an API endpoint to fetch available subtitles for a given YouTube video ID.
@app.route('/api/fetch_subtitles', methods=['POST'])
def fetch_subtitles():
    """
    Fetches available subtitle tracks for a YouTube video ID.
    Expects a JSON payload with 'videoId'.
    Returns a JSON response with available subtitle tracks or an error message.
    """
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
        # --- Ensure proxies are cleared after the request ---
        clear_global_proxy_env()

# --- Define an API endpoint to download specific subtitles. ---
# This endpoint expects a GET request with 'videoId', 'lang', and 'format'.
@app.route('/api/download_subtitle', methods=['GET'])
def download_subtitle():
    """
    Downloads a specific subtitle track for a YouTube video ID in a given format.
    Expects 'videoId', 'lang', and 'format' as query parameters.
    Returns the subtitle content as a file download.
    """
    # Get query parameters from the request URL.
    video_id = request.args.get('videoId')
    lang = request.args.get('lang')
    file_format = request.args.get('format', 'srt') # Default to srt if format is not specified

    # Basic validation for required parameters.
    if not video_id or not lang:
        return jsonify({"success": False, "message": "Video ID and language are required"}), 400

    # --- Proxy application logic for download ---
    global current_proxy_index
    selected_proxy = None
    if PROXIES_URLS_CLEANED:
        selected_proxy = PROXIES_URLS_CLEANED[current_proxy_index % len(PROXIES_URLS_CLEANED)]
        current_proxy_index += 1 # Move to the next proxy for the next request

    try:
        if selected_proxy:
            set_global_proxy_env(selected_proxy) # Set proxy for this request

        # Fetch the transcript for the specified video ID and language, using proxies if configured.
        # The youtube_transcript_api library automatically uses environment variables for proxies.
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
        
        # Initialize an empty string to build the subtitle content.
        subtitle_content = ""

        # Format the subtitle content based on the requested file_format.
        if file_format == 'txt':
            # For TXT, simply concatenate all text.
            for entry in transcript:
                subtitle_content += f"{entry['text']}\n"
            mimetype = "text/plain"
            filename = f"{video_id}_{lang}.txt"
        elif file_format == 'srt':
            # For SRT, format with timestamps and sequence numbers.
            for i, entry in enumerate(transcript):
                start_ms = int(entry['start'] * 1000)
                end_ms = int((entry['start'] + entry['duration']) * 1000)

                # Helper to format milliseconds into HH:MM:SS,MS
                def format_timestamp(ms):
                    hours = ms // 3_600_000
                    ms %= 3_600_000
                    minutes = ms // 60_000
                    ms %= 60_000
                    seconds = ms // 1_000
                    milliseconds = ms % 1_000
                    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

                subtitle_content += f"{i + 1}\n" # Sequence number
                subtitle_content += f"{format_timestamp(start_ms)} --> {format_timestamp(end_ms)}\n"
                subtitle_content += f"{entry['text']}\n\n"
            mimetype = "application/x-subrip" # Standard MIME type for SRT
            filename = f"{video_id}_{lang}.srt"
        else:
            # Handle unsupported formats.
            return jsonify({"success": False, "message": "Unsupported format. Only 'txt' and 'srt' are supported."}), 400

        # Create an in-memory file-like object from the subtitle content.
        buffer = io.BytesIO(subtitle_content.encode('utf-8'))
        
        # Send the file to the client for download.
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
        # --- Ensure proxies are cleared after the request ---
        clear_global_proxy_env()

# --- NEW: Authentication Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already authenticated, redirect them away from login page
    if current_user.is_authenticated:
        flash('You are already logged in!', 'info')
        return redirect(url_for('admin.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))
        login_user(user) # Log in the user
        next_page = request.args.get('next') # Get the URL they were trying to access
        flash(f'Logged in as {user.username}.', 'success')
        return redirect(next_page or url_for('admin.index')) # Redirect to admin or original page

    return render_template('login.html', form=form, title="Login")

@app.route('/logout')
# @login_required # This is not strictly necessary for logout route, as it just clears session.
def logout():
    # If user is not logged in, they can't really "log out", so just redirect.
    if not current_user.is_authenticated:
        flash('You are not currently logged in.', 'info')
        return redirect(url_for('index'))
        
    logout_user() # Log out the user
    flash('You have been logged out.', 'info')
    return redirect(url_for('index')) # Redirect to homepage

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Allow registration only if no users exist. This is a simple way to restrict initial user creation.
    # In a more complex app, you might have an invite system or specific admin registration page.
    if User.query.count() > 0: # If any user exists, disallow public registration
        flash('Registration is currently closed.', 'danger')
        return redirect(url_for('login'))

    if current_user.is_authenticated: # If an admin is already logged in, they shouldn't register
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

# --- NEW: Password Reset Routes ---
def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password Reset Request',
                  sender=app.config['MAIL_DEFAULT_SENDER'],
                  recipients=[user.email])
    # The URL for resetting password will be http://127.0.0.1:5000/reset_password/<token>
    # Make sure this matches your deployed domain later.
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
            flash('There is no account with that email. Please check your email address.', 'danger')
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
# --- END NEW ---


# --- NEW: Blog Frontend Routes (No changes here, just for context) ---
@app.route('/blog')
def blog_list():
    """
    Renders the blog list page, showing all published posts.
    """
    # Order by most recent posts first
    posts = Post.query.filter_by(is_published=True).order_by(Post.date_posted.desc()).all()
    return render_template('blog_list.html', posts=posts, title="Blog")

@app.route('/blog/<slug>')
def blog_post(slug):
    """
    Renders a single blog post by its slug.
    """
    # Retrieve the post by slug, return 404 if not found or not published
    post = Post.query.filter_by(slug=slug, is_published=True).first_or_404()
    return render_template('blog_post.html', title=post.title, post=post)
# --- END NEW ---

# This ensures the Flask development server runs only when the script is executed directly.
if __name__ == '__main__':
    # Create database tables if they don't exist
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
            # REMOVED: login_user(new_admin) - This line was removed to prevent auto-login.


    app.run(debug=True)
