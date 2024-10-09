import sqlite3
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from tensorflow import keras
from tensorflow.keras import layers


class DatabaseAnalyzer:
    def __init__(self, database_path):
        self.database_path = database_path
        self.model = None

    def load_data_from_db(self):
        """Lädt die Track-Datenbank und gibt einen Pandas DataFrame zurück."""
        conn = sqlite3.connect(self.database_path)
        query = "SELECT * FROM tracks"
        tracks_df = pd.read_sql(query, conn)
        conn.close()
        return tracks_df

    def preprocess_data(self, df):
        """Vorbereitung der Daten für das neuronale Netzwerk."""
        # Wähle die relevanten Features aus
        features = df[['danceability', 'energy', 'tempo', 'popularity']]
        labels = df['popularity'] > 50  # Beispiel: Als beliebt markieren, wenn die Popularität über 50 ist
        labels = labels.astype(int)  # Umwandlung von boolean nach int

        # Normalisiere die Features
        features_normalized = (features - features.min()) / (features.max() - features.min())
        return features_normalized, labels

    def build_model(self, input_shape):
        """Erstellt das neuronale Netzwerkmodell."""
        self.model = keras.Sequential([
            layers.InputLayer(input_shape=input_shape),
            layers.Dense(16, activation='relu'),
            layers.Dense(8, activation='relu'),
            layers.Dense(1, activation='sigmoid')
        ])
        self.model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])

    def train_model(self, features, labels, epochs=10, batch_size=32):
        """Trainiert das Modell mit den gegebenen Features und Labels."""
        X_train, X_test, y_train, y_test = train_test_split(features, labels, test_size=0.2, random_state=42)

        if self.model is None:
            self.build_model(input_shape=X_train.shape[1:])
        else:
            print("Model already built, proceeding to training.")

        self.model.summary()
        self.model.fit(X_train, y_train, epochs=epochs, batch_size=batch_size, validation_split=0.2)

        test_loss, test_accuracy = self.model.evaluate(X_test, y_test)
        print(f"Test Accuracy: {test_accuracy:.2f}")

    def predict(self, new_data):
        """Macht Vorhersagen mit dem trainierten Modell."""
        if self.model is None:
            raise Exception("Model is not built or trained yet.")
        return self.model.predict(new_data)


def main():
    # Instantiate the analyzer with the path to your database
    analyzer = DatabaseAnalyzer('tracks.db')

    # Load and preprocess data
    df = analyzer.load_data_from_db()
    features, labels = analyzer.preprocess_data(df)

    # Train the model
    analyzer.train_model(features, labels)

    # Example of making a prediction
    # Assume we have a new track with preprocessed features
    new_track_features = np.array([[0.5, 0.6, 0.7, 0.6]])  # Replace with real data
    prediction = analyzer.predict(new_track_features)
    print(f"Prediction for new track: {prediction}")


if __name__ == '__main__':
    main()