import asyncio
from cogs.uno import UnoGame  # Annahme: Diese Klasse ist in deiner uno.py definiert


# Debugging-Skript für das lokale Testen der Funktionalität des Projekts.
# Dieses Skript ermöglicht es, verschiedene Klassen und Funktionen zu testen,
# ohne dass eine Discord-Integration erforderlich ist.

# In diesem Beispiel wird die Uno-Spielmechanik getestet,
# Weitere Testfunktionen können hinzugefügt werden, um andere Module zu testen.
# from deinem_module import DeineKlasse, andere_notwendige_Funktion

async def test_uno_game():
    """Testet die Funktionalität des Uno-Spiels lokal.

    Diese Funktion simuliert ein Uno-Spiel zwischen zwei Spielern
    und verarbeitet Züge, um die Spielmechanik zu testen.
    """
    # Erstelle eine Instanz des Uno-Spiels für zwei Spieler.
    game = UnoGame(num_players=2)

    # Initialisiere das Spiel, indem du die Karten mischtest und die Ausgangshände verteilst.
    game.reset_game()

    # Eine Schleife, die die Aktionen jedes Spielers der Reihe nach behandelt, bis das Spiel gewonnen wird.
    while True:
        # Bestimme, welcher Spieler im aktuellen Zug agiert.
        current_player = game.current_player

        # Prozess für den menschlichen Spieler (hier Spieler 0).
        if current_player == 0:
            print(f"Spieler {current_player} ist am Zug")
            print(f"Oberste Karte: {game.discard_pile[-1]}")
            print(f"Hand: {game.players[current_player]}")

            # Zeige die gültigen Züge an, die der Spieler machen kann.
            valid_actions = game.get_valid_actions()
            if valid_actions:
                print("Wähle eine Karte zu spielen oder 'ziehen' um zu ziehen:")
                for i, action in enumerate(valid_actions):
                    print(f"{i + 1}: {action}")
                print("0: Ziehen")

                # Erfrage die Eingabe des Spielers für deren nächsten Zug.
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
                # Wenn keine gültigen Züge vorhanden sind, muss der Spieler eine Karte ziehen.
                print("Keine spielbaren Karten. Ziehe eine Karte.")
                action = None

        # KI-Logik für den Computergegner.
        else:
            # Entscheide die Aktion der KI basierend auf dem aktuellen Zustand.
            state = game.encode_state()
            valid_actions = game.get_valid_actions()
            action = game.nn.act(state, valid_actions)

        # Führe die gewählte Aktion aus und aktualisiere den Spielstatus.
        _, _, reward, _, done = game.step(action)
        print(f"Aktion: {'Zieht Karte' if action is None else action}")
        print(f"Belohnung: {reward}")

        # Überprüfen, ob ein Spieler gewonnen hat und beende das Spiel bei Bedarf.
        winner = game.check_winner()
        if winner is not None:
            print(f"Spieler {winner} gewinnt!")
            break


if __name__ == "__main__":
    # Starte das Testen der Funktionen asynchron, um asynchronen Code zu behandeln.
    asyncio.run(test_uno_game())