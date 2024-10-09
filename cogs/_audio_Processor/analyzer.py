import os
import sqlite3
import pandas as pd
import numpy as np
import json
import multiprocessing
from sklearn.model_selection import train_test_split
from tensorflow import keras
from tensorflow.keras import layers
import graphics as gp  # Importiere das graphics Modul


def preprocess_data(df):
    """Vorbereitung der Daten für das neuronale Netzwerk."""
    features = df[['danceability', 'energy', 'tempo', 'popularity']]
    labels = df['popularity']
    features_normalized = (features - features.min()) / (features.max() - features.min())
    return features_normalized, labels


def calculate_statistics(df):
    """Berechnet statistische Kennzahlen für die Features danceability, energy, tempo und popularity."""
    stats = {}
    features = ['danceability', 'energy', 'tempo', 'popularity']
    for feature in features:
        stats[feature] = {
            'mean': df[feature].mean(),
            'std_dev': df[feature].std(),
            'variance': df[feature].var(),
            'range': df[feature].max() - df[feature].min(),
            'min': df[feature].min(),
            'max': df[feature].max(),
            'median': df[feature].median(),
            'q1': df[feature].quantile(0.25),
            'q3': df[feature].quantile(0.75)
        }
    return stats


class DatabaseAnalyzer:
    def __init__(self, database_path):
        self.database_path = database_path
        self.model = None
        self.model_save_path = os.path.join(os.path.dirname(__file__), 'neuralNet.keras')
        self.log_save_path = os.path.join(os.path.dirname(__file__), 'analysis/training_log.json')

    def load_data_from_db(self):
        """Lädt die Track-Datenbank und gibt einen Pandas DataFrame zurück."""
        conn = sqlite3.connect(self.database_path)
        query = "SELECT * FROM tracks"
        tracks_df = pd.read_sql(query, conn)
        conn.close()
        return tracks_df

    def build_model(self, input_shape):
        """Erstellt das neuronale Netzwerkmodell."""
        self.model = keras.Sequential([
            layers.InputLayer(input_shape=input_shape),
            layers.Dense(16, activation='relu'),
            layers.Dense(8, activation='relu'),
            layers.Dense(1)
        ])
        self.model.compile(optimizer='adam', loss='mean_squared_error', metrics=['mean_absolute_error'])

    def train_model(self, features, labels, epochs=1000, batch_size=32):
        """Trainiert das Modell mit den gegebenen Features und Labels."""
        X_train, X_test, y_train, y_test = train_test_split(features, labels, test_size=0.2, random_state=42)

        if self.model is None:
            self.build_model(input_shape=X_train.shape[1:])

        self.model.summary()
        history = self.model.fit(X_train, y_train, epochs=epochs, batch_size=batch_size, validation_split=0.2)

        test_loss, test_mae = self.model.evaluate(X_test, y_test)
        print(f"Test Mean Absolute Error: {test_mae:.2f}")

        self.model.save(self.model_save_path)
        print(f"Model saved to {self.model_save_path}")

        self.save_training_log(history)
        return history

    def save_training_log(self, history):
        """Speichert den Trainingsverlauf in einer JSON-Datei."""
        log_data = history.history
        with open(self.log_save_path, 'w') as f:
            json.dump(log_data, f)
        print(f"Training log saved to {self.log_save_path}")

    def read_training_log(self):
        """Liest den Trainingsverlauf aus einer JSON-Datei."""
        with open(self.log_save_path, 'r') as f:
            log_data = json.load(f)
        print(f"Training log loaded from {self.log_save_path}")
        return log_data

    def predict(self, new_data):
        """Macht Vorhersagen mit dem trainierten Modell."""
        if self.model is None:
            raise Exception("Model is not built or trained yet.")
        return self.model.predict(new_data)


def main():
    analyzer = DatabaseAnalyzer('tracks.db')

    df = analyzer.load_data_from_db()
    features, labels = preprocess_data(df)

    # Berechne und zeige die statistischen Kennzahlen
    stats = calculate_statistics(df)
    for feature, values in stats.items():
        print(f"{feature} statistics: {values}")

    history = analyzer.train_model(features, labels)

    # Verwende Multiprocessing, um die Plots parallel zu öffnen
    process1 = multiprocessing.Process(target=gp.plot_training_history, args=(history, True))
    process2 = multiprocessing.Process(target=gp.visualize_database)

    process1.start()
    process2.start()

    process1.join()
    process2.join()

    new_track_features = np.array([[0.5, 0.6, 0.7, 0.6]])
    prediction = analyzer.predict(new_track_features)
    print(f"Projection for new track popularity: {prediction}")

    training_log = analyzer.read_training_log()
    print(training_log)


if __name__ == '__main__':
    main()
