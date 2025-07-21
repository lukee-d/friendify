import os
from dotenv import load_dotenv
from flask import Flask, session, redirect, url_for, request
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Spotify app credentials from environment variables
CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
REDIRECT_URI = 'https://friendify-s2rz.onrender.com/callback'  # Update with your actual deployed URL
SCOPE = 'user-top-read playlist-modify-public playlist-modify-private'

# In-memory store for users' top tracks: {user_id: [track_uris]}
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

    token_info = session['token_info']
    sp = get_spotify_client(token_info['access_token'])

    # Redirect straight to callback to keep logic consistent
    return redirect(url_for('callback', code=token_info['access_token']))


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

    # ✅ Get user's Spotify display name
    profile = sp.current_user()
    display_name = profile.get('display_name', 'Unknown User')
    session['token_info'] = token_info
    session['user_id'] = profile['id']

    # ✅ Get top 5 tracks (with names + artists)
    top_tracks = sp.current_user_top_tracks(limit=5, time_range='short_term')
    track_info = []
    for item in top_tracks['items']:
        name = item['name']
        artists = ', '.join([artist['name'] for artist in item['artists']])
        track_info.append(item['uri'])  # Save URI for playlist creation

    # ✅ Save using display name
    user_top_tracks[display_name] = track_info

    return f"Hello {display_name}! Your top 5 tracks have been saved."




@app.route('/create_playlist')
def create_playlist():
    if 'token_info' not in session or 'user_id' not in session:
        return redirect(url_for('login'))

    token_info = session['token_info']
    sp = get_spotify_client(token_info['access_token'])
    user_id = session['user_id']

    # Combine all users' saved tracks, remove duplicates
    combined_tracks = list({track for tracks in user_top_tracks.values() for track in tracks})

    # Create playlist in the current user's account
    playlist = sp.user_playlist_create(user=user_id, name="Combined Top Tracks Playlist")

    # Add tracks in batches of 100 (Spotify limit)
    for i in range(0, len(combined_tracks), 100):
        sp.playlist_add_items(playlist_id=playlist['id'], items=combined_tracks[i:i+100])

    return f"Combined playlist created! Listen here: {playlist['external_urls']['spotify']}"

@app.route('/saved_tracks')
def saved_tracks():
    output = "Saved Users' Top Tracks:\n"
    for user, tracks in user_top_tracks.items():
        output += f"\nUser: {user}\n"
        for track in tracks:
            output += track + "\n"
    return f"<pre>{output}</pre>"




if __name__ == '__main__':
    app.run(debug=True)
