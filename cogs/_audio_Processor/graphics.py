import os
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pandas.plotting import parallel_coordinates


def load_tracks_data():
    """Lädt die Track-Datenbank in einen Pandas DataFrame."""
    database_path = os.path.join(os.path.dirname(__file__), 'tracks.db')
    conn = sqlite3.connect(database_path)
    query = "SELECT danceability, energy, tempo, popularity FROM tracks"
    tracks_df = pd.read_sql(query, conn)
    conn.close()
    return tracks_df


def plot_features(df):
    """Visualisiert mehrere Features aus dem DataFrame in einem Pairplot."""
    sns.set(style='whitegrid')
    pairplot = sns.pairplot(df, diag_kind='kde', plot_kws={'alpha': 0.6, 's': 80, 'edgecolor': 'k'},
                            diag_kws={'fill': True})
    pairplot.fig.suptitle('Feature Pairplot of Tracks', y=1.02)
    plt.show(block=True)


def plot_parallel_coordinates(df):
    """Visualisiert mehrere Features aus dem DataFrame in einem Parallelkoordinatendiagramm."""
    df_normalized = (df - df.min()) / (df.max() - df.min())  # Normalisierung für parallele Koordinaten
    plt.figure(figsize=(12, 6))
    parallel_coordinates(df_normalized, class_column='popularity', colormap=plt.get_cmap('viridis'))
    plt.title('Parallel Coordinates Plot for Tracks')
    plt.xlabel('Features')
    plt.ylabel('Normalized Feature Value')
    plt.show(block=True)


def plot_histogram(df, feature, normalize=True, save_to_file=True):
    """Erstellt ein Histogramm für ein gegebenes Feature und speichert es optional."""
    plt.figure(figsize=(10, 6))
    sns.histplot(df[feature], bins=30, kde=True, stat='density' if normalize else 'count')
    plt.title(f'Histogram of {feature.capitalize()}')
    plt.xlabel(feature.capitalize())
    plt.ylabel('Density' if normalize else 'Frequency')

    # Sicherstellen, dass das Unterverzeichnis 'analysis' existiert
    output_dir = os.path.join(os.path.dirname(__file__), 'analysis')
    os.makedirs(output_dir, exist_ok=True)

    # Datei unter dem entsprechenden Namen speichern
    if save_to_file:
        file_path = os.path.join(output_dir, f"{feature}_histogram.png")
        plt.savefig(file_path)
        print(f"Saved histogram to {file_path}")

    plt.show()


def plot_distribution(df, feature, save_to_file=True):
    """Erstellt die kumulative Verteilungsfunktion (CDF) des gegebenen Features und speichert sie optional."""
    plt.figure(figsize=(10, 6))
    sns.ecdfplot(df[feature])
    plt.title(f'CDF of {feature.capitalize()}')
    plt.xlabel(feature.capitalize())
    plt.ylabel('Cumulative Probability')

    # Sicherstellen, dass das Unterverzeichnis 'analysis' existiert
    output_dir = os.path.join(os.path.dirname(__file__), 'analysis')
    os.makedirs(output_dir, exist_ok=True)

    # Datei unter dem entsprechenden Namen speichern
    if save_to_file:
        file_path = os.path.join(output_dir, f"{feature}_cdf.png")
        plt.savefig(file_path)
        print(f"Saved CDF to {file_path}")

    plt.show()


def plot_training_history(history, log_scale=False):
    """Visualisiert die Trainings- und Validierungsmetriken über die Epochen.

    Args:
        history: Das Verlauf-Objekt, das beim Keras-Modelltraining zurückgegeben wird.
        log_scale: Boolean, der bestimmt, ob die y-Achse logarithmisch dargestellt werden soll.
    """
    plt.figure(figsize=(12, 5))
    plt.subplot(1, 2, 1)
    plt.plot(history.history['loss'], label='Trainingsverlust')
    plt.plot(history.history['val_loss'], label='Validierungsverlust')
    plt.title('Verlust während des Trainings')
    plt.xlabel('Epochen')
    plt.ylabel('Verlust')
    if log_scale:
        plt.yscale('log')
    plt.legend()

    plt.subplot(1, 2, 2)
    plt.plot(history.history['mean_absolute_error'], label='Training MAE')
    plt.plot(history.history['val_mean_absolute_error'], label='Validierung MAE')
    plt.title('Mean Absolute Error während des Trainings')
    plt.xlabel('Epochen')
    plt.ylabel('MAE')
    if log_scale:
        plt.yscale('log')
    plt.legend()

    plt.tight_layout()
    plt.show()


def visualize_database():
    tracks_df = load_tracks_data()
    print(tracks_df.head())  # Debugging-Ausgabe

    # Pairplot-Visualisierung
    plot_features(tracks_df)

    # Parallel-Koordinaten-Visualisierung
    plot_parallel_coordinates(tracks_df)

    # Histogramme für jede Eigenschaft plotten
    plot_histogram(tracks_df, 'danceability', normalize=True, save_to_file=True)
    plot_histogram(tracks_df, 'energy', normalize=True, save_to_file=True)
    plot_histogram(tracks_df, 'tempo', normalize=True, save_to_file=True)
    plot_histogram(tracks_df, 'popularity', normalize=True, save_to_file=True)

    # Cumulative Distribution Function (CDF) für jedes Feature plotten
    plot_distribution(tracks_df, 'danceability', save_to_file=True)
    plot_distribution(tracks_df, 'energy', save_to_file=True)
    plot_distribution(tracks_df, 'tempo', save_to_file=True)
    plot_distribution(tracks_df, 'popularity', save_to_file=True)