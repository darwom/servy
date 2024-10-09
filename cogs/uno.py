import os
import pickle
import random
import json
import numpy as np
import cv2
from collections import deque
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Input
from tensorflow.keras.optimizers import Adam

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'


class CardExtractor:
    def __init__(self, output_dir: str = 'cards'):
        self.output_dir = output_dir
        self.colors = ['green', 'yellow', 'red', 'blue']
        self.values = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                       'skip', 'reverse', 'draw2', 'wild', 'draw4']

    def extract_cards(self, image_path: str):
        # Bild laden
        img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError(f"Could not load image from {image_path}")

        # Ausgabeverzeichnis erstellen, falls es nicht existiert
        os.makedirs(self.output_dir, exist_ok=True)

        # Bild in HSV-Farbraum konvertieren für bessere Farbsegmentierung
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Farbgrenzen definieren
        color_ranges = {
            'green': ([35, 50, 50], [85, 255, 255]),
            'yellow': ([20, 50, 50], [35, 255, 255]),
            'red1': ([0, 50, 50], [10, 255, 255]),
            'red2': ([170, 50, 50], [180, 255, 255]),
            'blue': ([100, 50, 50], [130, 255, 255])
        }

        extracted_cards = []
        color_masks = {}

        # Masken für jede Farbe erstellen
        for color, (lower, upper) in color_ranges.items():
            lower = np.array(lower)
            upper = np.array(upper)
            mask = cv2.inRange(hsv, lower, upper)

            if color == 'red1':
                mask2 = cv2.inRange(hsv, np.array([170, 50, 50]), np.array([180, 255, 255]))
                mask = cv2.bitwise_or(mask, mask2)

            color_masks[color] = mask

        # Bildgröße ermitteln
        height, width = img.shape[:2]
        expected_card_height = height // 4
        expected_card_width = width // 15

        # Für jede Farbreihe
        for color_idx, color in enumerate(['green', 'yellow', 'red1', 'blue']):
            mask = color_masks[color if color != 'red1' else 'red1']

            # Konturen in der Maske finden
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # Konturen nach x-Koordinate sortieren
            sorted_contours = sorted(contours, key=lambda c: cv2.boundingRect(c)[0])

            for card_idx, contour in enumerate(sorted_contours):
                if len(sorted_contours) > 15:  # Überspringe zu kleine Konturen
                    continue

                x, y, w, h = cv2.boundingRect(contour)

                # Kartengrößen-Check
                if w < expected_card_width * 0.5 or h < expected_card_height * 0.5:
                    continue

                # Karte ausschneiden mit etwas Padding
                padding = 5
                card_img = img[max(0, y - padding):min(height, y + h + padding),
                           max(0, x - padding):min(width, x + w + padding)]

                if card_img.size == 0:
                    continue

                # Bestimme Kartentyp und Dateinamen
                if card_idx < 13:
                    color_name = self.colors[color_idx]
                    value = self.values[card_idx]
                    filename = f"{color_name}_{value}.png"
                else:
                    value = self.values[card_idx]
                    filename = f"wild_{value}.png"

                filepath = os.path.join(self.output_dir, filename)

                # Speichern mit Alpha-Kanal
                if card_img.shape[-1] == 4:
                    cv2.imwrite(filepath, card_img)
                else:
                    card_rgba = cv2.cvtColor(card_img, cv2.COLOR_BGR2BGRA)
                    cv2.imwrite(filepath, card_rgba)

                extracted_cards.append(card_img)
                print(f"Extracted card: {filename}")

        return extracted_cards


class Card:
    def __init__(self, color, value):
        self.color = color
        self.value = value

    def __repr__(self):
        return f"{self.color or 'Wild'} {self.value}"

    def is_playable_on(self, other_card):
        if self.color is None or other_card.color is None:
            return True
        return self.color == other_card.color or self.value == other_card.value


class Deck:
    def __init__(self):
        self.cards = self.initialize_deck()
        random.shuffle(self.cards)

    def initialize_deck(self):
        colors = ["Rot", "Gelb", "Grün", "Blau"]
        values = ["1", "2", "3", "4", "5", "6", "7", "8", "9",
                  "Aussetzen", "Richtungswechsel", "+2"]
        deck = []

        # Einmal für die Null pro Farbe
        for color in colors:
            deck.append(Card(color, "0"))

        # Zweimal für alle anderen Werte in den Farben
        for color in colors:
            for value in values:
                deck.extend([Card(color, value) for _ in range(2)])

        # Wildcards hinzufügen
        wild_cards = [Card(None, "Wild") for _ in range(4)] + [Card(None, "+4") for _ in range(4)]
        deck.extend(wild_cards)

        return deck

    def draw_card(self):
        return self.cards.pop() if self.cards else None

    def shuffle_discard_pile_into_deck(self, discard_pile):
        if len(discard_pile) <= 1:
            return
        self.cards = discard_pile[:-1]
        random.shuffle(self.cards)
        top_card = discard_pile[-1]
        discard_pile.clear()
        discard_pile.append(top_card)


class NeuralNet:
    def __init__(self, input_size, memory_size=2000, gamma=0.95, epsilon=1.0, epsilon_min=0.01, epsilon_decay=0.995,
                 learning_rate=0.001):
        self.memory = deque(maxlen=memory_size)
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.learning_rate = learning_rate
        self.input_size = input_size
        self.model = self.build_model()

    def build_model(self):
        model = Sequential([
            Input(shape=(self.input_size,)),
            Dense(256, activation='relu'),
            Dense(128, activation='relu'),
            Dense(64, activation='relu'),
            Dense(1, activation='linear')
        ])
        model.compile(loss='mse', optimizer=Adam(learning_rate=self.learning_rate))
        return model

    def memorize(self, state, action, reward, next_state, done):
        """ Speichert Erfahrungen im Replay-Speicher. """
        self.memory.append((state, action, reward, next_state, done))

    def act(self, state, valid_actions):
        """ Führt eine Aktion basierend auf dem gegebenen Zustand aus, wobei Exploration gegen Exploitation abgewogen wird. """
        if not valid_actions:
            return None

        if np.random.rand() <= self.epsilon:
            return random.choice(valid_actions)

        act_values = []
        for action in valid_actions:
            state_action_pair = self.get_state_action_pair(state, action)
            prediction = self.model.predict(state_action_pair, verbose=0)[0]
            act_values.append(prediction[0])

        return valid_actions[np.argmax(act_values)]

    def get_state_action_pair(self, state, action):
        """ Kombiniert den Zustandsvektor mit einem kodierten Aktionsvektor. """
        action_vector = self.encode_action(action)
        return np.concatenate([state, action_vector], axis=1)

    def encode_action(self, action):
        """ Kodiert die Aktion als einen Vektor. """
        action_vector = np.zeros((1, 52))
        if action is not None:
            action_vector[0, self.get_card_index(action)] = 1
        return action_vector

    @staticmethod
    def get_card_index(card):
        """ Gibt den Index einer Karte in einem Vektor zurück. """
        colors = ["Rot", "Gelb", "Grün", "Blau"]
        values = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "Aussetzen", "Richtungswechsel", "+2"]
        if card.value in ["Wild", "+4"]:
            return 48 + ["Wild", "+4"].index(card.value)
        return colors.index(card.color) * 12 + values.index(card.value)

    def replay(self, batch_size):
        """ Trainiert das Model durch erneuten Einsatz von Erfahrungen im Speicher. """
        if len(self.memory) < batch_size:
            return

        minibatch = random.sample(self.memory, batch_size)
        for index, (state, action, reward, next_state, done) in enumerate(minibatch):
            target = reward
            if not done:
                next_state_action = self.get_state_action_pair(next_state, action)
                target = reward + self.gamma * self.model.predict(next_state_action, verbose=0)[0][0]

            target_f = self.model.predict(self.get_state_action_pair(state, action), verbose=0)
            target_f[0][0] = target
            self.model.fit(self.get_state_action_pair(state, action), target_f, epochs=1, verbose=0)

            print(f"Replay Step {index + 1}: State: {state}, Action: {action}, Reward: {reward}, Target: {target}")

        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

    def save_model(self, filename='uno_model.keras'):
        """ Speichert das aktuelle Modell in einer Datei. """
        self.model.save(filename)
        print(f"Model saved to {filename}")

    def save_experience(self, filename='uno_experience_memory.pkl'):
        """ Speichert den Replay-Memory in einer Datei. """
        with open(filename, 'wb') as f:
            pickle.dump(self.memory, f)
        print(f"Experience memory saved to {filename}")

    def load_experience(self, filename='uno_experience_memory.pkl'):
        """ Lädt den Replay-Memory von einer Datei. """
        try:
            with open(filename, 'rb') as f:
                self.memory = pickle.load(f)
            print(f"Experience memory loaded from {filename}")
        except FileNotFoundError:
            print(f"No experience memory file found at {filename}, starting fresh.")

    @staticmethod
    def save_progress(epsilon, episode, filename='trainingProgress.json'):
        """ Speichert den Fortschritt des Trainings als JSON. """
        progress = {'epsilon': epsilon, 'episode': episode}
        with open(filename, 'w') as f:
            json.dump(progress, f)
        print(f"Progress saved to {filename}")


class UnoGame:
    def __init__(self, num_players):
        self.num_players = num_players
        self.reset_game()
        self.state_size = 208  # 156 (state) + 52 (action)
        self.nn = NeuralNet(self.state_size)
        self.card_extractor = CardExtractor()

    def extract_cards_from_image(self, image_path):
        try:
            extracted_cards = self.card_extractor.extract_cards(image_path)
            print(f"Successfully extracted {len(extracted_cards)} cards to the 'cards' directory")
            return True
        except Exception as e:
            print(f"Error extracting cards: {e}")
            return False

    def reset_game(self):
        self.deck = Deck()
        self.players = [[] for _ in range(self.num_players)]
        self.discard_pile = []
        self.current_player = 0
        self.direction = 1
        self.deal_starting_hands()
        initial_card = self.deck.draw_card()
        if initial_card:
            self.discard_pile.append(initial_card)

    def deal_starting_hands(self):
        for _ in range(7):
            for player in self.players:
                card = self.deck.draw_card()
                if card:
                    player.append(card)

    def draw_cards(self, player_idx, count):
        drawn_cards = []
        for _ in range(count):
            card = self.deck.draw_card()
            if card:
                drawn_cards.append(card)
            elif len(self.discard_pile) > 1:
                self.deck.shuffle_discard_pile_into_deck(self.discard_pile)
                card = self.deck.draw_card()
                if card:
                    drawn_cards.append(card)
        self.players[player_idx].extend(drawn_cards)
        return drawn_cards

    def play_card(self, player_idx, card, training_mode=False):
        if card in self.players[player_idx]:
            self.players[player_idx].remove(card)
            if card.color is None:
                if player_idx == 0 and not training_mode:  # Menschlicher Spieler
                    card.color = self.choose_color()
                else:  # KI oder Training
                    card.color = random.choice(["Rot", "Gelb", "Grün", "Blau"])
                print(f"Player {player_idx} played a wildcard. New color: {card.color}")

            self.discard_pile.append(card)  # Karte auf den Ablagestapel legen

            if card.value == "+2":
                next_player = (player_idx + self.direction) % self.num_players
                drawn_cards = self.draw_cards(next_player, 2)
                print(f"Player {next_player} draws 2 cards: {drawn_cards}")

            elif card.value == "Richtungswechsel":
                self.direction *= -1
                print(f"Game direction changed to {'clockwise' if self.direction == 1 else 'counterclockwise'}.")

                if self.num_players == 2:
                    # Bei nur zwei Spielern bedeutet ein Richtungswechsel ein "Aussetzen"
                    self.current_player = (self.current_player + self.direction) % self.num_players
                    print(
                        f"Since there are only two players, this acts as a 'Skip'. Next player is {self.current_player}.")

            elif card.value == "Aussetzen":
                # Die Logik zur Behandlung von Spielzügen im `step`-Abschnitt ist berücksichtigt
                print(f"Player {player_idx} played 'Aussetzen'. Skipping the next player.")
                self.current_player = (self.current_player + self.direction) % self.num_players

            return True
        return False

    def choose_color(self):
        colors = ["Rot", "Gelb", "Grün", "Blau"]
        while True:
            print("Wähle eine neue Farbe: 1: Rot, 2: Gelb, 3: Grün, 4: Blau")
            try:
                choice = int(input("Deine Wahl: "))
                if 1 <= choice <= 4:
                    return colors[choice - 1]
                else:
                    print("Ungültige Auswahl. Bitte erneut versuchen.")
            except ValueError:
                print("Ungültige Eingabe. Bitte eine Zahl eingeben.")

    def encode_state(self):
        state = np.zeros((1, 156))

        # Encode player's hand
        for card in self.players[self.current_player]:
            state[0, self.nn.get_card_index(card)] += 1

        # Encode top card
        if self.discard_pile:
            top_card_idx = self.nn.get_card_index(self.discard_pile[-1])
            state[0, 52 + top_card_idx] = 1

        # Encode discard pile
        for card in self.discard_pile:
            state[0, 104 + self.nn.get_card_index(card)] += 1

        return state

    def get_valid_actions(self):
        if not self.discard_pile:
            return self.players[self.current_player]

        top_card = self.discard_pile[-1]
        valid_actions = [card for card in self.players[self.current_player]
                         if card.is_playable_on(top_card)]

        print(f"Player {self.current_player} hand: {self.players[self.current_player]}")
        print(f"Top Card: {top_card}")
        print(f"Valid Actions: {valid_actions}")
        return valid_actions

    def calculate_reward(self, action, old_hand_size):
        if action is None:
            return -1

        reward = 5

        if action.value in ["+2", "+4"]:
            reward += 3
        elif action.value in ["Aussetzen", "Richtungswechsel"]:
            reward += 2

        new_hand_size = len(self.players[self.current_player])
        if new_hand_size < old_hand_size:
            reward += (old_hand_size - new_hand_size) * 2

        if new_hand_size == 0:
            reward += 50
        elif new_hand_size == 1:
            reward += 10

        return reward

    def step(self, action, training_mode=False):
        old_state = self.encode_state()
        old_hand_size = len(self.players[self.current_player])

        if action is None:
            print(f"Player {self.current_player} has to draw a card.")
            self.draw_cards(self.current_player, 1)
        else:
            success = self.play_card(self.current_player, action, training_mode)
            if not success:
                print(f"Failed to play card: {action} for Player {self.current_player}")

        reward = self.calculate_reward(action, old_hand_size)
        done = self.check_winner() is not None

        # Wenn es kein Aussetzen oder Richtungswechsel mit nur zwei Spielern war, zum nächsten Spieler wechseln
        if not (action and action.value in ["Aussetzen", "Richtungswechsel"] and self.num_players == 2):
            self.current_player = (self.current_player + self.direction) % self.num_players

        return old_state, action, reward, self.encode_state(), done

    def check_winner(self):
        for player_idx, hand in enumerate(self.players):
            if len(hand) == 0:
                return player_idx
        return None

    def train(self, num_episodes=1000, batch_size=32, save_every=100):
        total_steps = 0
        for episode in range(num_episodes):
            self.reset_game()
            total_reward = 0

            while True:
                state = self.encode_state()
                valid_actions = self.get_valid_actions()
                action = self.nn.act(state, valid_actions)

                old_state, action, reward, new_state, done = self.step(action, training_mode=True)
                total_reward += reward

                self.nn.memorize(old_state, action, reward, new_state, done)
                self.nn.replay(batch_size)

                total_steps += 1

                if total_steps % save_every == 0:
                    self.nn.save_model()
                    NeuralNet.save_progress(self.nn.epsilon, episode)

                if done:
                    break

            if episode % 100 == 0:
                print(f"Episode: {episode}, Total Reward: {total_reward}, Epsilon: {self.nn.epsilon:.2f}")

    def play_game(self, verbose=True):
        self.reset_game()

        while True:
            if verbose:
                print(f"\nSpieler {self.current_player} ist am Zug")
                print(f"Oberste Karte: {self.discard_pile[-1]}")
                print(f"Hand: {self.players[self.current_player]}")

            state = self.encode_state()
            valid_actions = self.get_valid_actions()
            action = self.nn.act(state, valid_actions)

            _, _, reward, _, done = self.step(action)

            if verbose:
                print(f"Aktion: {'Zieht Karte' if action is None else action}")
                print(f"Belohnung: {reward}")

            winner = self.check_winner()
            if winner is not None:
                if verbose:
                    print(f"\nSpieler {winner} gewinnt!")
                return winner

    def play_uno_cmd(self, verbose=True):
        self.reset_game()

        while True:
            if verbose:
                print(f"\nSpieler {self.current_player} ist am Zug")
                print(f"Oberste Karte: {self.discard_pile[-1]}")
                print(f"Hand: {self.players[self.current_player]}")

            state = self.encode_state()
            valid_actions = self.get_valid_actions()

            if self.current_player == 0:
                if valid_actions:
                    print("Mögliche Karten zu spielen:")
                    for i, action in enumerate(valid_actions, start=1):
                        print(f"{i}: {action}")
                    print("0: Karte ziehen")

                    while True:
                        try:
                            user_input = input("Wähle eine Aktion (Nummer eingeben): ")
                            user_action_idx = int(user_input)
                            if user_action_idx == 0:
                                action = None
                                break
                            else:
                                action = valid_actions[user_action_idx - 1]
                                break
                        except (IndexError, ValueError):
                            print("Ungültige Eingabe. Bitte erneut versuchen.")
                else:
                    print("Keine spielbaren Karten. Ziehe eine Karte.")
                    action = None
            else:
                action = self.nn.act(state, valid_actions)

            _, _, reward, _, done = self.step(action)

            if verbose:
                print(f"Aktion: {'Zieht Karte' if action is None else action}")
                print(f"Belohnung: {reward}")

            winner = self.check_winner()
            if winner is not None:
                if verbose:
                    if winner == 0:
                        print("\nHerzlichen Glückwunsch, du hast gewonnen!")
                    else:
                        print(f"\nSpieler {winner} (KI) gewinnt!")
                return winner


# Beispiel zur Nutzung: Uno-Training und eventuell ein Spiel gegen die KI
if __name__ == "__main__":
    game = UnoGame(num_players=2)

    # Laden der gespeicherten Erfahrungen, falls vorhanden
    game.nn.load_experience('uno_experience_memory.pkl')

    # Extract cards before starting the game
    #game.extract_cards_from_image('uno_set.png')

    # Uncomment to train the AI
    #game.train(num_episodes=10, batch_size=32, save_every=10)

    # Start the game
    game.play_uno_cmd()

    # Nach dem Spiel die Erfahrungen speichern
    game.nn.save_experience('uno_experience_memory.pkl')