import os
import logging
import sqlite3
from datetime import datetime
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import youtube_dl
import matplotlib.pyplot as plt
import seaborn as sns

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
    def __init__(self, track_data: dict, audio_features: dict):
        """
        Initializes a Track object with metadata and audio features.

        Args:
            track_data (dict): The track metadata from Spotify.
            audio_features (dict): The audio features of the track from Spotify.
        """
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
        """
        Converts the track object to a dictionary.

        Returns:
            dict: The track metadata as a dictionary.
        """
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
        """
        Returns a string representation of the track object for debugging.

        Returns:
            str: String representation of the track.
        """
        return f"Track(id={self.id}, name={self.name}, artist={self.artist}, album={self.album}, release_date={self.release_date}, uri={self.uri})"


class DatabaseManager:
    def __init__(self, db_path='history.db'):
        """
        Initializes the DatabaseManager with a SQLite database file.

        Args:
            db_path (str): The file path for the SQLite database.
        """
        self.db_path = db_path
        self.connection = self.connect_to_db()
        self.create_table()

    def connect_to_db(self):
        """
        Connects to the SQLite database.

        Returns:
            sqlite3.Connection: The database connection object.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            logging.info(f"Connected to database at {self.db_path}")
            return conn
        except sqlite3.Error as e:
            logging.error(f"Error connecting to database: {e}")
            return None

    def create_table(self):
        """
        Creates the track history table in the database if it does not exist.
        """
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
                        timestamp DATETIME
                    )
                ''')
                logging.info("Table 'track_history' ensured in database.")
        except sqlite3.Error as e:
            logging.error(f"Error creating table: {e}")

    def save_track(self, track: Track, user_name: str, on_spotify: bool, timestamp: datetime):
        """
        Saves a track entry to the database or updates the count if it exists.

        Args:
            track (Track): The track object to save.
            user_name (str): The name of the user who requested the track.
            on_spotify (bool): Flag indicating if the track was found on Spotify.
            timestamp (datetime): The timestamp of the request.
        """
        try:
            with self.connection:
                cursor = self.connection.cursor()
                cursor.execute('''
                    SELECT count FROM track_history
                    WHERE title = ? AND artist = ? AND user_name = ?
                ''', (track.name, track.artist, user_name))
                result = cursor.fetchone()

                if result:
                    current_count = result[0]
                    new_count = current_count + 1
                    cursor.execute('''
                        UPDATE track_history
                        SET count = ?, timestamp = ?
                        WHERE title = ? AND artist = ? AND user_name = ?
                    ''', (new_count, timestamp, track.name, track.artist, user_name))
                else:
                    cursor.execute('''
                        INSERT INTO track_history
                        (title, artist, album, release_date, playlist_uri, user_name, on_spotify, count, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                    ''', (track.name, track.artist, track.album, track.release_date, track.uri, user_name, on_spotify, timestamp))

                self.connection.commit()
                logging.info(f"Track '{track.name}' by '{track.artist}' saved to database.")
        except sqlite3.Error as e:
            logging.error(f"Error saving track to database: {e}")

    def get_most_requested_tracks(self):
        """
        Retrieves the most requested tracks from the database.

        Returns:
            list of tuple: A list of tuples containing track title, artist, and request count.
        """
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
        """
        Retrieves the top artists with the most tracks found on Spotify.

        Returns:
            list of tuple: A list of tuples containing artist name and total count.
        """
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
        """
        Fetches statistics on successful vs. unsuccessful Spotify searches.

        Returns:
            tuple: A tuple containing counts of successful and unsuccessful searches.
        """
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
        """
        Retrieves user activity statistics indicating most active users.

        Returns:
            list of tuple: A list of tuples containing user names and total request count.
        """
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
        """
        Generates and saves a heatmap of user activity over time.
        """
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


class SpotifyParser:
    def __init__(self):
        """
        Initializes SpotifyParser with Spotify API and YouTube data extractor.
        """
        self.sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))
        self.ytdl = youtube_dl.YoutubeDL({
            'quiet': True,
            'noplaylist': True,
            'format': 'bestaudio/best',
        })
        self.db_manager = DatabaseManager()

    def extract_info_from_youtube(self, youtube_url):
        """
        Extracts title and artist information from a YouTube URL.

        Args:
            youtube_url (str): The URL of the YouTube video.

        Returns:
            tuple: A tuple containing the title and artist extracted.
        """
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
        """
        Searches for a track on Spotify given a title and artist, then saves result.

        Args:
            title (str): The title of the track to search on Spotify.
            artist (str): The artist of the track to search on Spotify.
            user_name (str): The name of the user who requested the search.
            timestamp (datetime): The timestamp of when the request was made.

        Returns:
            Track or bool: The Track object if found, False if not found.
        """
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
                dummy_track = Track({'id': None, 'name': title, 'artists': [{'name': artist}], 'album': {'name': '', 'release_date': ''}, 'uri': None, 'duration_ms': 0, 'popularity': 0}, {})
                self.db_manager.save_track(dummy_track, user_name, on_spotify=False, timestamp=timestamp)
                return False
        except Exception as e:
            logging.error(f"Error searching Spotify: {e}")
            return False

    def check_youtube_in_spotify(self, youtube_url, user_name, timestamp):
        """
        Checks if a YouTube video is available on Spotify and saves the result.

        Args:
            youtube_url (str): The URL of the YouTube video to check.
            user_name (str): The name of the user who requested the check.
            timestamp (datetime): The timestamp of when the request was made.

        Returns:
            Track or bool: The Track object if found on Spotify, False otherwise.
        """
        title, artist = self.extract_info_from_youtube(youtube_url)
        return self.find_on_spotify(title, artist, user_name, timestamp)
