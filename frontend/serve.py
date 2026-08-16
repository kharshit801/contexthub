"""Simple static file server for the frontend."""
import http.server
import socketserver
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

PORT = 3000
Handler = http.server.SimpleHTTPRequestHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Frontend serving at http://localhost:{PORT}")
    print(f"Make sure FastAPI backend is running at http://localhost:8000")
    httpd.serve_forever()
