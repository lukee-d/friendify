import os
from flask import Flask, redirect, request, url_for, session, jsonify  # add session to imports
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import random
import string

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

# Database Models
class UserTracks(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), unique=True, nullable=False)
    display_name = db.Column(db.String(100))
    tracks = db.Column(db.JSON)

class Lobby(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(8), unique=True, nullable=False)
    state = db.Column(db.JSON)  # Store game state, track pool, round, etc.

class LobbyMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lobby_id = db.Column(db.Integer, db.ForeignKey('lobby.id'))
    user_id = db.Column(db.String(50))
    display_name = db.Column(db.String(100))

# Create tables (this runs automatically on first deploy)
with app.app_context():
    db.create_all()

# Helper Functions
def generate_lobby_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return f"""
            Logged in as {session.get('display_name', session['user_id'])}<br>
            <a href='/my_tracks'>View My Tracks</a><br>
            <a href='/saved_tracks'>View All Friends' Tracks</a><br>
            <a href='/game/start'>Play the Guessing Game (Solo)</a><br>
            <a href='/lobby/create'>Create Multiplayer Lobby</a><br>
            <a href='/lobby/join'>Join Multiplayer Lobby</a><br>
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
        # Prompt user to re-save tracks
        return """
            <h2>No tracks found for your account.</h2>
            <a href='/login'>Click here to re-save your tracks from Spotify</a>
            <br><a href='/'>Back to Home</a>
        """
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
    return redirect(url_for('game_start'))

@app.route('/game/guess', methods=['POST'])
def game_guess():
    guess = request.form.get('guess')
    owners = request.form.get('owners', '').split(',')

    game_round = session.get('game_round', 0)
    game_score = session.get('game_score', 0)

    if guess in owners:
        result = f"✅ Correct! {guess} has this song in their top tracks."
        game_score += 1
    else:
        result = f"❌ Wrong! Correct answer(s): {', '.join(owners)}"

    session['game_score'] = game_score
    session['game_round'] = game_round + 1

    html = f"<h2>{result}</h2>"
    html += f"<a href='{url_for('game_round')}'>Next Round</a> | <a href='/'>Back to Home</a>"
    return html

@app.route('/admin/clear_users')
def clear_users():
    try:
        num_deleted = UserTracks.query.delete()
        db.session.commit()
        return f"Deleted {num_deleted} users from the database."
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/game/start')
def game_start():
    users = UserTracks.query.all()
    if not users:
        return "No users have saved tracks yet."

    # Build track pool
    track_pool = {}
    all_usernames = [user.display_name for user in users]
    for user in users:
        for track in user.tracks:
            key = (track['name'], track['artists'])
            if key not in track_pool:
                track_pool[key] = {'track': track, 'owners': []}
            track_pool[key]['owners'].append(user.display_name)

    all_tracks = list(track_pool.values())
    rounds = min(10, len(all_tracks))
    selected_tracks = random.sample(all_tracks, rounds)

    # Store game state in session
    session['game_tracks'] = selected_tracks
    session['game_round'] = 0
    session['game_score'] = 0

    return redirect(url_for('game_round'))

@app.route('/game/round')
def game_round():
    game_tracks = session.get('game_tracks')
    game_round = session.get('game_round', 0)
    game_score = session.get('game_score', 0)

    if not game_tracks or game_round >= len(game_tracks):
        return redirect(url_for('game_end'))

    entry = game_tracks[game_round]
    track = entry['track']
    owners = entry['owners']
    all_usernames = set()
    for e in game_tracks:
        all_usernames.update(e['owners'])

    html = f"<h2>Round {game_round + 1}</h2>"
    html += f"<strong>{track['name']}</strong> by {track['artists']}<br>"
    if track.get('image'):
        html += f"<img src='{track['image']}' style='height:100px;'><br>"
    if track.get('preview_url'):
        html += f"<audio controls src='{track['preview_url']}'></audio><br>"
    html += f"<form method='post' action='/game/guess'><input type='hidden' name='owners' value='{','.join(owners)}'>"
    for username in all_usernames:
        html += f"<button type='submit' name='guess' value='{username}'>{username}</button> "
    html += "</form>"
    html += f"<br>Score: {game_score}/{game_round}"
    return html

@app.route('/game/end')
def game_end():
    score = session.get('game_score', 0)
    total = len(session.get('game_tracks', []))
    html = f"<h2>Game Over!</h2><p>Your score: {score} / {total}</p>"
    html += "<a href='/game/start'>Play Again</a> | <a href='/'>Back to Home</a>"
    # Optionally clear session state
    session.pop('game_tracks', None)
    session.pop('game_round', None)
    session.pop('game_score', None)
    return html

@app.route('/lobby/create')
def lobby_create():
    # Only allow if logged in
    if 'user_id' not in session:
        return redirect(url_for('login'))
    code = generate_lobby_code()
    lobby = Lobby(code=code, state={})
    db.session.add(lobby)
    db.session.commit()
    # Add creator as member
    member = LobbyMember(lobby_id=lobby.id, user_id=session['user_id'], display_name=session['display_name'])
    db.session.add(member)
    db.session.commit()
    return redirect(url_for('lobby_view', code=code))

@app.route('/lobby/join', methods=['GET', 'POST'])
def lobby_join():
    if request.method == 'POST':
        code = request.form.get('code', '').upper()
        lobby = Lobby.query.filter_by(code=code).first()
        if not lobby:
            return "Lobby not found. <a href='/lobby/join'>Try again</a>"
        # Add user as member if not already
        if 'user_id' not in session:
            return redirect(url_for('login'))
        existing = LobbyMember.query.filter_by(lobby_id=lobby.id, user_id=session['user_id']).first()
        if not existing:
            member = LobbyMember(lobby_id=lobby.id, user_id=session['user_id'], display_name=session['display_name'])
            db.session.add(member)
            db.session.commit()
        return redirect(url_for('lobby_view', code=code))
    return '''
        <form method="post">
            Enter Lobby Code: <input name="code" maxlength="8">
            <button type="submit">Join</button>
        </form>
        <a href="/">Back to Home</a>
    '''

@app.route('/lobby/<code>')
def lobby_view(code):
    lobby = Lobby.query.filter_by(code=code).first()
    if not lobby:
        return "Lobby not found."
    members = LobbyMember.query.filter_by(lobby_id=lobby.id).all()
    html = f"<h2>Lobby {code}</h2>"
    html += "<ul>"
    for m in members:
        html += f"<li>{m.display_name}</li>"
    html += "</ul>"
    html += f"<a href='/lobby/{code}/start'>Start Game</a><br>"
    html += "<a href='/'>Back to Home</a>"
    return html

@app.route('/lobby/<code>/start')
def lobby_start(code):
    lobby = Lobby.query.filter_by(code=code).first()
    if not lobby:
        return "Lobby not found."
    members = LobbyMember.query.filter_by(lobby_id=lobby.id).all()
    user_ids = [m.user_id for m in members]
    users = UserTracks.query.filter(UserTracks.user_id.in_(user_ids)).all()
    # Pool tracks
    track_pool = {}
    all_usernames = [u.display_name for u in users]
    for user in users:
        for track in user.tracks:
            key = (track['name'], track['artists'])
            if key not in track_pool:
                track_pool[key] = {'track': track, 'owners': []}
            track_pool[key]['owners'].append(user.display_name)
    all_tracks = list(track_pool.values())
    rounds = min(10, len(all_tracks))
    selected_tracks = random.sample(all_tracks, rounds)
    # Store in lobby state
    lobby.state = {
        'tracks': selected_tracks,
        'round': 0,
        'scores': {m.user_id: 0 for m in members}
    }
    db.session.commit()
    session['lobby_code'] = code
    session['lobby_round'] = 0
    return redirect(url_for('lobby_game_round', code=code))

@app.route('/lobby/<code>/round')
def lobby_game_round(code):
    lobby = Lobby.query.filter_by(code=code).first()
    if not lobby or not lobby.state:
        return "Lobby/game not found."
    state = lobby.state
    round_num = state.get('round', 0)
    tracks = state.get('tracks', [])
    if round_num >= len(tracks):
        return redirect(url_for('lobby_game_end', code=code))
    entry = tracks[round_num]
    track = entry['track']
    owners = entry['owners']
    all_usernames = set()
    for e in tracks:
        all_usernames.update(e['owners'])
    html = f"<h2>Lobby {code} - Round {round_num + 1}</h2>"
    html += f"<strong>{track['name']}</strong> by {track['artists']}<br>"
    if track.get('image'):
        html += f"<img src='{track['image']}' style='height:100px;'><br>"
    if track.get('preview_url'):
        html += f"<audio controls src='{track['preview_url']}'></audio><br>"
    html += f"<form method='post' action='/lobby/{code}/guess'><input type='hidden' name='owners' value='{','.join(owners)}'>"
    for username in all_usernames:
        html += f"<button type='submit' name='guess' value='{username}'>{username}</button> "
    html += "</form>"
    return html

@app.route('/lobby/<code>/guess', methods=['POST'])
def lobby_game_guess(code):
    lobby = Lobby.query.filter_by(code=code).first()
    if not lobby or not lobby.state:
        return "Lobby/game not found."
    state = lobby.state
    round_num = state.get('round', 0)
    tracks = state.get('tracks', [])
    owners = request.form.get('owners', '').split(',')
    guess = request.form.get('guess')
    user_id = session.get('user_id')
    # Score for this user
    if user_id and guess in owners:
        state['scores'][user_id] = state['scores'].get(user_id, 0) + 1
    # Advance round
    state['round'] = round_num + 1
    lobby.state = state
    db.session.commit()
    html = f"<h2>{'✅ Correct!' if guess in owners else '❌ Wrong!'} Correct answer(s): {', '.join(owners)}</h2>"
    html += f"<a href='{url_for('lobby_game_round', code=code)}'>Next Round</a> | <a href='/'>Back to Home</a>"
    return html

@app.route('/lobby/<code>/end')
def lobby_game_end(code):
    lobby = Lobby.query.filter_by(code=code).first()
    if not lobby or not lobby.state:
        return "Lobby/game not found."
    state = lobby.state
    scores = state.get('scores', {})
    members = LobbyMember.query.filter_by(lobby_id=lobby.id).all()
    html = f"<h2>Lobby {code} - Game Over!</h2><ul>"
    for m in members:
        html += f"<li>{m.display_name}: {scores.get(m.user_id, 0)}</li>"
    html += "</ul>"
    html += f"<a href='/lobby/{code}/start'>Play Again</a> | <a href='/'>Back to Home</a>"
    return html
