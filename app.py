from flask import Flask, redirect, request, url_for, session
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
import psycopg
import sqlalchemy.dialects.postgresql.psycopg

print("psycopg version:", psycopg.__version__)

load_dotenv()

# Flask setup
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")

# PostgreSQL setup (Render provides DATABASE_URL)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace(
    "postgres://", "postgresql+psycopg://", 1
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # Helps with Render's connection recycling
    'pool_recycle': 300,    # 5 minutes (Render kills idle connections)
}
db = SQLAlchemy(app)

# Spotify OAuth setup
SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = "https://friendify-s2rz.onrender.com/callback"
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
    user_id = db.Column(db.String(50), unique=True)
    display_name = db.Column(db.String(100))
    tracks = db.Column(db.JSON)  # Stores track data as JSON

# Create tables (run once)
with app.app_context():
    db.create_all()

# Routes
@app.route('/')
def index():
    return "<a href='/login'>Log in with Spotify</a>"

@app.route('/login')
def login():
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)

    sp = spotipy.Spotify(auth=token_info['access_token'])
    user = sp.current_user()
    user_id = user['id']
    display_name = user.get('display_name', user_id)

    # Fetch top 5 tracks
    results = sp.current_user_top_tracks(limit=5, time_range='short_term')
    track_info = []
    for item in results['items']:
        track_info.append({
            'name': item['name'],
            'artists': ', '.join([artist['name'] for artist in item['artists']]),
            'image': item['album']['images'][0]['url'] if item['album']['images'] else None
        })

    # Save to PostgreSQL
    user = UserTracks.query.filter_by(user_id=user_id).first()
    if user:
        user.tracks = track_info
        user.display_name = display_name
    else:
        user = UserTracks(user_id=user_id, display_name=display_name, tracks=track_info)
        db.session.add(user)
    db.session.commit()

    return f"""
        Hello {display_name}! Your top 5 tracks have been saved.
        <br><a href='/saved_tracks'>View All Friends' Tracks</a>
    """

@app.route('/saved_tracks')
def saved_tracks():
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)