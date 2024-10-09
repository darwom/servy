import os
import time
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import logging
from cachetools import TTLCache
from dotenv import load_dotenv
import sqlite3
from typing import Set

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
# Set the path to the .env file relative to the current script location
env_path = os.path.join(os.path.dirname(__file__), '_audio_Processor/spotifySecrets.env')
if not load_dotenv(dotenv_path=env_path):
    logging.error(f"Failed to load .env file from {env_path}")

# Verify environment variables
client_id = os.getenv('SPOTIFY_CLIENT_ID')
client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
if not client_id or not client_secret:
    logging.error("Spotify client ID und secret müssen in den Umgebungsvariablen gesetzt sein.")
else:
    logging.info("Spotify client ID und secret erfolgreich geladen.")

# Define database
DATABASE_DIR = os.path.join(os.path.dirname(__file__), '_audio_Processor')
DATABASE = os.path.join(DATABASE_DIR, 'tracks.db')

# Create directory if it doesn't exist
if not os.path.exists(DATABASE_DIR):
    os.makedirs(DATABASE_DIR)

logging.info(f"Database file path: {os.path.abspath(DATABASE)}")

# Cache setup: TTLCache with a 6-hour expiration time
cache = TTLCache(maxsize=10000, ttl=21600)


class Track:
    def __init__(self, track_data: dict, audio_features: dict):
        logging.debug(f"Creating Track object for '{track_data['name']}' with ID '{track_data['id']}'")
        self.id = track_data['id']
        self.name = track_data['name']
        self.artist = ', '.join(artist['name'] for artist in track_data.get('artists', []))
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
            "tempo": self.tempo,
        }

    def save_to_db(self, conn: sqlite3.Connection):
        try:
            logging.debug(f"Preparing to save track to DB: {self.to_dict()}")
            with conn:
                sql = '''INSERT OR REPLACE INTO tracks 
                         (id, name, artist, album, release_date, uri, duration, 
                          popularity, danceability, energy, tempo) 
                         VALUES (?,?,?,?,?,?,?,?,?,?,?)'''
                data = (self.id, self.name, self.artist, self.album, self.release_date,
                        self.uri, self.duration, self.popularity, self.danceability,
                        self.energy, self.tempo)
                logging.debug(f"Attempting to save track data: {data}")
                conn.execute(sql, data)

            # Verify insertion
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tracks WHERE id =?", (self.id,))
            result = cursor.fetchone()
            if result:
                logging.debug(f"Track {self.name} with ID {self.id} successfully verified in the database.")
                logging.info(f"Track erfolgreich in die Datenbank eingefügt: {self.id}")
            else:
                raise sqlite3.DatabaseError(
                    f"Track {self.name} with ID {self.id} not found in the database after insertion.")
        except sqlite3.IntegrityError as e:
            logging.error(f"Integrity error while saving track {self.name} with ID {self.id}: {e}")
            raise
        except sqlite3.DatabaseError as e:
            logging.error(f"Database error while saving track {self.name} with ID {self.id}: {e}")
            raise
        except sqlite3.Error as e:
            logging.error(f"SQLite error while saving track {self.name} with ID {self.id}: {e.args[0]}")
            raise
        except Exception as e:
            logging.error(f"Unexpected error while saving track {self.name} with ID {self.id}: {e}")
            raise


class Sourcer:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth_manager = SpotifyClientCredentials(client_id=self.client_id, client_secret=self.client_secret)
        self.sp = spotipy.Spotify(auth_manager=self.auth_manager)
        self.last_request_time = 0
        self.min_request_interval = 2  # Minimum interval between requests in seconds
        self.conn = self._create_db_connection()
        if not self.conn:
            raise Exception('Database connection could not be established.')
        logging.info('Database connection established.')
        self._create_tables()
        self.global_pause_threshold = 10  # Number of consecutive 429 errors before a global pause
        self.consecutive_429_errors = 0  # Counter for consecutive 429 errors
        self.error_cache = TTLCache(maxsize=100, ttl=7200)  # Cache error state for 2 hours

    def _create_db_connection(self):
        try:
            logging.debug(f"Connecting to database at {DATABASE}")
            conn = sqlite3.connect(DATABASE)
            conn.execute("PRAGMA foreign_keys = 1")
            logging.debug(f"Successfully connected to the database {DATABASE}.")
            return conn
        except sqlite3.DatabaseError as e:
            logging.error(f"Failed to connect to the database: {e}")
            return None

    def _create_tables(self):
        if self.conn:
            try:
                with self.conn:
                    sql_table_creation = '''CREATE TABLE IF NOT EXISTS tracks (
                        id TEXT PRIMARY KEY,
                        name TEXT,
                        artist TEXT,
                        album TEXT,
                        release_date TEXT,
                        uri TEXT,
                        duration INTEGER,
                        popularity INTEGER,
                        danceability REAL,
                        energy REAL,
                        tempo REAL
                    )'''
                    logging.debug(f"Executing SQL: {sql_table_creation}")
                    self.conn.execute(sql_table_creation)
                    self.conn.commit()  # Commit table creation
                cursor = self.conn.cursor()
                cursor.execute("PRAGMA table_info(tracks)")
                columns = cursor.fetchall()
                logging.debug(f"Tracks table columns: {columns}")
                logging.info('Database tables created or verified.')
            except sqlite3.DatabaseError as e:
                logging.error(f"Error while creating tables: {e}")

    def verify_tracks_in_db(self):
        try:
            if self.conn:
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute("SELECT * FROM tracks")
                    rows = cursor.fetchall()
                    logging.info(f"Number of tracks in database: {len(rows)}")
                    for row in rows:
                        logging.debug(f"Track in DB: {row}")
            else:
                logging.error("No database connection available to verify tracks")
        except sqlite3.DatabaseError as e:
            logging.error(f"Database error while verifying tracks: {e}")

    def close_connection(self):
        if self.conn:
            self.conn.close()
            logging.info("Database connection closed.")

    def commit_changes(self):
        if self.conn:
            self.conn.commit()
            logging.info("Changes committed to the database.")

    def wait_if_needed(self):
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def handle_rate_limits(self, headers):
        retry_after = headers.get('Retry-After', 120)  # Default to 120 seconds if not specified
        logging.warning(f"Rate limited. Retrying after {retry_after} seconds.")
        time.sleep(int(retry_after))
        self.last_request_time = time.time()  # Update last request time after handling rate limit

    def exponential_backoff(self, attempt):
        backoff_time = min(180, (2 ** attempt))  # Increase to a max of 180 seconds
        logging.info(f"Backing off for {backoff_time} seconds.")
        time.sleep(backoff_time)

    def get_audio_features(self, track_id: str):
        if track_id in self.error_cache:
            logging.warning(f"Skipping track {track_id} due to repeated 429 errors.")
            return {}

        cache_key = f"audio_features:{track_id}"
        if cache_key in cache:
            logging.info(f"Cache hit for audio features: {track_id}")
            return cache[cache_key]

        retries = 5
        for attempt in range(retries):
            self.wait_if_needed()
            try:
                response = self.sp.audio_features([track_id])
                logging.debug(f"Audio features response for track {track_id}: {response}")
                if response and response[0]:
                    features = response[0]
                    if features:
                        cache[cache_key] = features  # Cache the result
                        return features
            except spotipy.exceptions.SpotifyException as e:
                logging.error(f"Spotify API error while fetching features for track {track_id}: {e}")
                if e.http_status == 429:
                    self.handle_rate_limit(e, attempt)
                    continue
                self.error_cache[track_id] = True  # Cache error for this track
                return {}
            except Exception as e:
                logging.error(f"Unexpected error while fetching audio features for track {track_id}: {e}")
                return {}
        logging.error(f"Max retries reached. Failed to get audio features for track {track_id}.")
        return {}

    def handle_rate_limit(self, e, attempt):
        if e.http_status == 429:
            self.consecutive_429_errors += 1
            if self.consecutive_429_errors >= self.global_pause_threshold:
                logging.warning("Too many 429 errors. Global pause for 300 seconds.")
                time.sleep(300)  # Global pause for 5 minutes
                self.consecutive_429_errors = 0

            self.handle_rate_limits(e.headers)
            self.exponential_backoff(attempt)
            return True
        self.consecutive_429_errors = 0
        return False

    def get_track(self, track_id: str):
        cache_key = f"track:{track_id}"
        if cache_key in cache:
            logging.info(f"Cache hit for track: {track_id}")
            return cache[cache_key]

        retries = 5
        for attempt in range(retries):
            self.wait_if_needed()
            try:
                logging.debug(f"Fetching data for track ID: {track_id}")
                response = self.sp.track(track_id)
                if response:
                    track_data = response
                    logging.debug(f"Track data response for track {track_id}: {track_data}")
                    if not track_data:
                        logging.warning(f"Failed to retrieve track data for track {track_id}")
                        continue

                    if track_data['is_local']:
                        logging.info(f"Skipping local track: {track_id}")
                        continue

                    audio_features = self.get_audio_features(track_id)

                    track = Track(track_data, audio_features)
                    track_dict = track.to_dict()
                    logging.debug(f"Track data: {track_dict}")

                    try:
                        track.save_to_db(self.conn)
                        logging.info(f"Track successfully saved: {track.name} by {track.artist}")
                    except Exception as e:
                        logging.error(f"Error saving track {track_id}: {e}")
                        logging.debug(f"Track data that caused error: {track_dict}")
                        # Don't raise the exception here, continue processing other tracks

                    cache[cache_key] = track  # Cache the result
                    logging.debug(f"Track with ID {track_id} processed and saved to the database.")
                    return track
            except spotipy.exceptions.SpotifyException as e:
                logging.error(f"Spotify API error fetching track {track_id}: {e}")
                if e.http_status == 429:
                    self.handle_rate_limit(e, attempt)
                    continue
            except Exception as e:
                logging.error(f"Unexpected error while fetching track {track_id}: {e}")
        logging.error(f"Max retries reached. Failed to get track data for track {track_id}.")
        return None

    def get_top_playlists_by_genre(self, genre: str, limit: int = 10):
        retries = 5
        for attempt in range(retries):
            self.wait_if_needed()
            try:
                results = self.sp.search(q=f'genre:"{genre}"', type='playlist', limit=limit)
                logging.debug(f"Playlist search results for genre '{genre}': {results}")
                if results:
                    playlists = results['playlists']['items']
                    if not playlists:
                        logging.warning(f"No playlists found for genre: {genre}")
                        return []

                    return [playlist['id'] for playlist in playlists]
            except spotipy.exceptions.SpotifyException as e:
                logging.error(f"Spotify API error during genre playlist search: {e}")
                if e.http_status == 429:
                    self.handle_rate_limit(e, attempt)
                    continue
            except Exception as e:
                logging.error(f"Unexpected error during genre playlist search: {e}")
        logging.error("Max retries reached. Failed to get playlists for genre.")
        return []

    def get_playlist_tracks(self, playlist_id: str) -> Set[str]:
        retries = 5
        track_ids = set()
        for attempt in range(retries):
            self.wait_if_needed()
            try:
                logging.debug(f"Fetching tracks from playlist ID: {playlist_id}")
                results = self.sp.playlist_tracks(playlist_id)
                logging.debug(f"Tracks from playlist '{playlist_id}': {results}")

                if results:
                    tracks = results['items']
                    if not tracks:
                        logging.warning(f"No tracks found in playlist: {playlist_id}")
                        return set()

                    for track_item in tracks:
                        track = track_item['track']
                        if track and not track.get('is_local'):
                            track_ids.add(track['id'])
                        else:
                            logging.info(f"Skipping local or unavailable track in playlist: {track_item}")

                # Handle pagination if necessary
                while results['next']:
                    self.wait_if_needed()
                    results = self.sp.next(results)
                    logging.debug(f"Paginated tracks from playlist '{playlist_id}': {results}")
                    tracks = results['items']
                    for track_item in tracks:
                        track = track_item['track']
                        if track and not track.get('is_local'):
                            track_ids.add(track['id'])
                        else:
                            logging.info(f"Skipping local or unavailable track in playlist: {track_item}")

                logging.debug(f"Total tracks fetched from playlist '{playlist_id}': {len(track_ids)}")
                return track_ids
            except spotipy.exceptions.SpotifyException as e:
                logging.error(f"Spotify API error fetching playlist tracks {playlist_id}: {e}")
                if e.http_status == 429:
                    self.handle_rate_limit(e, attempt)
                    continue
            except Exception as e:
                logging.error(f"Unexpected error fetching tracks from playlist {playlist_id}: {e}")
        logging.error("Max retries reached. Failed to get tracks from playlist.")
        return set()


def setup_database():
    try:
        conn = sqlite3.connect(DATABASE)
        sql_table_creation = '''CREATE TABLE IF NOT EXISTS tracks (
                id TEXT PRIMARY KEY,
                name TEXT,
                artist TEXT,
                album TEXT,
                release_date TEXT,
                uri TEXT,
                duration INTEGER,
                popularity INTEGER,
                danceability REAL,
                energy REAL,
                tempo REAL
            )'''
        conn.execute(sql_table_creation)
        conn.commit()
        conn.close()
        logging.info("Database setup completed.")
    except sqlite3.DatabaseError as e:
        logging.error(f"Database setup failed: {e}")


def test_db_connection():
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(tracks)")
        columns = cursor.fetchall()
        assert len(columns) > 0, "Tracks table does not exist or has no columns"
        logging.info("Database connection and table verification successful.")
    except sqlite3.DatabaseError as e:
        logging.error(f"Database connection test failed: {e}")
    finally:
        conn.close()


def test_insert():
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        track_data = (
            "1", "Test Track", "Test Artist", "Test Album", "2022-01-01", "spotify:track:1", 200000, 50, 0.8, 0.7,
            120.0)
        cursor.execute('''INSERT OR REPLACE INTO tracks (id, name, artist, album, release_date, uri, duration, popularity, danceability, energy, tempo)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', track_data)
        conn.commit()

        cursor.execute("SELECT * FROM tracks WHERE id = ?", ("1",))
        result = cursor.fetchone()
        assert result is not None, "Failed to insert track into database"
        logging.info("Track insertion test successful.")
    except sqlite3.DatabaseError as e:
        logging.error(f"Track insertion test failed: {e}")
    finally:
        conn.close()  # Ensure the connection is closed


def main():
    client_id = os.getenv('SPOTIFY_CLIENT_ID')
    client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')

    if not client_id or not client_secret:
        logging.error("Spotify client ID und secret müssen in den Umgebungsvariablen gesetzt sein.")
        return

    logging.info(f"Client ID: {client_id}")

    try:
        sourcer = Sourcer(client_id, client_secret)
    except Exception as e:
        logging.error(f"Failed to create Sourcer: {e}")
        return

    genre = input("Geben Sie das Genre ein, um die Top-Playlists abzurufen: ")
    top_playlist_ids = sourcer.get_top_playlists_by_genre(genre)

    if not top_playlist_ids:
        logging.warning(f"Keine Playlists für das Genre '{genre}' gefunden")
        return

    all_track_ids = set()

    for playlist_id in top_playlist_ids:
        logging.info(f"Abrufen von Tracks aus der Playlist: {playlist_id}")
        playlist_track_ids = sourcer.get_playlist_tracks(playlist_id)
        all_track_ids.update(playlist_track_ids)

    track_count = 0
    for track_id in all_track_ids:
        try:
            track = sourcer.get_track(track_id)
            if track:
                logging.info(f"Successfully processed track: {track.name}")
                track_count += 1
                if track_count % 100 == 0:  # Commit every 100 tracks
                    sourcer.commit_changes()
            else:
                logging.warning(f"Failed to process track with ID: {track_id}")
        except Exception as e:
            logging.error(f"Error processing track {track_id}: {e}")

    sourcer.commit_changes()  # Final commit
    sourcer.verify_tracks_in_db()


if __name__ == '__main__':
    setup_database()
    test_db_connection()
    test_insert()
    main()