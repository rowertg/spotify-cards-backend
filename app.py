import os, base64, re, io, csv
from typing import List, Dict, Any, Optional
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse, JSONResponse

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

app = FastAPI(title="Spotify Cards Backend", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

def extract_playlist_id(url: str) -> Optional[str]:
  m = re.search(r"playlist/([a-zA-Z0-9]+)", url)
  return m.group(1) if m else None

async def get_app_token() -> str:
  if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    raise HTTPException(status_code=500, detail="Spotify Credentials fehlen (Env Vars).")
  creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
  async with httpx.AsyncClient(timeout=20) as client:
    r = await client.post("https://accounts.spotify.com/api/token",
      headers={"Authorization": f"Basic {creds}",
               "Content-Type": "application/x-www-form-urlencoded"},
      data={"grant_type": "client_credentials"})
    if r.status_code != 200:
      raise HTTPException(status_code=502, detail=f"Token-Fehler: {r.text}")
    return r.json()["access_token"]

async def fetch_playlist_tracks(playlist_id: str, token: str, market: str="DE") -> List[Dict[str, Any]]:
  url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks?market={market}&limit=100&offset=0"
  rows: List[Dict[str, Any]] = []
  async with httpx.AsyncClient(timeout=30) as client:
    while url:
      r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
      if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=f"Spotify API: {r.text}")
      data = r.json()
      for it in data.get("items", []):
        t = it.get("track")
        if not t or t.get("type") != "track":
          continue
        artists = ", ".join(a.get("name","") for a in (t.get("artists") or []))
        year = (t.get("album", {}).get("release_date") or "")[:4]
        title = t.get("name", "")
        link = t.get("external_urls", {}).get("spotify", "")
        rows.append({"Artist": artists, "Year": year, "Title": title, "Link": link})
      url = data.get("next")
  return rows

def rows_to_csv(rows: List[Dict[str, Any]]) -> str:
  out = io.StringIO()
  w = csv.writer(out, quoting=csv.QUOTE_ALL)
  w.writerow(["Artist","Year","Title","Link"])
  for r in rows:
    w.writerow([r.get("Artist",""), r.get("Year",""), r.get("Title",""), r.get("Link","")])
  return out.getvalue()

@app.get("/", response_class=PlainTextResponse)
def root():
  return ("OK: Spotify Cards Backend läuft.\n\n"
          "Nutzung:\n"
          "  /api/playlist.json?url=<spotify_playlist_url>&market=DE\n"
          "  /api/playlist.csv?url=<spotify_playlist_url>&market=DE\n")

@app.get("/api/playlist.json")
async def api_playlist_json(url: str = Query(...), market: str = Query("DE")):
  pid = extract_playlist_id(url)
  if not pid: raise HTTPException(status_code=400, detail="Ungültige Playlist-URL")
  token = await get_app_token()
  rows = await fetch_playlist_tracks(pid, token, market=market)
  return JSONResponse({"count": len(rows), "rows": rows})

@app.get("/api/playlist.csv")
async def api_playlist_csv(url: str = Query(...), market: str = Query("DE")):
  pid = extract_playlist_id(url)
  if not pid: raise HTTPException(status_code=400, detail="Ungültige Playlist-URL")
  token = await get_app_token()
  rows = await fetch_playlist_tracks(pid, token, market=market)
  csv_text = rows_to_csv(rows)
  return StreamingResponse(io.StringIO(csv_text),
    media_type="text/csv",
    headers={"Content-Disposition": 'attachment; filename="songs.csv"'})
