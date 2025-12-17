from fastapi import FastAPI, HTTPException
import httpx
import asyncio
import time

app = FastAPI()

# ---------------- CONFIG ----------------
REPLAY_HOST = "http://127.0.0.1:8000"
POLL_INTERVAL = 1  # seconds

# Stores latest formatted output per gamePk
latest_formatted = {}

# Prevent duplicate at-bat processing
last_processed_atbat = {}

# ---------------- FORMATTER ----------------
def format_play(play, teams):
    result = play.get("result", {})
    about = play.get("about", {})

    return {
        "game": {
            "inning": {
                "half": about.get("halfInning"),
                "inning#": about.get("inning")
            },
            "score": {
                "awayScore": {
                    "team": teams["away"],
                    "score": result.get("awayScore")
                },
                "homeScore": {
                    "team": teams["home"],
                    "score": result.get("homeScore")
                }
            },
            "gameEvent": result.get("description")
        }
    }

# ---------------- BACKGROUND POLLER ----------------
async def poll_game(gamePk: int):
    endpoint = f"{REPLAY_HOST}/replay/game/{gamePk}/live"
    last_processed_atbat[gamePk] = -1

    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            try:
                r = await client.get(endpoint)
                r.raise_for_status()
                data = r.json()
            except Exception:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            if data.get("status") == "COMPLETE":
                break

            plays = data.get("allPlays", [])
            teams = data.get("teams", {})

            if not plays or not teams:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            last_play = plays[-1]
            result = last_play.get("result")

            if not result:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            atbat_index = last_play["about"]["atBatIndex"]

            if atbat_index == last_processed_atbat[gamePk]:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            last_processed_atbat[gamePk] = atbat_index
            latest_formatted[gamePk] = format_play(last_play, teams)

            await asyncio.sleep(POLL_INTERVAL)

# ---------------- API ENDPOINT ----------------
@app.get("/formatted/game/{gamePk}")
async def get_formatted_game(gamePk: int):
    # Start polling if not already running
    if gamePk not in latest_formatted:
        asyncio.create_task(poll_game(gamePk))
        return {
            "status": "INITIALIZING",
            "message": "Waiting for first completed at-bat"
        }

    return latest_formatted[gamePk]
