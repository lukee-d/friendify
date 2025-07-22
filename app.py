import os
from flask import Flask, redirect, request, url_for, session, jsonify  # add session to imports
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or 'dev_secret_key'

# Use SQLite for local file-based database (avoid psycopg issues)
db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'app.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Spotify OAuth Configuration
SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.environ.get("SPOTIPY_REDIRECT_URI", "https://friendify-s2rz.onrender.com/callback")
SCOPE = "user-top-read"

sp_oauth = SpotifyOAuth(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET,
    redirect_uri=SPOTIPY_REDIRECT_URI,
    scope=SCOPE
)

# Database Model
class UserTracks(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), unique=True, nullable=False)
    display_name = db.Column(db.String(100))
    tracks = db.Column(db.JSON)

# Create tables (this runs automatically on first deploy)
with app.app_context():
    db.create_all()

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return f"""
            Logged in as {session.get('display_name', session['user_id'])}<br>
            <a href='/my_tracks'>View My Tracks</a><br>
            <a href='/saved_tracks'>View All Friends' Tracks</a><br>
            <a href='/logout'>Log out</a>
        """
    else:
        return "<a href='/login'>Log in with Spotify</a>"

@app.route('/login')
def login():
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "Error: No authorization code received", 400

    try:
        token_info = sp_oauth.get_access_token(code)
        sp = spotipy.Spotify(auth=token_info['access_token'])
        user = sp.current_user()
        user_id = user['id']
        display_name = user.get('display_name', user_id)

        # Store user info in session
        session['user_id'] = user_id
        session['display_name'] = display_name

        # Get top tracks
        results = sp.current_user_top_tracks(limit=5, time_range='short_term')
        track_info = [{
            'name': item['name'],
            'artists': ', '.join(artist['name'] for artist in item['artists']),
            'image': item['album']['images'][0]['url'] if item['album']['images'] else None
        } for item in results['items']]

        # Save to database
        user_record = UserTracks.query.filter_by(user_id=user_id).first()
        if user_record:
            user_record.tracks = track_info
            user_record.display_name = display_name
        else:
            user_record = UserTracks(
                user_id=user_id,
                display_name=display_name,
                tracks=track_info
            )
            db.session.add(user_record)
        db.session.commit()

        return redirect(url_for('index'))

    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/my_tracks')
def my_tracks():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))
    user = UserTracks.query.filter_by(user_id=user_id).first()
    if not user:
        return "No tracks found for your account."
    html = f"<h2>Your Top Tracks, {user.display_name}:</h2><ul>"
    for track in user.tracks:
        html += "<li>"
        html += f"<strong>{track['name']}</strong> by {track['artists']}<br>"
        if track['image']:
            html += f"<img src='{track['image']}' style='height:100px;'><br>"
        html += "</li>"
    html += "</ul><a href='/'>Back to Home</a>"
    return html

@app.route('/saved_tracks')
def saved_tracks():
    try:
        users = UserTracks.query.all()
        if not users:
            return "No users have saved tracks yet."

        html = "<h2>All Friends' Top Tracks:</h2>"
        for user in users:
            html += f"<h3>{user.display_name}</h3><ul>"
            for track in user.tracks:
                html += "<li>"
                html += f"<strong>{track['name']}</strong> by {track['artists']}<br>"
                if track['image']:
                    html += f"<img src='{track['image']}' style='height:100px;'><br>"
                html += "</li>"
            html += "</ul><hr>"
        return html

    except Exception as e:
        return f"Database error: {str(e)}", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
