import os
import csv
import io
from urllib.parse import urlparse
from flask import Flask, request, Response, jsonify
import requests

app = Flask(__name__)

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")

def extract_playlist_id(url_or_id: str) -> str:
    if "open.spotify.com" in url_or_id:
        path = urlparse(url_or_id).path.strip("/")
        parts = path.split("/")
        if len(parts) >= 2 and parts[0] == "playlist":
            return parts[1]
        raise ValueError("Konnte Playlist-ID aus der URL nicht extrahieren.")
    return url_or_id

def get_access_token():
    r = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        timeout=15
    )
    r.raise_for_status()
    return r.json()["access_token"]

def first_release_year(track_obj):
    album = track_obj.get("album", {})
    date = album.get("release_date")
    return date.split("-")[0] if date else ""

def fetch_all_items(token, playlist_id):
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    params = {"limit": 100, "offset": 0}
    items = []
    while True:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        items.extend(data.get("items", []))
        if data.get("next"):
            url = data["next"]
            params = None
        else:
            break
    return items

@app.get("/api/playlist")
def playlist_to_csv():
    """
    GET /api/playlist?url=<playlist-url-or-id>
    Returns CSV with headers:
    Interpret,Release Year,Title,Spotify Song Link
    """
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        return jsonify(error="Missing SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET"), 500

    url_or_id = request.args.get("url", "").strip()
    if not url_or_id:
        return jsonify(error="Query param 'url' is required"), 400

    try:
        playlist_id = extract_playlist_id(url_or_id)
        token = get_access_token()
        items = fetch_all_items(token, playlist_id)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Interpret", "Release Year", "Title", "Spotify Song Link"])

        for it in items:
            tr = it.get("track") or {}
            if not tr:
                continue
            artists = tr.get("artists", [])
            interpret = ", ".join(a.get("name", "") for a in artists if a)
            title = tr.get("name", "")
            link = tr.get("external_urls", {}).get("spotify", "")
            year = first_release_year(tr)
            if not title and not interpret:
                continue
            writer.writerow([interpret, year, title, link])

        csv_data = output.getvalue()
        return Response(
            csv_data,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "inline; filename=playlist_cards.csv"}
        )
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.get("/health")
def health():
    return jsonify(status="ok")
