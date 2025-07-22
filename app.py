import os
from flask import Flask, redirect, request, url_for, session, jsonify  # add session to imports
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import random

load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or 'dev_secret_key'

app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True  # Set to False if testing locally without HTTPS

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
            <a href='/game'>Play the Guessing Game</a><br>
            <a href='/logout'>Log out</a>
        """
    else:
        return "<a href='/login'>Log in with Spotify</a>"

@app.route('/login')
def login():
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope=SCOPE,
        cache_path=None
    )
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@app.route('/callback')
def callback():
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope=SCOPE,
        cache_path=None
    )
    code = request.args.get('code')
    if not code:
        return "Error: No authorization code received", 400

    try:
        token_info = sp_oauth.get_access_token(code, check_cache=False)
        print("Access token:", token_info['access_token'])  # <-- Add this line
        sp = spotipy.Spotify(auth=token_info['access_token'])
        user = sp.current_user()
        print("Spotify user info:", user)  # <-- This will show up in Render logs!
        user_id = user['id']
        display_name = user.get('display_name', user_id)

        # Store user info in session
        session['user_id'] = user_id
        session['display_name'] = display_name

        # Get top tracks
        results = sp.current_user_top_tracks(limit=20, time_range='short_term')
        track_info = [{
            'name': item['name'],
            'artists': ', '.join(artist['name'] for artist in item['artists']),
            'image': item['album']['images'][0]['url'] if item['album']['images'] else None,
            'preview_url': item.get('preview_url')  # For audio preview in game
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
    spotify_logout_url = "https://accounts.spotify.com/logout"
    return redirect(f"{spotify_logout_url}?continue={url_for('index', _external=True)}")

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

@app.route('/game')
def game():
    users = UserTracks.query.all()
    if not users:
        return "No users have saved tracks yet."

    # Build a pool: each entry is (track, [user_display_names])
    track_pool = {}
    all_usernames = [user.display_name for user in users]
    for user in users:
        for track in user.tracks:
            key = (track['name'], track['artists'])
            if key not in track_pool:
                track_pool[key] = {'track': track, 'owners': []}
            track_pool[key]['owners'].append(user.display_name)

    # Pick 10 random tracks for the game
    all_tracks = list(track_pool.values())
    rounds = min(10, len(all_tracks))
    selected_tracks = random.sample(all_tracks, rounds)

    html = "<h2>Guess Whose Song!</h2>"
    html += "<ol>"
    for i, entry in enumerate(selected_tracks, 1):
        track = entry['track']
        owners = entry['owners']
        html += f"<li>"
        html += f"<strong>{track['name']}</strong> by {track['artists']}<br>"
        if track.get('image'):
            html += f"<img src='{track['image']}' style='height:100px;'><br>"
        if track.get('preview_url'):
            html += f"<audio controls src='{track['preview_url']}'></audio><br>"
        html += f"<form method='post' action='/game/guess'><input type='hidden' name='track' value='{track['name']}|{track['artists']}'>"
        for username in all_usernames:
            html += f"<button type='submit' name='guess' value='{username}'>{username}</button> "
        html += f"<input type='hidden' name='owners' value='{','.join(owners)}'>"
        html += "</form>"
        html += "</li>"
    html += "</ol>"
    html += "<a href='/'>Back to Home</a>"
    return html

@app.route('/game/guess', methods=['POST'])
def game_guess():
    track = request.form.get('track')
    guess = request.form.get('guess')
    owners = request.form.get('owners', '').split(',')

    if guess in owners:
        result = f"✅ Correct! {guess} has this song in their top tracks."
    else:
        result = f"❌ Wrong! Correct answer(s): {', '.join(owners)}"

    html = f"<h2>{result}</h2>"
    html += "<a href='/game'>Play Again</a> | <a href='/'>Back to Home</a>"
    return html

@app.route('/admin/clear_users')
def clear_users():
    try:
        num_deleted = UserTracks.query.delete()
        db.session.commit()
        return f"Deleted {num_deleted} users from the database."
    except Exception as e:
        return f"Error: {str(e)}", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
