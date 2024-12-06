import os
import json
import subprocess
import gzip
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class MyHandler(SimpleHTTPRequestHandler):
    """HTTP request handler for serving Minecraft map files and handling map updates."""

    def do_GET(self):
        parsed_path = urlparse(self.path)
        query = parse_qs(parsed_path.query)

        # Get last modification time of map file
        if parsed_path.path == "/get_file_date":
            map_name = query.get("map", ["world"])[0]
            file_path = os.path.join(
                BASE_DIR, "maps", map_name, "unmined.map.regions.js"
            )

            if os.path.exists(file_path):
                mod_time = os.path.getmtime(file_path)
                formatted_time = datetime.fromtimestamp(mod_time).strftime(
                    "%d.%m.%Y %H:%M"
                )
                self._send_json({"last_updated": formatted_time})
            else:
                self._send_json({"error": "File not found"}, status=404)
            return

        # Load and modify map HTML with base tag and coordinate capture
        elif parsed_path.path == "/maps":
            map_name = query.get("map", ["world"])[0]
            file_path = os.path.join(BASE_DIR, "maps", map_name, "index.html")

            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    base_href = f'<base href="/maps/{map_name}/">'
                    coordinate_script = """
                    <script>
                    window.stop();
                    document.addEventListener('keydown', (event) => {
                        if (event.ctrlKey && event.key === 'c') {
                            const mousePositionDiv = document.querySelector('.ol-mouse-position');
                            if (mousePositionDiv) {
                                const coords = mousePositionDiv.textContent.trim().split(',');
                                if (coords.length === 2) {
                                    const [x, z] = coords.map(coord => parseInt(coord.trim(), 10));
                                    window.parent.postMessage({
                                        type: 'coordinates',
                                        coords: { x, z }
                                    }, '*');
                                }
                            }
                        }
                    });
                    </script>
                    """

                    lines = content.splitlines()
                    if len(lines) >= 6:
                        lines.insert(6, base_href)
                        body_end_idx = next(
                            i for i, line in enumerate(lines) if "</body>" in line
                        )
                        lines.insert(body_end_idx, coordinate_script)

                    modified_content = "\n".join(lines)

                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(modified_content.encode("utf-8"))
                except Exception as e:
                    self.send_error(500, f"Error loading map HTML: {str(e)}")
            else:
                self.send_error(404, "Map not found")

        # Serve static files
        elif parsed_path.path.startswith("/static/"):
            relative_file_path = parsed_path.path.lstrip("/")
            file_path = os.path.join(BASE_DIR, relative_file_path)

            if os.path.exists(file_path):
                self._serve_file(file_path)
            else:
                self.send_error(404, f"File not found: {relative_file_path}")

        # Serve additional map resources
        elif parsed_path.path.startswith("/maps/"):
            relative_file_path = parsed_path.path.lstrip("/")
            file_path = os.path.join(BASE_DIR, relative_file_path)

            if os.path.exists(file_path):
                self._serve_file(file_path)
            else:
                self.send_error(404, f"File not found: {relative_file_path}")

        # Serve main page
        elif self.path == "/" or self.path == "/index.html":
            file_path = os.path.join(BASE_DIR, "index.html")
            self._serve_file(file_path)

        else:
            self.send_error(404, "Invalid endpoint")

    def _serve_file(self, file_path):
        """Serve a file with proper headers and gzip compression."""
        try:
            self.send_response(200)

            self.send_header("Connection", "close")
            self.send_header("Cache-Control", "public, max-age=10")
            self.send_header("Vary", "Accept-Encoding")

            with open(file_path, "rb") as f:
                content = f.read()

            if "gzip" in self.headers.get("Accept-Encoding", ""):
                content = gzip.compress(content)
                self.send_header("Content-Encoding", "gzip")

            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            self.wfile.flush()

        except Exception as e:
            self.send_error(500, f"Error serving file: {str(e)}")

    def _send_json(self, data, status=200):
        """Send a JSON response with proper headers."""
        try:
            content = json.dumps(data).encode("utf-8")

            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "close")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()

            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error sending JSON: {str(e)}")

    def do_POST(self):
        """Handle POST requests for map updates."""
        if self.path == "/update_map":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)
            map_name = data.get("map", "world")

            try:
                # Map dimension names to Minecraft internal names
                dimension_mapping = {
                    "world": "overworld",
                    "nether": "nether",
                    "end": "end",
                }
                dimension = dimension_mapping.get(map_name, "overworld")

                # Output path based on dimension
                output_path = f"C:\\Users\\dNine\\DiscordMinecraftBot\\website\\maps\\{map_name}\\"

                # Command as list of arguments
                command = [
                    r"C:\Users\dNine\Desktop\unmined-cli_0.19.43-dev_win-64bit\unmined-cli.exe",
                    "web",
                    "render",
                    r"--world=C:\Users\dNine\AppData\Roaming\.minecraft\saves\boyzTest",
                    f"--dimension={dimension}",
                    "--shadows=3d",
                    "--background=#191919",
                    "--zoomout=4",
                    "--zoomin=2",
                    f"--output={output_path}",
                ]

                # Add center coordinates for Overworld
                if map_name == "world":
                    command.extend(["--centerx=550", "--centerz=750"])
                else:
                    command.extend(["--centerx=0", "--centerz=0"])
                if map_name == "nether":
                    command.extend(["--topY=72"])

                # print(f"Running command: {' '.join(command)}")

                # Start process and read output in real-time
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                # Collect progress
                output = []
                for line in process.stdout:
                    output.append(line.strip())
                    print(line.strip())

                # Wait for process to finish
                process.wait()

                if process.returncode == 0:
                    self._send_json(
                        {"message": "Map updated successfully", "output": output}
                    )
                else:
                    self._send_json(
                        {
                            "error": f"Command failed with error: {process.returncode}",
                            "output": output,
                        },
                        status=500,
                    )
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
        if self.path == "/add_marker":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)
            map_name = data.get("map", "world")
            marker = data.get("marker")
            marker_file_path = os.path.join(
                BASE_DIR, "maps", map_name, "custom.markers.js"
            )

            try:
                if not os.path.exists(marker_file_path):
                    self._send_json({"message": "No map found."})
                    return

                with open(marker_file_path, "r") as file:
                    content = file.read()

                # Check if file is default template
                if content.startswith("/*"):
                    with open(marker_file_path, "w") as file:
                        content = """UnminedCustomMarkers = {
        isEnabled: true,
        markers: [
        ]}"""
                        file.write(content)

                # Add new marker to existing content
                marker_end = content.rfind("]")
                new_marker = (
                    """{
                x: %(x)d,
                z: %(z)d,
                text: "%(text)s",
                textColor: "#191919", 
                font:"bold 20px Arial,Calibri,sans serif",
            },"""
                    % marker
                )

                updated_content = (
                    content[:marker_end] + new_marker + "\n" + content[marker_end:]
                )

                with open(marker_file_path, "w") as file:
                    file.write(updated_content)

                self._send_json({"message": "Marker added successfully."})

            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
        else:
            self._send_json({"error": "Invalid endpoint"}, status=404)


if __name__ == "__main__":
    server_address = ("0.0.0.0", 8000)
    httpd = ThreadingHTTPServer(server_address, MyHandler)

    # Enable threading optimizations
    httpd.daemon_threads = True
    httpd.block_on_close = False

    # Set HTTP protocol version and connection handling
    MyHandler.protocol_version = "HTTP/1.1"
    MyHandler.close_connection = True

    print(f"Server running on http://{server_address[0]}:{server_address[1]}")
    httpd.serve_forever()
