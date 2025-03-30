import os
import json
import subprocess
import html
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import logging


# Basisverzeichnis des Skripts
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Pfade (Pfade auf dem Zielsystem prüfen!)
UNMINED_CLI_PATH = os.environ.get(
    "UNMINED_CLI_PATH",
    r"C:\Program Files\unmined\unmined-cli_0.19.47-dev_win-64bit\unmined-cli.exe",
)
MINECRAFT_WORLD_PATH = os.environ.get(
    "MC_WORLD_PATH", r"C:\Users\dNine\AppData\Roaming\.minecraft\saves\boyzTest"
)
MAP_OUTPUT_BASE_PATH = os.environ.get("MAP_OUTPUT_PATH", os.path.join(BASE_DIR, "maps"))

# Backend Server
BACKEND_HOST = "127.0.0.1"  # Nur lokal lauschen
BACKEND_PORT = 8000

# Sicherheit (Lade Secret aus Umgebungsvariable, mit sicherem Default nur für lokale Entwicklung)
ACTION_SECRET = os.environ.get("MAP_ACTION_SECRET", "xxx")

# Logging Konfiguration
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
# --------------------

# --- Hilfsfunktionen ---


def run_unmined(map_name):
    """Führt den unmined-cli Prozess sicher aus."""
    dimension_mapping = {"world": "overworld", "nether": "nether", "end": "end"}
    dimension = dimension_mapping.get(map_name)
    if not dimension:
        logging.error(f"Ungültiger map_name für Unmined: {map_name}")
        return False, "Invalid map name specified."  # Generische Meldung

    output_path = os.path.join(MAP_OUTPUT_BASE_PATH, map_name)
    os.makedirs(output_path, exist_ok=True)

    # Validiere Pfade (grundlegende Prüfung, ob sie existieren/erreichbar scheinen)
    if not os.path.exists(UNMINED_CLI_PATH):
        logging.error(f"Unmined CLI nicht gefunden: {UNMINED_CLI_PATH}")
        return False, "Internal server error (CLI missing)."
    if not os.path.isdir(MINECRAFT_WORLD_PATH):
        logging.error(f"Minecraft Welt nicht gefunden: {MINECRAFT_WORLD_PATH}")
        return False, "Internal server error (World missing)."

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
        f"--output={output_path}",
    ]
    center_coords = {
        "world": ("--centerx=550", "--centerz=750"),
        "nether": ("--centerx=0", "--centerz=0"),
        "end": ("--centerx=0", "--centerz=0"),
    }
    command.extend(center_coords.get(map_name, ("--centerx=0", "--centerz=0")))
    if map_name == "nether":
        command.extend(["--topY=72"])

    logging.info(f"Starte Unmined für Dimension '{dimension}'...")
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=(
                subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            ),  # Versteckt Konsolenfenster unter Windows
        )
        stdout, stderr = process.communicate(timeout=600)  # Timeout nach 10 Minuten

        if process.returncode == 0:
            logging.info(f"Unmined erfolgreich beendet für {map_name}.")
            modify_unmined_html(map_name)  # Script hinzufügen/prüfen
            return True, "Map updated successfully."
        else:
            error_message = f"Unmined-Prozess fehlgeschlagen (Code: {process.returncode}) für {map_name}."
            logging.error(error_message)
            if stderr:
                logging.error(f"Unmined STDERR:\n{stderr.strip()}")
            if stdout:
                logging.info(
                    f"Unmined STDOUT:\n{stdout.strip()}"
                )  # Info-Level für Stdout
            return (
                False,
                "Map update failed. Check server logs.",
            )  # Generische Fehlermeldung

    except subprocess.TimeoutExpired:
        logging.error(f"Unmined-Prozess Timeout für {map_name}.")
        process.kill()  # Prozess beenden
        stdout, stderr = process.communicate()  # Aufräumen
        return False, "Map update process timed out."
    except FileNotFoundError:
        logging.error(f"Unmined CLI nicht gefunden bei Ausführung: {UNMINED_CLI_PATH}")
        return False, "Internal server error (CLI execution failed)."
    except Exception as e:
        logging.exception(
            f"Unerwarteter Fehler beim Ausführen von Unmined für {map_name}"
        )  # Nutze logging.exception für Traceback
        return False, "An unexpected error occurred during map update."


def add_marker_safely(map_name, marker_data):
    """Fügt einen Marker sicher zur unmined.custom.markers.js hinzu."""
    if map_name not in ["world", "nether", "end"]:
        return False, "Invalid map name."
    if not all(k in marker_data for k in ("x", "z", "text")):
        return False, "Missing marker data."
    if not isinstance(marker_data["x"], int) or not isinstance(marker_data["z"], int):
        return False, "Invalid coordinates."
    text = marker_data.get("text", "")
    if not text or len(text) > 32:
        return False, "Invalid marker text (empty or > 32 chars)."

    marker_file_path = os.path.join(
        MAP_OUTPUT_BASE_PATH, map_name, "unmined.custom.markers.js"
    )

    try:
        markers_obj = {"isEnabled": True, "markers": []}
        if os.path.exists(marker_file_path):
            try:
                with open(marker_file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if (
                        content
                        and content.startswith("UnminedCustomMarkers")
                        and "[" in content
                    ):
                        start = content.find("[")
                        end = content.rfind("]")
                        if start != -1 and end != -1 and start < end:
                            json_str = content[start : end + 1]
                            json_str = re.sub(
                                r"//.*?\n", "\n", json_str
                            )  # Einfache Kommentare entfernen
                            json_str = re.sub(
                                r"/\*.*?\*/", "", json_str, flags=re.DOTALL
                            )
                            parsed_markers = json.loads(json_str)
                            if isinstance(parsed_markers, list):
                                markers_obj["markers"] = parsed_markers
            except (json.JSONDecodeError, FileNotFoundError) as e:
                logging.warning(
                    f"Konnte existierende Marker-Datei nicht parsen {marker_file_path}: {e}. Starte neu."
                )
            except Exception as e:
                logging.exception(
                    f"Fehler beim Lesen der Marker-Datei {marker_file_path}"
                )

        # Sanitize Text Input
        sanitized_text = html.escape(text)  # XSS Schutz!

        new_marker = {
            "x": marker_data["x"],
            "z": marker_data["z"],
            "text": sanitized_text,
            "textColor": "#191919",
            "font": "bold 20px Arial,Calibri,sans serif",
        }
        markers_obj["markers"].append(new_marker)

        # JS-Datei neu schreiben
        output_js = "UnminedCustomMarkers = {\n    isEnabled: true,\n    markers: "
        # Kompakteres JSON für Produktion, falls gewünscht (separators=(',', ':'))
        output_js += json.dumps(
            markers_obj["markers"], indent=4
        )  # Oder indent=None für kompakter
        output_js += "\n};"

        with open(marker_file_path, "w", encoding="utf-8") as f:
            f.write(output_js)
        logging.info(f"Marker erfolgreich zu {map_name} hinzugefügt.")
        return True, "Marker added successfully."

    except Exception as e:
        logging.exception(f"Fehler beim Hinzufügen des Markers zu {map_name}")
        return False, "An unexpected error occurred while adding marker."


def modify_unmined_html(map_name):
    """Fügt das Coordinate-Capture-Script zur Unmined index.html hinzu."""
    file_path = os.path.join(MAP_OUTPUT_BASE_PATH, map_name, "index.html")
    if not os.path.exists(file_path):
        logging.warning(f"Konnte {file_path} zum Modifizieren nicht finden.")
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Zuverlässigere Prüfung, ob das Kernstück des Scripts schon da ist
        if "requestCoordinates" in content and "sendCoordinates" in content:
            return  # Bereits vorhanden

        # Minimalisiertes Script für Produktion
        coordinate_script = """<script>function sendCoordinates(){const d=document.querySelector('.ol-mouse-position');if(d){const t=d.textContent.trim(),m=t.match(/(-?\\d+)\\s*,\\s*(-?\\d+)/);if(m&&m.length===3){const x=parseInt(m[1],10),z=parseInt(m[2],10);if(!isNaN(x)&&!isNaN(z))window.parent.postMessage({type:'coordinates',coords:{x:x,z:z}},'*')}}}window.addEventListener('message',(e)=>{if(e.data&&e.data.type==='requestCoordinates')sendCoordinates()});document.addEventListener('keydown',(e)=>{if(e.ctrlKey&&(e.key==='c'||e.key==='C')){e.preventDefault();sendCoordinates()}});</script>"""

        if "</body>" in content:
            modified_content = content.replace(
                "</body>", coordinate_script + "\n</body>", 1
            )
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(modified_content)
            logging.info(f"Koordinaten-Script zu {file_path} hinzugefügt/aktualisiert.")
        else:
            logging.warning(f"Konnte </body> Tag in {file_path} nicht finden.")

    except Exception as e:
        logging.exception(f"Fehler beim Modifizieren von {file_path}")


def check_secret(handler):
    """Prüft das Secret im 'X-Action-Secret' Header."""
    submitted_secret = handler.headers.get("X-Action-Secret")
    if (
        submitted_secret and submitted_secret == ACTION_SECRET
    ):  # Prüfe auch ob Secret nicht None ist
        return True
    else:
        # Logge fehlgeschlagenen Versuch serverseitig
        logging.warning(
            f"Ungültiger Secret-Versuch auf {handler.path} von {handler.client_address[0]}."
        )
        # Sende generische Fehlermeldung
        handler._send_json({"error": "Unauthorized"}, status=401)
        return False


# --- Request Handler Klasse ---
class MyHandler(BaseHTTPRequestHandler):
    """Handles API requests for map updates and information."""

    # Setze Server-Header auf etwas Unauffälliges
    server_version = "MapService/1.0"
    sys_version = ""

    # Überschreibe log_message für strukturiertes Logging
    def log_message(self, format, *args):
        logging.info("%s - %s" % (self.address_string(), format % args))

    def log_error(self, format, *args):
        logging.error("%s - %s" % (self.address_string(), format % args))

    def _send_json(self, data, status=200):
        """Sendet eine JSON-Antwort sicher."""
        try:
            content = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header(
                "Referrer-Policy", "no-referrer"
            )  # Sende keinen Referrer bei API-Antworten
            # Connection Header wird vom Server normalerweise automatisch gehandhabt
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            # Verhindere Senden von Fehlern, wenn Header schon gesendet wurden oder Socket zu ist
            if not self.wfile.closed:
                try:
                    self.wfile.close()
                except Exception:
                    pass
            logging.error(f"Konnte JSON-Antwort nicht senden: {e}")

    def do_GET(self):
        """Handles GET requests (read-only information)."""
        parsed_path = urlparse(self.path)
        path_only = parsed_path.path

        if path_only == "/get_file_date":
            query = parse_qs(parsed_path.query)
            map_name = query.get("map", ["world"])[0]
            if map_name not in ["world", "nether", "end"]:
                self._send_json({"error": "Bad Request"}, status=400)
                return  # Generisch
            file_path = os.path.join(
                MAP_OUTPUT_BASE_PATH, map_name, "unmined.map.regions.js"
            )
            if os.path.exists(file_path):
                try:
                    mod_time = os.path.getmtime(file_path)
                    formatted_time = datetime.fromtimestamp(mod_time).strftime(
                        "%d.%m.%Y %H:%M"
                    )
                    self._send_json({"last_updated": formatted_time})
                except OSError as e:
                    logging.error(
                        f"Fehler beim Lesen des Zeitstempels von {file_path}: {e}"
                    )
                    self._send_json({"error": "Internal Server Error"}, status=500)
            else:
                self._send_json({"last_updated": "Not generated yet"})
            return

        # elif path_only == "/get_player_count": # Falls benötigt
        #    ...
        #    return

        else:
            self._send_json({"error": "Not Found"}, status=404)

    def do_POST(self):
        """Handles POST requests (actions like update map, add marker)."""
        parsed_path = urlparse(self.path)
        path_only = parsed_path.path

        # --- Sicherheitsprüfung ---
        if path_only in ["/update_map", "/add_marker"]:
            if not check_secret(self):
                return  # Fehlerantwort gesendet

        # --- Endpunkt-Logik ---
        content_length_header = self.headers.get("Content-Length")
        if not content_length_header:
            self._send_json({"error": "Bad Request"}, status=400)
            return
        try:
            content_length = int(content_length_header)
            if content_length > 10 * 1024:  # Limit Request Body Size (z.B. 10KB)
                self._send_json({"error": "Payload Too Large"}, status=413)
                return
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)
        except (ValueError, json.JSONDecodeError):
            self._send_json({"error": "Bad Request"}, status=400)
            return
        except Exception as e:
            logging.exception("Fehler beim Lesen des POST-Bodys")
            self._send_json({"error": "Internal Server Error"}, status=500)
            return

        if path_only == "/update_map":
            map_name = data.get("map", "world")
            if map_name not in ["world", "nether", "end"]:
                self._send_json({"error": "Bad Request"}, status=400)
                return
            success, messages = run_unmined(map_name)
            if success:
                self._send_json({"message": messages[0]})  # Nur erste Nachricht
            else:
                self._send_json(
                    {"error": messages[0]}, status=500
                )  # Nur erste Nachricht

        elif path_only == "/add_marker":
            map_name = data.get("map", "world")
            marker_data = data.get("marker")
            if not marker_data or map_name not in ["world", "nether", "end"]:
                self._send_json({"error": "Bad Request"}, status=400)
                return
            try:  # Robuste Konvertierung
                marker_data["x"] = int(marker_data.get("x", ""))
                marker_data["z"] = int(marker_data.get("z", ""))
            except (ValueError, TypeError):
                self._send_json({"error": "Bad Request"}, status=400)
                return
            success, message = add_marker_safely(map_name, marker_data)
            if success:
                self._send_json({"message": message})
            else:
                self._send_json(
                    {"error": message}, status=500
                )  # Generische Fehlermeldung

        else:
            self._send_json({"error": "Not Found"}, status=404)


# --- Hauptteil ---
if __name__ == "__main__":
    server_address = (BACKEND_HOST, BACKEND_PORT)
    # Verwende ThreadingHTTPServer für bessere Performance bei gleichzeitigen Anfragen
    httpd = ThreadingHTTPServer(server_address, MyHandler)
    httpd.daemon_threads = True  # Erlaubt sauberes Beenden mit Strg+C

    logging.info(f"Python Backend lauscht auf http://{BACKEND_HOST}:{BACKEND_PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logging.info("Backend wird beendet.")
        httpd.server_close()
