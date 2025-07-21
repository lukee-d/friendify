import os
from dotenv import load_dotenv
from flask import Flask, session, redirect, url_for, request
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Spotify credentials
CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
REDIRECT_URI = 'https://friendify-s2rz.onrender.com/callback'
SCOPE = 'user-top-read playlist-modify-public playlist-modify-private'

# Store top tracks: {username: [{name, artists, uri, image_url}]}
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
    return "You're logged in! Go to /saved_tracks or /create_playlist"

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

    track_info = []
    for item in top_tracks['items']:
        name = item['name']
        artists = ', '.join([artist['name'] for artist in item['artists']])
        uri = item['uri']
        image_url = item['album']['images'][0]['url'] if item['album']['images'] else ''
        track_info.append({'name': name, 'artists': artists, 'uri': uri, 'image': image_url})

    user_top_tracks[display_name] = track_info

    return f"Hello {display_name}! Your top 5 tracks have been saved."

@app.route('/saved_tracks')
def saved_tracks():
    html = "<h2>Saved Users' Top Tracks</h2>"
    for user, tracks in user_top_tracks.items():
        html += f"<h3>{user}</h3><ul>"
        for track in tracks:
            html += "<li>"
            html += f"<strong>{track['name']}</strong> by {track['artists']}<br>"
            if track['image']:
                html += f"<img src='{track['image']}' alt='Album Art' style='height:100px;'><br>"
            html += "</li>"
        html += "</ul><hr>"
    return html

@app.route('/create_playlist')
def create_playlist():
    if 'token_info' not in session or 'user_id' not in session:
        return redirect(url_for('login'))

    token_info = session['token_info']
    sp = get_spotify_client(token_info['access_token'])
    user_id = session['user_id']

    # Combine unique URIs
    combined_tracks = list({
        track['uri']
        for tracks in user_top_tracks.values()
        for track in tracks
    })

    playlist = sp.user_playlist_create(user=user_id, name="Combined Top Tracks Playlist")

    for i in range(0, len(combined_tracks), 100):
        sp.playlist_add_items(playlist_id=playlist['id'], items=combined_tracks[i:i+100])

    return f"Combined playlist created! Listen here: {playlist['external_urls']['spotify']}"

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
