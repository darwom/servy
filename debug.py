import asyncio
import os
from cogs._uno import UnoGame
from cogs.audioProcessor import Sourcer, setup_database, test_db_connection, test_insert
from dotenv import load_dotenv


# Debugging-Skript für das lokale Testen der Funktionalität des Projekts.

def test_spotify_integration():
    """Testet die Integration mit der Spotify-API und dem Datenbankmodul."""

    # Stelle sicher, dass Umgebungsvariablen geladen werden
    env_path = os.path.join(os.path.dirname(__file__), 'spotifySecrets.env')
    if not load_dotenv(dotenv_path=env_path):
        raise RuntimeError(f"Failed to load .env file from {env_path}")

    client_id = os.getenv('SPOTIFY_CLIENT_ID')
    client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')

    if not client_id or not client_secret:
        raise ValueError("Spotify client ID und secret müssen in den Umgebungsvariablen gesetzt sein.")

    # Instanziiere den Spotify-Datenlader
    sourcer = Sourcer(client_id, client_secret)

    # Lade und teste Top-Playlists für eine Genre
    genre = "pop"  # Beispielgenre zum Testen
    playlist_ids = sourcer.get_top_playlists_by_genre(genre)
    print(f"Gefundene Playlists für Genre '{genre}': {playlist_ids}")

    if playlist_ids:
        # Teste den Abruf von Tracks aus der ersten Playlist
        track_ids = sourcer.get_playlist_tracks(playlist_ids[0])
        print(f"Tracks in der Playlist '{playlist_ids[0]}': {track_ids}")

    # Führe Datenbanktests aus
    test_db_connection()
    test_insert()


def test_uno_game():
    """Testet die Funktionalität des Uno-Spiels lokal.

    Diese Funktion simuliert ein Uno-Spiel zwischen zwei Spielern
    und verarbeitet Züge, um die Spielmechanik zu testen.
    """
    game = UnoGame(num_players=2)
    game.nn.load_experience('experience_memory.pkl')
    game.reset_game()

    while True:
        current_player = game.current_player
        if current_player == 0:
            print(f"Spieler {current_player} ist am Zug")
            print(f"Oberste Karte: {game.discard_pile[-1]}")
            print(f"Hand: {game.players[current_player]}")

            valid_actions = game.get_valid_actions()
            if valid_actions:
                print("Wähle eine Karte zu spielen oder 'ziehen' um zu ziehen:")
                for i, action in enumerate(valid_actions):
                    print(f"{i + 1}: {action}")
                print("0: Ziehen")

                user_input = input("Gib eine Nummer oder 'ziehen' ein: ")
                if user_input.lower().strip() == 'ziehen':
                    action = None
                else:
                    try:
                        action = valid_actions[int(user_input) - 1]
                    except (IndexError, ValueError):
                        print("Ungültige Eingabe. Ziehe eine Karte.")
                        action = None
            else:
                print("Keine spielbaren Karten. Ziehe eine Karte.")
                action = None

        else:
            state = game.encode_state()
            valid_actions = game.get_valid_actions()
            action = game.nn.act(state, valid_actions)

        _, _, reward, _, done = game.step(action)
        print(f"Aktion: {'Zieht Karte' if action is None else action}")
        print(f"Belohnung: {reward}")

        winner = game.check_winner()
        if winner is not None:
            print(f"Spieler {winner} gewinnt!")
            break

    game.nn.save_experience('experience_memory.pkl')


def main():
    """Orchestriert die Tests für UNO-Spielmechanik und Spotify-Interaktionen."""
    setup_database()
    test_spotify_integration()
    #asyncio.run(test_uno_game())


if __name__ == "__main__":
    main()