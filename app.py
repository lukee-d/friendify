from flask import Flask, request, redirect, session, url_for
import spotipy
from spotipy.oauth2 import SpotifyOAuth

app = Flask(__name__)
app.secret_key = 'supersneakylukekey'  # Change this!

CLIENT_ID = '5794dafbd677419b96cec1425c518a47'
CLIENT_SECRET = 'f11d64e15c1049628a6e31d375ebb2a1'
REDIRECT_URI = 'https://friendify-s2rz.onrender.com/callback'  # update after ngrok setup
SCOPE = 'user-top-read playlist-modify-private'

# Initialize Spotify OAuth object (no caching here for simplicity)
sp_oauth = SpotifyOAuth(client_id=CLIENT_ID,
                        client_secret=CLIENT_SECRET,
                        redirect_uri=REDIRECT_URI,
                        scope=SCOPE,
                        cache_path=".cache")

@app.route('/')
def index():
    if 'token_info' in session:
        return 'Logged in! <a href="/top-tracks">See Top Tracks</a>'
    else:
        auth_url = sp_oauth.get_authorize_url()
        return f'<a href="{auth_url}">Log in with Spotify</a>'

@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session['token_info'] = token_info
    return redirect(url_for('index'))

@app.route('/top-tracks')
def top_tracks():
    token_info = session.get('token_info', None)
    if not token_info:
        return redirect(url_for('index'))

    sp = spotipy.Spotify(auth=token_info['access_token'])
    results = sp.current_user_top_tracks(limit=5)
    tracks = [f"{t['name']} by {t['artists'][0]['name']}" for t in results['items']]
    return '<br>'.join(tracks)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
