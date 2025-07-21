from flask import Flask, redirect, request, session, url_for
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import json
import os
from dotenv import load_dotenv
load_dotenv()

SPOTIPY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI")



app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")

# Spotify OAuth setup
SPOTIPY_CLIENT_ID = "your_client_id"
SPOTIPY_CLIENT_SECRET = "your_client_secret"
SPOTIPY_REDIRECT_URI = "http://localhost:5000/callback"
SCOPE = "user-top-read"

sp_oauth = SpotifyOAuth(client_id=SPOTIPY_CLIENT_ID,
                        client_secret=SPOTIPY_CLIENT_SECRET,
                        redirect_uri=SPOTIPY_REDIRECT_URI,
                        scope=SCOPE)

DATA_FILE = "data.json"

# Save a user's top tracks to JSON
def save_user_tracks(user_id, display_name, track_info):
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
    else:
        data = {}

    data[user_id] = {
        'display_name': display_name,
        'tracks': track_info
    }

    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# Helper to get a Spotify client
def get_spotify_client(token):
    return spotipy.Spotify(auth=token)

@app.route('/')
def index():
    if 'token_info' not in session:
        return redirect(url_for('login'))

    token_info = session['token_info']
    sp = get_spotify_client(token_info['access_token'])
    user = sp.current_user()
    user_id = user['id']
    display_name = user.get('display_name', user_id)

    # Get top 5 tracks
    results = sp.current_user_top_tracks(limit=5, time_range='short_term')
    track_info = []
    for item in results['items']:
        track_info.append({
            'name': item['name'],
            'artists': ', '.join([artist['name'] for artist in item['artists']]),
            'image': item['album']['images'][0]['url'] if item['album']['images'] else None
        })

    save_user_tracks(user_id, display_name, track_info)

    return f"Hello {display_name}! Your top 5 tracks have been saved.<br><a href='/saved_tracks'>View All Saved Tracks</a>"

@app.route('/login')
def login():
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session['token_info'] = token_info
    return redirect(url_for('index'))

@app.route('/saved_tracks')
def saved_tracks():
    if not os.path.exists(DATA_FILE):
        return "No users have saved tracks yet."

    with open(DATA_FILE, 'r') as f:
        data = json.load(f)

    html = "<h2>Saved Users' Top Tracks:</h2>"
    for user_id, user_data in data.items():
        html += f"<h3>{user_data['display_name']}</h3><ul>"
        for track in user_data['tracks']:
            html += "<li>"
            html += f"<strong>{track['name']}</strong> by {track['artists']}<br>"
            if track['image']:
                html += f"<img src='{track['image']}' style='height:100px;'><br>"
            html += "</li>"
        html += "</ul><hr>"

    return html

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))

