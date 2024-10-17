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
VERBOSE = True


def verbose_print(message):
    if VERBOSE:
        print(message)


class CardExtractor:
    def __init__(self, output_dir: str = 'cards'):
        self.output_dir = output_dir
        self.colors = ['green', 'yellow', 'red', 'blue']
        self.values = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                       'skip', 'reverse', 'draw2', 'wild', 'draw4']

    # to be improved upon!
    def extract_cards(self, image_path: str):
        # load image
        img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError(f"Could not load image from {image_path}")

        # create directory if it does not exist
        os.makedirs(self.output_dir, exist_ok=True)

        # convert to HSV
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        color_ranges = {
            'green': ([35, 50, 50], [85, 255, 255]),
            'yellow': ([20, 50, 50], [35, 255, 255]),
            'red1': ([0, 50, 50], [10, 255, 255]),
            'red2': ([170, 50, 50], [180, 255, 255]),
            'blue': ([100, 50, 50], [130, 255, 255])
        }

        extracted_cards = []
        color_masks = {}

        # mask for each color
        for color, (lower, upper) in color_ranges.items():
            lower = np.array(lower)
            upper = np.array(upper)
            mask = cv2.inRange(hsv, lower, upper)

            if color == 'red1':
                mask2 = cv2.inRange(hsv, np.array([170, 50, 50]), np.array([180, 255, 255]))
                mask = cv2.bitwise_or(mask, mask2)

            color_masks[color] = mask

        height, width = img.shape[:2]
        expected_card_height = height // 4
        expected_card_width = width // 15

        for color_idx, color in enumerate(['green', 'yellow', 'red1', 'blue']):
            mask = color_masks[color if color != 'red1' else 'red1']

            # find contours in masks
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # sort by x-coord
            sorted_contours = sorted(contours, key=lambda c: cv2.boundingRect(c)[0])

            for card_idx, contour in enumerate(sorted_contours):
                if len(sorted_contours) > 15:  # Überspringe zu kleine Konturen
                    continue

                x, y, w, h = cv2.boundingRect(contour)

                # check card size
                if w < expected_card_width * 0.5 or h < expected_card_height * 0.5:
                    continue

                # cut out by using padding
                padding = 5
                card_img = img[max(0, y - padding):min(height, y + h + padding),
                           max(0, x - padding):min(width, x + w + padding)]

                if card_img.size == 0:
                    continue

                # determine card type and color
                if card_idx < 13:
                    color_name = self.colors[color_idx]
                    value = self.values[card_idx]
                    filename = f"{color_name}_{value}.png"
                else:
                    value = self.values[card_idx]
                    filename = f"wild_{value}.png"

                filepath = os.path.join(self.output_dir, filename)

                # save with alpha channel
                if card_img.shape[-1] == 4:
                    cv2.imwrite(filepath, card_img)
                else:
                    card_rgba = cv2.cvtColor(card_img, cv2.COLOR_BGR2BGRA)
                    cv2.imwrite(filepath, card_rgba)

                extracted_cards.append(card_img)
                verbose_print(f"Extracted card: {filename}")

        return extracted_cards


class Card:
    def __init__(self, color, value):
        self.color = color
        self.value = value

    def __repr__(self):
        return f"{self.color or 'Wild'} {self.value}"

    def is_playable_on(self, other_card):
        """
        Determines if the current card can be played on top of another card.

        Args:
            other_card: The card to check against the current card for playability.

        Returns:
            bool: True if the current card can be played on the other card, False otherwise.
        """
        if self.color is None or other_card.color is None:
            return True
        return self.color == other_card.color or self.value == other_card.value


def initialize_deck():
    """
    Initializes a standard Uno deck with colored and wildcard cards.

    Returns:
        list: A list of Card objects representing a complete Uno deck, including numbered cards,
              action cards, and wildcards.
    """
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


class Deck:
    def __init__(self):
        self.cards = initialize_deck()
        random.shuffle(self.cards)

    def draw_card(self):
        return self.cards.pop() if self.cards else None

    def shuffle_discard_pile_into_deck(self, discard_pile):
        """
        Shuffles the discard pile, except the top card, back into the deck.

        Args:
            discard_pile (list): The pile of cards that have been played during the game.

        Note:
            The top card of the discard pile remains on the discard pile to continue the game.
        """
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
        """
        Initializes a Neural Network for reinforcement learning.

        Args:
            input_size (int): The size of the input layer for the neural network.
            memory_size (int, optional): The maximum size of the replay memory. Defaults to 2000.
            gamma (float, optional): The discount factor for future rewards. Defaults to 0.95.
            epsilon (float, optional): The initial exploration rate for action selection. Defaults to 1.0.
            epsilon_min (float, optional): The minimum exploration rate. Defaults to 0.01.
            epsilon_decay (float, optional): The decay rate for reducing epsilon after each episode. Defaults to 0.995.
            learning_rate (float, optional): The learning rate for the neural network optimizer. Defaults to 0.001.
        """
        self.memory = deque(maxlen=memory_size)
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.learning_rate = learning_rate
        self.input_size = input_size
        self.model = self.build_model()

    def build_model(self):
        """
        Constructs and compiles a neural network model for processing input data.

        Returns:
            keras.Model: A compiled Keras Sequential model with fully connected layers tailored
                         for regression tasks using mean squared error as the loss function.
        """
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
        """
        Stores experiences in the replay memory.

        Args:
            state: The current state of the game.
            action: The action taken by the agent.
            reward: The reward received after taking the action.
            next_state: The state of the game after the action is taken.
            done (bool): A flag indicating whether the episode has ended after this step.
        """
        self.memory.append((state, action, reward, next_state, done))

    def act(self, state, valid_actions):
        """
        Executes an action based on the given state, balancing exploration and exploitation.

        Args:
            state: The current state of the game.
            valid_actions (list): A list of actions that are valid in the current state.

        Returns:
            The chosen action, or None if there are no valid actions.
        """
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
        """
        Combines the state vector with an encoded action vector.

        Args:
            state: The current state of the game as a vector.
            action: The action to be encoded and combined with the state.

        Returns:
            numpy.ndarray: A concatenated array representing the combined state-action pair.
        """
        action_vector = self.encode_action(action)
        return np.concatenate([state, action_vector], axis=1)

    def encode_action(self, action):
        """
        Encodes the given action as a vector.

        Args:
            action: The action to be encoded, typically represented by a card.

        Returns:
            numpy.ndarray: A 1x52 vector where the index corresponding to the action is set to 1, others to 0.
        """
        action_vector = np.zeros((1, 52))
        if action is not None:
            action_vector[0, self.get_card_index(action)] = 1
        return action_vector

    @staticmethod
    def get_card_index(card):
        """
        Returns the index of a card in a vector representation.

        Args:
            card: The card for which the index is to be determined, characterized by its color and value.

        Returns:
            int: The index of the card, calculated based on its color and value, for use in representations like vectors.
        """
        colors = ["Rot", "Gelb", "Grün", "Blau"]
        values = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "Aussetzen", "Richtungswechsel", "+2"]
        if card.value in ["Wild", "+4"]:
            return 48 + ["Wild", "+4"].index(card.value)
        return colors.index(card.color) * 12 + values.index(card.value)

    def replay(self, batch_size):
        """
        Trains the model by reusing experiences stored in memory.

        Args:
            batch_size (int): The number of experiences to use from memory for training the model.
        """
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

            verbose_print(
                f"Replay Step {index + 1}: State: {state}, Action: {action}, Reward: {reward}, Target: {target}")

        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

    def save_model(self, filename='uno_model.keras'):
        """
        Saves the current model to a file.

        Args:
            filename (str, optional): The name of the file to save the model to. Defaults to 'uno_model.keras'.
        """
        self.model.save(filename)
        verbose_print(f"Model saved to {filename}")

    def save_experience(self, filename='uno_experience_memory.pkl'):
        """
        Saves the replay memory to a file.

        Args:
            filename (str, optional): The name of the file to save the replay memory to. Defaults to 'uno_experience_memory.pkl'.
        """
        with open(filename, 'wb') as f:
            pickle.dump(self.memory, f)
        verbose_print(f"Experience memory saved to {filename}")

    def load_experience(self, filename='uno_experience_memory.pkl'):
        """
        Loads the replay memory from a file.

        Args:
            filename (str, optional): The name of the file to load the replay memory from. Defaults to 'uno_experience_memory.pkl'.
        """
        try:
            with open(filename, 'rb') as f:
                self.memory = pickle.load(f)
            verbose_print(f"Experience memory loaded from {filename}")
        except FileNotFoundError:
            verbose_print(f"No experience memory file found at {filename}, starting fresh.")

    @staticmethod
    def save_progress(epsilon, episode, filename='trainingProgress.json'):
        """
        Saves the training progress as a JSON file.

        Args:
            epsilon (float): The current exploration rate.
            episode (int): The current episode number.
            filename (str, optional): The name of the file to save the progress to. Defaults to 'trainingProgress.json'.
        """
        progress = {'epsilon': epsilon, 'episode': episode}
        with open(filename, 'w') as f:
            json.dump(progress, f)
        verbose_print(f"Progress saved to {filename}")


class UnoGame:
    def __init__(self, num_players):
        self.num_players = num_players
        self.reset_game()
        self.state_size = 208  # 156 (state) + 52 (action)
        self.nn = NeuralNet(self.state_size)
        self.card_extractor = CardExtractor()

    def extract_cards_from_image(self, image_path):
        """
        Extracts cards from an image using a card extraction tool.

        Args:
            image_path (str): The file path to the image from which cards should be extracted.

        Returns:
            bool: True if the card extraction was successful, False otherwise.
        """
        try:
            extracted_cards = self.card_extractor.extract_cards(image_path)
            verbose_print(f"Successfully extracted {len(extracted_cards)} cards to the 'cards' directory")
            return True
        except Exception as e:
            verbose_print(f"Error extracting cards: {e}")
            return False

    def reset_game(self):
        """
        Resets the game to its initial state.

        This includes creating a new deck, resetting player hands, initializing the discard pile,
        setting the starting player and game direction, and dealing starting hands to players.
        """
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
        """
        Deals the initial hand of cards to each player at the start of the game.

        Each player receives 7 cards drawn from the deck.
        """
        for _ in range(7):
            for player in self.players:
                card = self.deck.draw_card()
                if card:
                    player.append(card)

    def draw_cards(self, player_idx, count):
        """
        Draws a specified number of cards from the deck for a given player.

        Args:
            player_idx (int): The index of the player who will draw the cards.
            count (int): The number of cards to draw from the deck.

        Returns:
            list: A list of cards that have been drawn.
        """
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
        """
        Executes the action of playing a card from the specified player's hand.

        Args:
            player_idx (int): The index of the player who is playing the card.
            card: The card being played.
            training_mode (bool, optional): Indicates if the game is in training mode, affecting wildcard color choice.
                                            Defaults to False.

        Returns:
            bool: True if the card was successfully played, False otherwise.
        """
        if card in self.players[player_idx]:
            self.players[player_idx].remove(card)
            if card.color is None:
                if player_idx == 0 and not training_mode:  # Menschlicher Spieler
                    card.color = self.choose_color()
                else:  # KI oder Training
                    card.color = random.choice(["Rot", "Gelb", "Grün", "Blau"])
                verbose_print(f"Player {player_idx} played a wildcard. New color: {card.color}")

            self.discard_pile.append(card)  # Karte auf den Ablagestapel legen

            if card.value == "+2":
                next_player = (player_idx + self.direction) % self.num_players
                drawn_cards = self.draw_cards(next_player, 2)
                verbose_print(f"Player {next_player} draws 2 cards: {drawn_cards}")

            elif card.value == "Richtungswechsel":
                self.direction *= -1
                verbose_print(
                    f"Game direction changed to {'clockwise' if self.direction == 1 else 'counterclockwise'}.")

                if self.num_players == 2:
                    # Bei nur zwei Spielern bedeutet ein Richtungswechsel ein "Aussetzen"
                    self.current_player = (self.current_player + self.direction) % self.num_players
                    verbose_print(
                        f"Since there are only two players, this acts as a 'Skip'. Next player is {self.current_player}.")

            elif card.value == "Aussetzen":
                # Die Logik zur Behandlung von Spielzügen im `step`-Abschnitt ist berücksichtigt
                verbose_print(f"Player {player_idx} played 'Aussetzen'. Skipping the next player.")
                self.current_player = (self.current_player + self.direction) % self.num_players

            return True
        return False

    def choose_color(self):
        """
        Prompts the player to choose a new color during the game.

        Returns:
            str: The chosen color as a string ("Rot", "Gelb", "Grün", or "Blau").
        """
        colors = ["Rot", "Gelb", "Grün", "Blau"]
        while True:
            verbose_print("Wähle eine neue Farbe: 1: Rot, 2: Gelb, 3: Grün, 4: Blau")
            try:
                choice = int(input("Deine Wahl: "))
                if 1 <= choice <= 4:
                    return colors[choice - 1]
                else:
                    verbose_print("Ungültige Auswahl. Bitte erneut versuchen.")
            except ValueError:
                verbose_print("Ungültige Eingabe. Bitte eine Zahl eingeben.")

    def encode_state(self):
        """
        Encodes the current game state into a fixed-size numerical representation suitable for AI processing.

        Returns:
            numpy.ndarray: A 1x156 array representing the encoded state of the game, including the player's hand,
                           the top card of the discard pile, and the contents of the discard pile.
        """
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
        """
        Retrieves a list of valid actions (playable cards) for the current player.

        Returns:
            list: A list of cards that the current player can legally play on the discard pile.
        """
        if not self.discard_pile:
            return self.players[self.current_player]

        top_card = self.discard_pile[-1]
        valid_actions = [card for card in self.players[self.current_player]
                         if card.is_playable_on(top_card)]

        verbose_print(f"Player {self.current_player} hand: {self.players[self.current_player]}")
        verbose_print(f"Top Card: {top_card}")
        verbose_print(f"Valid Actions: {valid_actions}")
        return valid_actions

    def calculate_reward(self, action, old_hand_size):
        """
           Calculates the reward for the current player based on their action and hand size.

           Args:
               action: The action performed by the current player.
               old_hand_size (int): The number of cards in the player's hand before the action.

           Returns:
               int: The calculated reward based on the action's effect and changes in hand size.
           """
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
        """
        Executes a single game step by performing the specified action.

        Args:
            action: The action to be performed by the current player.
            training_mode (bool, optional): Indicates if the step is part of a training session.
                                            Defaults to False.

        Returns:
            tuple: A tuple containing the old state, the action taken, the reward received,
                   the new state, and a boolean indicating if the game is done.
        """
        old_state = self.encode_state()
        old_hand_size = len(self.players[self.current_player])

        if action is None:
            verbose_print(f"Player {self.current_player} has to draw a card.")
            self.draw_cards(self.current_player, 1)
        else:
            success = self.play_card(self.current_player, action, training_mode)
            if not success:
                verbose_print(f"Failed to play card: {action} for Player {self.current_player}")

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
        """
        Trains the AI model over a specified number of episodes.

        Args:
            num_episodes (int, optional): The number of episodes to train the model. Defaults to 1000.
            batch_size (int, optional): The batch size used for experience replay during training. Defaults to 32.
            save_every (int, optional): Frequency (in steps) at which the model and progress are saved. Defaults to 100.
        """
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
                verbose_print(f"Episode: {episode}, Total Reward: {total_reward}, Epsilon: {self.nn.epsilon:.2f}")

    def play_game(self, verbose=True):
        """
        Simulates a text-based game where an AI plays the entire game.

        Args:
            verbose (bool, optional): If True, displays detailed game progression information.
                                      Defaults to True.
        """
        self.reset_game()

        while True:
            if verbose:
                verbose_print(f"\nSpieler {self.current_player} ist am Zug")
                verbose_print(f"Oberste Karte: {self.discard_pile[-1]}")
                verbose_print(f"Hand: {self.players[self.current_player]}")

            state = self.encode_state()
            valid_actions = self.get_valid_actions()
            action = self.nn.act(state, valid_actions)

            _, _, reward, _, done = self.step(action)

            if verbose:
                verbose_print(f"Aktion: {'Zieht Karte' if action is None else action}")
                verbose_print(f"Belohnung: {reward}")

            winner = self.check_winner()
            if winner is not None:
                if verbose:
                    verbose_print(f"\nSpieler {winner} gewinnt!")
                return winner

    def play_uno_cmd(self, verbose=True):
        """
        Plays a text-based version of Uno in the console where a human player
        competes against an AI.

        Args:
            verbose (bool, optional): If True, displays detailed game progression information.
                                      Defaults to True.
        """
        self.reset_game()

        while True:
            if verbose:
                verbose_print(f"\nSpieler {self.current_player} ist am Zug")
                verbose_print(f"Oberste Karte: {self.discard_pile[-1]}")
                verbose_print(f"Hand: {self.players[self.current_player]}")

            state = self.encode_state()
            valid_actions = self.get_valid_actions()

            if self.current_player == 0:
                if valid_actions:
                    verbose_print("Mögliche Karten zu spielen:")
                    for i, action in enumerate(valid_actions, start=1):
                        verbose_print(f"{i}: {action}")
                    verbose_print("0: Karte ziehen")

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
                            verbose_print("Ungültige Eingabe. Bitte erneut versuchen.")
                else:
                    verbose_print("Keine spielbaren Karten. Ziehe eine Karte.")
                    action = None
            else:
                action = self.nn.act(state, valid_actions)

            _, _, reward, _, done = self.step(action)

            if verbose:
                verbose_print(f"Aktion: {'Zieht Karte' if action is None else action}")
                verbose_print(f"Belohnung: {reward}")

            winner = self.check_winner()
            if winner is not None:
                if verbose:
                    if winner == 0:
                        verbose_print("\nHerzlichen Glückwunsch, du hast gewonnen!")
                    else:
                        verbose_print(f"\nSpieler {winner} (KI) gewinnt!")
                return winner


# Beispiel zur Nutzung: Uno-Training und eventuell ein Spiel gegen die KI
if __name__ == "__main__":
    game = UnoGame(num_players=2)

    # Laden der gespeicherten Erfahrungen, falls vorhanden
    game.nn.load_experience('uno_experience_memory.pkl')

    # Extract cards before starting the game
    # game.extract_cards_from_image('uno_set.png')

    # Uncomment to train the AI
    # game.train(num_episodes=50, batch_size=32, save_every=10)

    # Start the game
    game.play_uno_cmd()

    # Nach dem Spiel die Erfahrungen speichern
    game.nn.save_experience('uno_experience_memory.pkl')
