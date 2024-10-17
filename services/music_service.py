import os
import logging
import sqlite3
from datetime import datetime
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import youtube_dl
import matplotlib.pyplot as plt
import seaborn as sns
from discord.ext import commands

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Verify Spotify environment variables
client_id = os.getenv('SPOTIFY_CLIENT_ID')
client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
if not client_id or not client_secret:
    logging.error("Spotify client ID und secret müssen in den Umgebungsvariablen gesetzt sein.")
else:
    logging.info("Spotify client ID und secret erfolgreich geladen.")


class Track:
    """
    A class representing a music track with its metadata.
    """

    def __init__(self, track_data: dict, audio_features: dict):
        logging.debug(f"Creating Track object for '{track_data['name']}' with ID '{track_data['id']}'")
        self.id = track_data['id']
        self.name = track_data['name']
        self.artist = ', '.join(artist['name'] for artist in track_data['artists'])
        self.album = track_data['album']['name']
        self.release_date = track_data['album']['release_date']
        self.uri = track_data['uri']
        self.duration = track_data['duration_ms']
        self.popularity = track_data['popularity']
        self.danceability = audio_features.get('danceability', 0)
        self.energy = audio_features.get('energy', 0)
        self.tempo = audio_features.get('tempo', 0)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "artist": self.artist,
            "album": self.album,
            "release_date": self.release_date,
            "uri": self.uri,
            "duration": self.duration,
            "popularity": self.popularity,
            "danceability": self.danceability,
            "energy": self.energy,
            "tempo": self.tempo
        }

    def __repr__(self):
        return f"Track(id={self.id}, name={self.name}, artist={self.artist}, album={self.album}, release_date={self.release_date}, uri={self.uri})"


class DatabaseManager:
    """
    A class to manage interactions with the SQLite database for track history.
    """

    def __init__(self, db_path='history.db'):
        self.db_path = db_path
        self.connection = self.connect_to_db()
        self.create_table()

    def connect_to_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            logging.info(f"Connected to database at {self.db_path}")
            return conn
        except sqlite3.Error as e:
            logging.error(f"Error connecting to database: {e}")
            return None

    def create_table(self):
        try:
            with self.connection:
                self.connection.execute('''
                    CREATE TABLE IF NOT EXISTS track_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT,
                        artist TEXT,
                        album TEXT,
                        release_date TEXT,
                        playlist_uri TEXT,
                        user_name TEXT,
                        on_spotify INTEGER,
                        count INTEGER DEFAULT 1,
                        timestamp DATETIME,
                        manual_addition INTEGER DEFAULT 0
                    )
                ''')
                logging.info("Table 'track_history' ensured in database.")
        except sqlite3.Error as e:
            logging.error(f"Error creating table: {e}")

    def save_track(self, track: Track, user_name: str, on_spotify: bool, timestamp: datetime,
                   manual_addition: bool = False):
        try:
            with self.connection:
                cursor = self.connection.cursor()
                cursor.execute('''
                    SELECT count FROM track_history
                    WHERE title = ? AND artist = ?
                ''', (track.name, track.artist))
                result = cursor.fetchone()

                if result:
                    logging.info(f"Track '{track.name}' by '{track.artist}' already in database. Skipping addition.")
                else:
                    cursor.execute('''
                        INSERT INTO track_history
                        (title, artist, album, release_date, playlist_uri, user_name, on_spotify, count, timestamp, manual_addition)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    ''', (track.name, track.artist, track.album, track.release_date, track.uri, user_name, on_spotify,
                          timestamp, int(manual_addition)))

                self.connection.commit()
                logging.info(f"Track '{track.name}' by '{track.artist}' saved to database.")
        except sqlite3.Error as e:
            logging.error(f"Error saving track to database: {e}")

    def get_most_requested_tracks(self):
        logging.info("Fetching most requested tracks.")
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT title, artist, SUM(count) as total_count
            FROM track_history
            GROUP BY title, artist
            ORDER BY total_count DESC
            LIMIT 10
        ''')
        return cursor.fetchall()

    def get_top_artists(self):
        logging.info("Fetching top artists.")
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT artist, SUM(count) as total_count
            FROM track_history
            WHERE on_spotify = 1
            GROUP BY artist
            ORDER BY total_count DESC
            LIMIT 10
        ''')
        return cursor.fetchall()

    def get_search_success_stats(self):
        logging.info("Fetching search success stats.")
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT
                SUM(CASE WHEN on_spotify = 1 THEN 1 ELSE 0 END) AS successful,
                SUM(CASE WHEN on_spotify = 0 THEN 1 ELSE 0 END) AS unsuccessful
            FROM track_history
        ''')
        return cursor.fetchone()

    def get_user_activity_stats(self):
        logging.info("Fetching user activity stats.")
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT user_name, SUM(count) as total_count
            FROM track_history
            GROUP BY user_name
            ORDER BY total_count DESC
            LIMIT 10
        ''')
        return cursor.fetchall()

    def generate_activity_heatmap(self):
        logging.info("Generating activity heatmap.")
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT strftime('%Y-%m-%d', timestamp) as date, COUNT(*) as count
            FROM track_history
            GROUP BY date
        ''')
        data = cursor.fetchall()

        if data:
            dates, counts = zip(*data)
            fig, ax = plt.subplots(figsize=(10, 6))
            sns.heatmap(
                [counts],
                cmap='Blues',
                annot=True,
                xticklabels=dates,
                yticklabels=['Activity'],
                cbar=False,
                ax=ax
            )
            ax.set_xlabel('Date')
            ax.set_ylabel('Activity')
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.savefig('activity_heatmap.png')
            logging.info("Activity heatmap generated and saved as 'activity_heatmap.png'.")


class MusicService(commands.Cog):
    """
    A class that wraps the Spotify and YouTube music services as a Discord bot cog.
    """

    def __init__(self, bot):
        self.bot = bot
        self.sp = None  # Spotify client will be initialized if credentials are available
        if client_id and client_secret:
            self.sp = spotipy.Spotify(
                auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))

        self.ytdl = youtube_dl.YoutubeDL({
            'quiet': True,
            'noplaylist': True,
            'format': 'bestaudio/best',
        })
        self.db_manager = DatabaseManager()

    @commands.command(name='youtube_to_spotify')
    async def youtube_to_spotify(self, ctx, youtube_url: str):
        user_name = ctx.author.name
        timestamp = datetime.now()
        track = self.check_youtube_in_spotify(youtube_url, user_name, timestamp)
        if track:
            await ctx.send(f"Track '{track.name}' by {track.artist} found on Spotify!")
        else:
            await ctx.send("Track not found on Spotify.")

    def check_youtube_in_spotify(self, youtube_url, user_name, timestamp):
        title, artist = self.extract_info_from_youtube(youtube_url)
        return self.find_on_spotify(title, artist, user_name, timestamp)

    def extract_info_from_youtube(self, youtube_url):
        try:
            logging.info(f"Extracting info from YouTube URL: {youtube_url}")
            info = self.ytdl.extract_info(youtube_url, download=False)
            title = info.get('title')
            artist = info.get('uploader')
            return title, artist
        except Exception as e:
            logging.error(f"Error extracting info from YouTube: {e}")
            return None, None

    def find_on_spotify(self, title, artist, user_name, timestamp):
        if not title or not artist:
            logging.error("Invalid title or artist information.")
            return False

        query = f"{title} {artist}"
        try:
            logging.info(f"Searching Spotify for: {query}")
            results = self.sp.search(q=query, type='track', limit=1)
            tracks = results.get('tracks', {}).get('items')
            if tracks:
                track_data = tracks[0]
                audio_features = self.sp.audio_features(track_data['id'])[0]
                logging.info("Found matching track on Spotify.")
                track = Track(track_data, audio_features)
                self.db_manager.save_track(track, user_name, on_spotify=True, timestamp=timestamp)
                return track
            else:
                logging.info("No matching track found on Spotify.")
                dummy_track = Track({'id': None, 'name': title, 'artists': [{'name': artist}],
                                     'album': {'name': '', 'release_date': ''}, 'uri': None, 'duration_ms': 0,
                                     'popularity': 0}, {})
                self.db_manager.save_track(dummy_track, user_name, on_spotify=False, timestamp=timestamp)
                return False
        except Exception as e:
            logging.error(f"Error searching Spotify: {e}")
            return False


# Add the MusicService cog to the bot
async def setup(bot):
    await bot.add_cog(MusicService(bot))
