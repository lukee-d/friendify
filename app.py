import os
from dotenv import load_dotenv
from flask import Flask, session, redirect, url_for, request
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
REDIRECT_URI = 'https://friendify-s2rz.onrender.com/callback'
SCOPE = 'user-top-read playlist-modify-public playlist-modify-private'

# {display_name: {"uris": [...], "info": [...]}}
user_top_tracks = {}

def get_spotify_oauth():
    return SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        cache_path=None
    )

def get_spotify_client(token):
    return Spotify(auth=token)

@app.route('/')
def index():
    if 'token_info' not in session:
        return redirect(url_for('login'))
    return "You're logged in! Go to <a href='/saved_tracks'>/saved_tracks</a> or <a href='/create_playlist'>/create_playlist</a>"

@app.route('/login')
def login():
    sp_oauth = get_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_info = get_spotify_oauth().get_access_token(code)
    access_token = token_info['access_token']

    sp = Spotify(auth=access_token)
    profile = sp.current_user()
    display_name = profile.get('display_name', 'Unknown User')
    session['token_info'] = token_info
    session['user_id'] = profile['id']

    top_tracks = sp.current_user_top_tracks(limit=5, time_range='short_term')
    uris = []
    info = []

    for item in top_tracks['items']:
        uri = item['uri']
        name = item['name']
        artists = ', '.join([artist['name'] for artist in item['artists']])
        uris.append(uri)
        info.append(f"{name} by {artists}")

    user_top_tracks[display_name] = {
        "uris": uris,
        "info": info
    }

    return f"Hello {display_name}! Your top 5 tracks have been saved."

@app.route('/create_playlist')
def create_playlist():
    if 'token_info' not in session or 'user_id' not in session:
        return redirect(url_for('login'))

    token_info = session['token_info']
    sp = get_spotify_client(token_info['access_token'])
    user_id = session['user_id']

    # Combine all users' URIs
    combined_uris = list({uri for user_data in user_top_tracks.values() for uri in user_data['uris']})

    playlist = sp.user_playlist_create(user=user_id, name="Combined Top Tracks Playlist")

    for i in range(0, len(combined_uris), 100):
        sp.playlist_add_items(playlist_id=playlist['id'], items=combined_uris[i:i+100])

    return f"Combined playlist created! <a href='{playlist['external_urls']['spotify']}'>Listen here</a>"

@app.route('/saved_tracks')
def saved_tracks():
    output = "<h2>Saved Users' Top Tracks</h2>"
    for user, data in user_top_tracks.items():
        output += f"<h3>{user}</h3><ul>"
        for track in data['info']:
            output += f"<li>{track}</li>"
        output += "</ul>"
    return output

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
