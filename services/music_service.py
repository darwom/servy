from contextlib import contextmanager
from dataclasses import dataclass, field
import logging
import os
import logging
import sqlite3
from datetime import datetime
from typing import Optional, List, Tuple

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


@dataclass
class Track:
    id: str
    name: str
    artist: str
    album: str
    release_date: str
    uri: str
    duration: int
    popularity: int
    danceability: float = field(default=0.0)
    energy: float = field(default=0.0)
    tempo: float = field(default=0.0)

    def __post_init__(self):
        logging.info(f"Creating Track object for '{self.name}' with ID '{self.id}'")

    @classmethod
    def from_data(cls, track_data: dict, audio_features: dict):
        if not all(key in track_data for key in ['id', 'name', 'artists', 'album', 'uri', 'duration_ms', 'popularity']):
            raise ValueError("track_data is missing required keys")
        if not all(key in audio_features for key in ['danceability', 'energy', 'tempo']):
            raise ValueError("audio_features is missing required keys")

        artist_names = ', '.join(artist['name'] for artist in track_data['artists'])
        return cls(
            id=track_data['id'],
            name=track_data['name'],
            artist=artist_names,
            album=track_data['album']['name'],
            release_date=track_data['album']['release_date'],
            uri=track_data['uri'],
            duration=track_data['duration_ms'],
            popularity=track_data['popularity'],
            danceability=audio_features.get('danceability', 0),
            energy=audio_features.get('energy', 0),
            tempo=audio_features.get('tempo', 0)
        )

    def to_dict(self) -> dict:
        return self.__dict__

    def __repr__(self):
        return (f"Track(id={self.id}, name={self.name}, artist={self.artist}, "
                f"album={self.album}, release_date={self.release_date}, uri={self.uri})")


@contextmanager
def get_db_connection(db_path: str):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


class DatabaseManager:
    def __init__(self, db_path='history.db'):
        self.db_path = db_path
        with get_db_connection(self.db_path) as conn:
            self.create_table(conn)

    @staticmethod
    def create_table(conn: sqlite3.Connection) -> None:
        """
        Ensures the 'track_history' table exists in the database.

        Parameters:
        - conn: sqlite3.Connection - The database connection object.

        Raises:
        - sqlite3.Error: If there is an error executing the SQL command.
        """
        try:
            conn.execute('''
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
            with get_db_connection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT count FROM track_history
                    WHERE title = ? AND artist = ?
                ''', (track.name, track.artist))
                result = cursor.fetchone()

                if result:
                    logging.info(f"Track '{track.name}' by '{track.artist}' already in database. Updating count.")
                    cursor.execute('''
                        UPDATE track_history
                        SET count = count + 1
                        WHERE title = ? AND artist = ?
                    ''', (track.name, track.artist))
                else:
                    cursor.execute('''
                        INSERT INTO track_history
                        (title, artist, album, release_date, playlist_uri, user_name, on_spotify, count, timestamp, manual_addition)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    ''', (track.name, track.artist, track.album, track.release_date, track.uri, user_name, on_spotify,
                          timestamp, int(manual_addition)))

                conn.commit()
                logging.info(f"Track '{track.name}' by '{track.artist}' saved to database.")
        except sqlite3.Error as e:
            logging.error(f"Error saving track to database: {e}")

    def get_most_requested_tracks(self) -> List[Tuple[str, str, int]]:
        logging.info("Fetching most requested tracks.")
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT title, artist, SUM(count) as total_count
                FROM track_history
                GROUP BY title, artist
                ORDER BY total_count DESC
                LIMIT 10
            ''')
            return cursor.fetchall()

    def get_top_artists(self) -> List[Tuple[str, int]]:
        logging.info("Fetching top artists.")
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT artist, SUM(count) as total_count
                FROM track_history
                WHERE on_spotify = 1
                GROUP BY artist
                ORDER BY total_count DESC
                LIMIT 10
            ''')
            return cursor.fetchall()

    def get_search_success_stats(self) -> Optional[Tuple[int, int]]:
        logging.info("Fetching search success stats.")
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    SUM(CASE WHEN on_spotify = 1 THEN 1 ELSE 0 END) AS successful,
                    SUM(CASE WHEN on_spotify = 0 THEN 1 ELSE 0 END) AS unsuccessful
                FROM track_history
            ''')
            return cursor.fetchone()

    def get_user_activity_stats(self) -> List[Tuple[str, int]]:
        logging.info("Fetching user activity stats.")
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
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
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
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
            else:
                logging.info("No data available to generate heatmap.")


class MusicService(commands.Cog):
    """
    A class that wraps the Spotify and YouTube music services as a Discord bot cog.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sp = None  # Spotify client will be initialized if credentials are available
        client_id = os.getenv('SPOTIFY_CLIENT_ID')
        client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        if client_id and client_secret:
            try:
                self.sp = spotipy.Spotify(
                    auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))
                logging.info("Spotify client initialized successfully.")
            except Exception as e:
                logging.error(f"Error initializing Spotify client: {e}")
        else:
            logging.warning("Spotify credentials not found in environment variables.")

        try:
            self.ytdl = youtube_dl.YoutubeDL({
                'quiet': True,
                'noplaylist': True,
                'format': 'bestaudio/best',
            })
            logging.info("YoutubeDL initialized successfully.")
        except Exception as e:
            logging.error(f"Error during YoutubeDL initialization: {e}")

        self.db_manager = DatabaseManager()

    @commands.command(name='youtube_to_spotify')
    async def youtube_to_spotify(self, ctx: commands.Context, youtube_url: str):
        user_name = ctx.author.name
        timestamp = datetime.now()
        track = await self.check_youtube_in_spotify(youtube_url, user_name, timestamp)
        if track:
            await ctx.send(f"Track '{track.name}' by {track.artist} found on Spotify!")
        else:
            await ctx.send("Track not found on Spotify. Please check the URL or try another track.")

    async def check_youtube_in_spotify(self, youtube_url: str, user_name: str, timestamp: datetime) -> Optional[Track]:
        info = self.extract_info_from_youtube(youtube_url)
        if info['title'] and info['artist']:
            return await self.find_on_spotify(info['title'], info['artist'], user_name, timestamp)
        else:
            logging.error("Failed to extract valid title or artist from YouTube.")
            return None

    def extract_info_from_youtube(self, youtube_url: str) -> dict:
        try:
            logging.info(f"Extracting info from YouTube URL: {youtube_url}")
            info = self.ytdl.extract_info(youtube_url, download=False)
            return {'title': info.get('title'), 'artist': info.get('uploader')}
        except Exception as e:
            logging.error(f"Error extracting info from YouTube: {e}")
            return {'title': None, 'artist': None}

    async def find_on_spotify(self, title: str, artist: str, user_name: str, timestamp: datetime) -> Optional[Track]:
        query = f"{title} {artist}"
        try:
            logging.info(f"Searching Spotify for: {query}")
            results = self.sp.search(q=query, type='track', limit=1)
            tracks = results.get('tracks', {}).get('items')
            if tracks:
                track_data = tracks[0]
                audio_features = self.sp.audio_features(track_data['id'])[0]
                logging.info("Found matching track on Spotify.")
                track = Track.from_data(track_data, audio_features)
                self.db_manager.save_track(track, user_name, on_spotify=True, timestamp=timestamp)
                return track
            else:
                logging.info("No matching track found on Spotify.")
                dummy_track = Track(
                    id=None, name=title, artist=artist, album='', release_date='', uri=None,
                    duration=0, popularity=0
                )
                self.db_manager.save_track(dummy_track, user_name, on_spotify=False, timestamp=timestamp)
                return None
        except Exception as e:
            logging.error(f"Error searching Spotify: {e}")
            return None


# Add the MusicService cog to the bot
async def setup(bot: commands.Bot):
    await bot.add_cog(MusicService(bot))
