import os
import json
import subprocess
import gzip  # Kann entfernt werden, wenn Nginx das übernimmt
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)  # BaseHTTPRequestHandler ist ausreichend
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import html  # Für XSS-Schutz

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Konfiguration (besser aus Umgebungsvariablen oder Config-Datei lesen)
UNMINED_CLI_PATH = (
    r"C:\Program Files\unmined\unmined-cli_0.19.47-dev_win-64bit\unmined-cli.exe"
)
MINECRAFT_WORLD_PATH = r"C:\Users\dNine\AppData\Roaming\.minecraft\saves\boyzTest"
MAP_OUTPUT_BASE_PATH = os.path.join(BASE_DIR, "maps")
# Einfacher Secret Token als rudimentäre Sicherung
# In einer echten Anwendung einen sicher generierten, langen Token verwenden und als Umgebungsvariable setzen!
SECRET_TOKEN = "K?R4?oDSJGzar58a5nzdYItTxCcZmAgv87pOZ?!v9y49"


# --- Hilfsfunktionen ---
def run_unmined(map_name):
    """Führt den unmined-cli Prozess sicher aus."""
    dimension_mapping = {
        "world": "overworld",
        "nether": "nether",
        "end": "end",
    }
    dimension = dimension_mapping.get(map_name)
    if not dimension:
        return False, ["Invalid map name specified."]

    output_path = os.path.join(MAP_OUTPUT_BASE_PATH, map_name)
    os.makedirs(
        output_path, exist_ok=True
    )  # Sicherstellen, dass das Verzeichnis existiert

    command = [
        UNMINED_CLI_PATH,
        "web",
        "render",
        f"--world={MINECRAFT_WORLD_PATH}",
        f"--dimension={dimension}",
        "--shadows=3d",
        "--background=#191919",
        "--zoomout=4",
        "--zoomin=2",
        # WICHTIG: Sicherstellen, dass der Pfad korrekt formatiert ist und mit einem Backslash endet, falls nötig.
        # subprocess unter Windows kann manchmal Probleme mit Pfaden ohne abschließenden Backslash haben.
        # os.path.join fügt normalerweise keinen hinzu, wenn das letzte Element ein Dateiname ist.
        # Da output_path ein Verzeichnis ist, sollte es okay sein, aber zur Sicherheit prüfen.
        # Für unmined ist es wahrscheinlich besser *ohne* Backslash am Ende. Testen!
        f"--output={output_path}",
    ]

    if map_name == "world":
        command.extend(["--centerx=550", "--centerz=750"])
    else:
        command.extend(["--centerx=0", "--centerz=0"])
    if map_name == "nether":
        command.extend(["--topY=72"])

    print(f"Running command: {' '.join(command)}")  # Logging für den Server-Admin

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",  # Explizit Encoding angeben
            errors="replace",  # Umgang mit fehlerhaften Zeichen
        )

        stdout_lines = []
        stderr_lines = []

        # Output lesen (non-blocking wäre besser, aber für einfache Zwecke reicht das)
        for line in process.stdout:
            print(f"STDOUT: {line.strip()}")  # Loggen
            stdout_lines.append(line.strip())
        for line in process.stderr:
            print(f"STDERR: {line.strip()}")  # Loggen
            stderr_lines.append(line.strip())

        process.wait()

        if process.returncode == 0:
            # Nach erfolgreichem Rendern: Unmined HTML anpassen (optional, siehe unten)
            modify_unmined_html(map_name)
            return True, ["Map updated successfully."]  # Nur Erfolgsmeldung senden
        else:
            error_message = f"Command failed with error code: {process.returncode}"
            # Sende nur eine generische Fehlermeldung an den Client, logge Details serverseitig
            print(f"{error_message}\nStderr: {' '.join(stderr_lines)}")
            return False, [error_message, "Check server logs for details."]

    except FileNotFoundError:
        print(f"Error: {UNMINED_CLI_PATH} not found.")
        return False, ["Error: Unmined CLI executable not found on server."]
    except Exception as e:
        print(f"Error running unmined-cli: {str(e)}")
        return False, [f"An unexpected error occurred during map update: {str(e)}"]


def add_marker_safely(map_name, marker_data):
    """Fügt einen Marker sicher zur custom.markers.js hinzu."""
    if map_name not in ["world", "nether", "end"]:
        return False, "Invalid map name."
    if not all(k in marker_data for k in ("x", "z", "text")):
        return False, "Missing marker data (x, z, text)."
    if not isinstance(marker_data["x"], int) or not isinstance(marker_data["z"], int):
        return False, "Invalid coordinates, must be integers."
    if not marker_data["text"] or len(marker_data["text"]) > 32:
        return False, "Marker text cannot be empty or longer than 32 characters."

    marker_file_path = os.path.join(
        MAP_OUTPUT_BASE_PATH, map_name, "unmined.custom.markers.js"
    )  # Korrekter Dateiname? Prüfen! Oft ist es 'unmined.custom.markers.js'

    # -- Sicherere Methode: JSON laden/speichern (angenommen, die Struktur ist nah genug) --
    try:
        markers_obj = {"isEnabled": True, "markers": []}
        if os.path.exists(marker_file_path):
            with open(marker_file_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Versuchen, den JS-Teil zu extrahieren und als JSON zu parsen
                # Das ist immer noch etwas heikel, da es kein echtes JSON ist.
                try:
                    # Finde den Start des Arrays '[' und das Ende ']'
                    start = content.find("[")
                    end = content.rfind("]")
                    if start != -1 and end != -1:
                        json_str = content[start : end + 1]
                        # Ersetze JS-spezifische Dinge (z.B. einfache Anführungszeichen, Kommentare) - kann komplex werden!
                        # Einfacher Ansatz: Nur das Array parsen
                        parsed_markers = json.loads(json_str)
                        if isinstance(parsed_markers, list):
                            markers_obj["markers"] = parsed_markers
                    # Wenn Parsen fehlschlägt oder Datei leer/Default ist, bleibt markers_obj leer
                except json.JSONDecodeError as e:
                    print(
                        f"Could not parse existing markers file {marker_file_path} as JSON: {e}. Starting fresh."
                    )
                    # Optional: Backup der alten Datei erstellen
                    # os.rename(marker_file_path, marker_file_path + ".bak")

        # Neuen Marker hinzufügen (mit Bereinigung!)
        new_marker = {
            "x": marker_data["x"],
            "z": marker_data["z"],
            # WICHTIG: HTML/JS-Sonderzeichen im Text escapen!
            "text": html.escape(
                marker_data["text"]
            ),  # html.escape schützt vor HTML-Injection/XSS
            "textColor": "#191919",
            "font": "bold 20px Arial,Calibri,sans serif",
        }
        markers_obj["markers"].append(new_marker)

        # JS-Datei neu schreiben (Format beibehalten)
        # Vorsicht: json.dumps erzeugt doppelte Anführungszeichen. Unmined erwartet das vielleicht nicht.
        # Wir müssen das manuell formatieren, um näher am Original zu sein, oder hoffen, dass Unmined flexibel ist.
        output_js = "UnminedCustomMarkers = {\n    isEnabled: true,\n    markers: "
        # JSON schön formatiert ausgeben
        output_js += json.dumps(markers_obj["markers"], indent=4)
        output_js += "\n};"

        # Ersetze doppelte durch einfache Anführungszeichen, falls Unmined das braucht (Testen!)
        # output_js = output_js.replace('"', "'") # Kann Probleme verursachen, wenn Text Anführungszeichen enthält! Besser bei " bleiben.

        with open(marker_file_path, "w", encoding="utf-8") as f:
            f.write(output_js)

        return True, "Marker added successfully."

    except Exception as e:
        print(f"Error adding marker: {str(e)}")
        return False, f"An unexpected error occurred while adding marker: {str(e)}"


# Optional: Funktion zum Modifizieren der Unmined index.html *nach* dem Generieren
def modify_unmined_html(map_name):
    """Fügt das Coordinate-Capture-Script zur Unmined index.html hinzu."""
    file_path = os.path.join(MAP_OUTPUT_BASE_PATH, map_name, "index.html")
    if not os.path.exists(file_path):
        print(f"Warning: Could not find {file_path} to modify.")
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Prüfen, ob das Script schon da ist
        if "window.parent.postMessage" in content:
            print(f"Coordinate script already present in {file_path}.")
            return

        coordinate_script = """
        <script>
function sendCoordinates() {
    console.log('Attempting to get coordinates...');
    const mousePositionDiv = document.querySelector('.ol-mouse-position');
    if (mousePositionDiv) {
        const coordsText = mousePositionDiv.textContent.trim();
        const match = coordsText.match(/(-?\d+)\s*,\s*(-?\d+)/);
        if (match && match.length === 3) {
            const x = parseInt(match[1], 10);
            const z = parseInt(match[2], 10);
            if (!isNaN(x) && !isNaN(z)) {
                console.log(`Coordinates found: x=${x}, z=${z}. Posting message to parent...`);
                // Sende Nachricht AN das Parent-Fenster (Hauptseite)
                window.parent.postMessage({
                    type: 'coordinates',
                    coords: { x, z }
                }, '*'); // Anpassen für mehr Sicherheit bei Bedarf
            } else { console.error('Failed to parse coordinates as numbers.'); }
        } else { console.warn('Could not match coordinates pattern in:', coordsText); }
    } else { console.warn('Could not find .ol-mouse-position div.'); }
}

// Listener für Nachrichten vom Hauptfenster
window.addEventListener('message', (event) => {
    // Optional: Sicherheitsprüfung der Herkunft (event.origin)
    // if (event.origin !== 'http://localhost') return; // Beispiel

    if (event.data && event.data.type === 'requestCoordinates') {
        sendCoordinates(); // Funktion aufrufen, um Koordinaten zu senden
    }
});

document.addEventListener('keydown', (event) => {
    if (event.ctrlKey && (event.key === 'c' || event.key === 'C')) {
        event.preventDefault();
        sendCoordinates(); // Dieselbe Funktion aufrufen
    }
});
</script>
        """
        # Füge das Script vor dem schließenden </body> Tag ein
        if "</body>" in content:
            modified_content = content.replace(
                "</body>", coordinate_script + "\n</body>", 1
            )
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(modified_content)
            print(f"Coordinate script added to {file_path}.")
        else:
            print(f"Warning: Could not find </body> tag in {file_path}.")

    except Exception as e:
        print(f"Error modifying {file_path}: {str(e)}")


ACTION_SECRET = "xxx"


def check_secret(handler):
    """Prüft das Secret im 'X-Action-Secret' Header."""
    submitted_secret = handler.headers.get("X-Action-Secret")  # Header holen

    if submitted_secret == ACTION_SECRET:
        return True
    else:
        print(
            f"Unauthorized action attempt on {handler.path}. Submitted secret via header: '{submitted_secret}'"
        )
        handler._send_json({"error": "Unauthorized - Invalid Secret"}, status=401)
        return False


class MyHandler(BaseHTTPRequestHandler):
    """Handler für dynamische API-Anfragen."""

    # --- Hilfsmethoden ---
    def _send_json(self, data, status=200):
        """Sendet eine JSON-Antwort."""
        try:
            content = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            # CORS Header (wichtig, wenn Frontend und Backend auf unterschiedlichen Ports/Domains laufen würden)
            # Nginx kann das auch global setzen
            self.send_header(
                "Access-Control-Allow-Origin", "*"
            )  # Anpassen für mehr Sicherheit
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            # Log error server-side
            print(f"Error sending JSON response: {e}")
            # Send a generic error response to the client
            try:
                # Try sending a minimal error response if headers weren't sent
                if not self.headers_sent:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                # If headers were sent, we might not be able to send a body
                self.wfile.write(
                    json.dumps({"error": "Internal Server Error"}).encode("utf-8")
                )
            except Exception as E:
                print(f"Failed to send error JSON response {E}")

    def _check_auth(self):
        """Prüft den Secret Token im Header."""
        auth_header = self.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return False
        token = auth_header.split(" ")[1]
        return token == SECRET_TOKEN

    # --- Request Handler ---
    def do_GET(self):
        parsed_path = urlparse(self.path)
        query = parse_qs(parsed_path.query)

        if parsed_path.path == "/get_file_date":
            map_name = query.get("map", ["world"])[0]
            # Validierung des map_name
            if map_name not in ["world", "nether", "end"]:
                self._send_json({"error": "Invalid map name"}, status=400)
                return

            # Pfad zur *generierten* Datei, die das Änderungsdatum hat
            # unmined.map.regions.js ist eine gute Wahl, da sie oft aktualisiert wird
            file_path = os.path.join(
                MAP_OUTPUT_BASE_PATH, map_name, "unmined.map.regions.js"
            )

            if os.path.exists(file_path):
                mod_time = os.path.getmtime(file_path)
                formatted_time = datetime.fromtimestamp(mod_time).strftime(
                    "%d.%m.%Y %H:%M"
                )
                self._send_json({"last_updated": formatted_time})
            else:
                # Es ist normal, dass die Datei nicht existiert, bevor die Karte generiert wurde
                self._send_json({"last_updated": "Not generated yet"})
            return
        else:
            self._send_json({"error": "Not Found"}, status=404)

    def do_POST(self):
        parsed_path = urlparse(self.path)
        path_only = parsed_path.path

        if path_only in ["/update_map", "/add_marker"]:
            if not check_secret(self):  # Ruft die neue Header-Prüfung auf
                return

        # --- Endpunkte ---
        if path_only == "/update_map":
            try:
                content_length = int(self.headers["Content-Length"])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data)
                map_name = data.get("map", "world")

                if map_name not in ["world", "nether", "end"]:
                    self._send_json({"error": "Invalid map name"}, status=400)
                    return

                success, messages = run_unmined(map_name)

                if success:
                    self._send_json({"message": "\n".join(messages)})
                else:
                    # Sende nur generische Fehlermeldung an Client
                    self._send_json({"error": "\n".join(messages)}, status=500)

            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON data"}, status=400)
            except Exception as e:
                print(f"Error in /update_map: {str(e)}")
                self._send_json(
                    {"error": f"Internal server error: {str(e)}"}, status=500
                )

        elif path_only == "/add_marker":
            try:
                content_length = int(self.headers["Content-Length"])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data)
                map_name = data.get("map", "world")
                marker_data = data.get("marker")  # Enthält x, z, text

                if not marker_data:
                    self._send_json({"error": "Missing marker data"}, status=400)
                    return

                # Versuche, Koordinaten in Zahlen umzuwandeln
                try:
                    marker_data["x"] = int(marker_data["x"])
                    marker_data["z"] = int(marker_data["z"])
                except (ValueError, TypeError):
                    self._send_json({"error": "Invalid coordinates"}, status=400)
                    return

                success, message = add_marker_safely(map_name, marker_data)

                if success:
                    self._send_json({"message": message})
                else:
                    self._send_json({"error": message}, status=500)

            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON data"}, status=400)
            except Exception as e:
                print(f"Error in /add_marker: {str(e)}")
                self._send_json(
                    {"error": f"Internal server error: {str(e)}"}, status=500
                )

        else:
            self._send_json({"error": "Not Found"}, status=404)

    # CORS Preflight Requests (optional, aber gut für die Entwicklung)
    def do_OPTIONS(self):
        self.send_response(204)  # No Content
        self.send_header("Access-Control-Allow-Origin", "*")  # Anpassen!
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type, Authorization"
        )  # Authorization hinzugefügt
        self.end_headers()


if __name__ == "__main__":
    # WICHTIG: Nur auf localhost binden, da Nginx der externe Einstiegspunkt ist!
    server_address = ("127.0.0.1", 8000)
    httpd = ThreadingHTTPServer(server_address, MyHandler)

    # Diese Einstellungen sind weniger relevant, wenn Nginx davor sitzt
    # httpd.daemon_threads = True
    # httpd.block_on_close = False
    # MyHandler.protocol_version = "HTTP/1.1"
    # MyHandler.close_connection = True # Nginx verwaltet die Connections

    print(f"Python backend listening on http://{server_address[0]}:{server_address[1]}")
    print(f"Ensure Nginx is configured to proxy requests to this backend.")
    print(f"SECRET_TOKEN for Authorization: Bearer {SECRET_TOKEN}")
    httpd.serve_forever()
