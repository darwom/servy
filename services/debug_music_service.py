# This script is for debugging services.music_service

import pytest
from unittest.mock import Mock, MagicMock, call
from datetime import datetime
from services.music_service import MusicService, DatabaseManager, Track


# Works flawlessly!
def test_successful_db_connection(mocker):
    # Correct the path to point to the actual location of DatabaseManager
    mock_db_manager = mocker.patch('services.music_service.DatabaseManager')
    mock_db_manager.return_value.connect_to_db.return_value = MagicMock()

    # Call the function or method you want to test
    result = mock_db_manager.connect_to_db()

    # Assert the expected outcome
    assert result is not None


# Should work too!
# Successfully creates the 'track_history' table if it does not exist
def test_create_table_success(mocker):
    # Mock the connection object
    mock_conn = mocker.Mock()
    mock_execute = mocker.patch.object(mock_conn, 'execute')

    # Create an instance of DatabaseManager
    db_manager = DatabaseManager()

    # Call the create_table method
    db_manager.create_table(mock_conn)

    # Define the expected SQL command
    expected_sql = '''
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
    '''

    # Normalize the SQL strings
    def normalize_sql(sql):
        return ' '.join(sql.split())

    # Assert that the execute method was called with the correct SQL
    mock_execute.assert_called_once()
    actual_sql = mock_execute.call_args[0][0]
    assert normalize_sql(actual_sql) == normalize_sql(expected_sql)


@pytest.fixture
def mock_db(mocker):
    # Patch get_db_connection to return a mocked connection and cursor
    mock_conn = MagicMock()
    mock_cursor = mock_conn.cursor()
    mock_cursor.fetchone.return_value = None  # Simulate track not present in DB
    mock_get_db_connection = mocker.patch('services.music_service.get_db_connection')
    mock_get_db_connection.return_value.__enter__.return_value = mock_conn
    mock_get_db_connection.return_value.__exit__.return_value = False
    return mock_conn, mock_cursor


@pytest.fixture
def track_fixture():
    # Creates a dummy Track instance for testing
    return Track(id='1', name='Test Track', artist='Test Artist', album='Test Album',
                 release_date='2023-01-01', uri='test_uri', duration=300000, popularity=50)


def normalize_sql(sql):
    """Remove leading, trailing, multiple spaces, and linebreaks for SQL."""
    return ' '.join(sql.split())


# Finally works (fingers crossed!)
def test_save_track_when_not_in_database(mocker, mock_db, track_fixture):
    # Arrange
    mock_conn, mock_cursor = mock_db

    # Mock the datetime to control the timestamp
    fixed_datetime = datetime(2023, 1, 1, 12, 0, 0)
    mock_datetime = mocker.patch('datetime.datetime')
    mock_datetime.now.return_value = fixed_datetime

    # Act
    db_manager = DatabaseManager(db_path="test_db_path")
    db_manager.save_track(track_fixture, 'test_user', True, fixed_datetime)

    # Normalize SQL
    expected_select_sql = normalize_sql('''
        SELECT count FROM track_history
        WHERE title = ? AND artist = ?
    ''')

    expected_insert_sql = normalize_sql('''
        INSERT INTO track_history
        (title, artist, album, release_date, playlist_uri, user_name, on_spotify, count, timestamp, manual_addition)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
    ''')

    # Assert SQL execution and commit
    select_call_args = mock_cursor.execute.call_args_list[0][0]
    insert_call_args = mock_cursor.execute.call_args_list[1][0]

    assert normalize_sql(select_call_args[0]) == expected_select_sql
    assert normalize_sql(insert_call_args[0]) == expected_insert_sql

    expected_select_params = (track_fixture.name, track_fixture.artist)
    expected_insert_params = (
        track_fixture.name, track_fixture.artist, track_fixture.album,
        track_fixture.release_date, track_fixture.uri, 'test_user',
        True, fixed_datetime, 0)

    assert select_call_args[1] == expected_select_params
    assert insert_call_args[1] == expected_insert_params

    mock_conn.commit.assert_called_once()


# This one works!
@pytest.mark.asyncio
async def test_successful_spotify_search(mocker):
    # Arrange
    mock_spotify = mocker.Mock()
    mock_db_manager = mocker.Mock()

    # Mock Spotify search response
    mock_spotify.search.return_value = {
        'tracks': {
            'items': [{
                'id': '123',
                'name': 'Test Track',
                'artists': [{'name': 'Test Artist'}],
                'album': {'name': 'Test Album', 'release_date': '2023-01-01'},
                'uri': 'spotify:track:123',
                'duration_ms': 300000,
                'popularity': 50
            }]
        }
    }

    # Mock Spotify audio features response
    mock_spotify.audio_features.return_value = [{
        'danceability': 0.8,
        'energy': 0.7,
        'tempo': 120.0
    }]

    # Initialize MusicService
    music_service = MusicService(bot=mocker.Mock())

    # Inject the mocked Spotify and DatabaseManager
    music_service.sp = mock_spotify
    music_service.db_manager = mock_db_manager

    # Act
    track = await music_service.find_on_spotify('Test Track', 'Test Artist', 'user123', datetime.now())

    # Assert
    assert track is not None
    assert track.id == '123'
    assert track.name == 'Test Track'
    assert track.artist == 'Test Artist'
    assert track.album == 'Test Album'
    assert track.release_date == '2023-01-01'
    assert track.uri == 'spotify:track:123'
    assert track.duration == 300000
    assert track.popularity == 50
    assert track.danceability == 0.8
    assert track.energy == 0.7
    assert track.tempo == 120.0

    # Verify that save_track was called with the correct parameters
    mock_db_manager.save_track.assert_called_once_with(
        track, 'user123', on_spotify=True, timestamp=mocker.ANY
    )


# Works too
# Test for get_most_requested_tracks method
def test_get_most_requested_tracks(mocker, mock_db):
    # Arrange
    mock_conn, mock_cursor = mock_db
    mock_cursor.fetchall.return_value = [
        ('Track 1', 'Artist 1', 10),
        ('Track 2', 'Artist 2', 8),
        ('Track 3', 'Artist 3', 5)
    ]

    db_manager = DatabaseManager(db_path="test_db_path")

    # Act
    result = db_manager.get_most_requested_tracks()

    # Assert
    expected_result = [
        ('Track 1', 'Artist 1', 10),
        ('Track 2', 'Artist 2', 8),
        ('Track 3', 'Artist 3', 5)
    ]
    assert result == expected_result

    # Normalize SQL
    def normalize_sql(sql):
        return ' '.join(sql.split())

    expected_sql = '''
        SELECT title, artist, SUM(count) as total_count
        FROM track_history
        GROUP BY title, artist
        ORDER BY total_count DESC
        LIMIT 10
    '''
    actual_sql = mock_cursor.execute.call_args[0][0]
    assert normalize_sql(actual_sql) == normalize_sql(expected_sql)
