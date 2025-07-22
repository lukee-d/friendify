import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")

# Get and clean up the database URL
raw_db_url = os.environ.get("DATABASE_URL")
if raw_db_url is None:
    raise ValueError("DATABASE_URL is not set in environment variables.")

# Ensure compatibility with psycopg3
db_url = raw_db_url.replace("postgres://", "postgresql+psycopg://", 1)

# Set any needed SQLAlchemy options
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Create the SQLAlchemy engine explicitly with psycopg3
engine = create_engine(db_url, pool_pre_ping=True, future=True)

# Setup the scoped session
db_session = scoped_session(sessionmaker(bind=engine, autoflush=False))

# Initialize the SQLAlchemy ORM
db = SQLAlchemy()
db.init_app(app)




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