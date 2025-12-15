from fastapi import FastAPI, HTTPException
from datetime import date
import httpx
import asyncio

app = FastAPI()

MLB_STATS_BASE = "https://statsapi.mlb.com/api/v1/schedule"
MLB_LIVE_FEED = "https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live"
METS_TEAM_ID = 121  # New York Mets team ID in MLB API :contentReference[oaicite:1]{index=1}

@app.get("/mets/today")
async def get_mets_game_today():
    #today = date.today().isoformat()
    today = "2025-09-19"
    params = {
        "sportId": 1,        # MLB
        "startDate": today,
        "endDate": today
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(MLB_STATS_BASE, params=params)
        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail="Error fetching MLB schedule")

        data = resp.json()

    # Extract dates list
    dates = data.get("dates", [])
    if not dates:
        return {"message": "No MLB games today", "date": today}

    # Find games for the Mets
    mets_games = []
    for game in dates[0].get("games", []):
        teams = game.get("teams", {})
        home = teams.get("home", {})
        away = teams.get("away", {})

        if home.get("team", {}).get("id") == METS_TEAM_ID or away.get("team", {}).get("id") == METS_TEAM_ID:
            mets_games.append(game)

    if not mets_games:
        return {"message": "No Mets games today", "date": today}

    return {"date": today, "metsGames": mets_games}

@app.get("/mets/watch-homer/{gamePk}")
async def watch_mets_home_run(
    gamePk: int,
    poll_seconds: int = 300
):
    """
    Polls live game data every 5 seconds to detect Mets home runs.
    Stops when:
      - A Mets HR is detected
      - poll_seconds is exceeded (default 5 minutes)
    """

    seen_play_ids = set()
    elapsed = 0

    async with httpx.AsyncClient(timeout=10) as client:
        while elapsed < poll_seconds:
            r = await client.get(MLB_LIVE_FEED.format(gamePk=gamePk))
            if r.status_code != 200:
                raise HTTPException(status_code=500, detail="Live feed error")

            data = r.json()
            plays = data.get("liveData", {}).get("plays", {}).get("allPlays", [])

            for play in plays:
                play_id = play.get("playEvents", [{}])[0].get("playId")
                if play_id in seen_play_ids:
                    continue

                seen_play_ids.add(play_id)

                result = play.get("result", {})
                about = play.get("about", {})
                matchup = play.get("matchup", {})

                if result.get("eventType") == "home_run":
                    batter_team_id = matchup.get("battingTeam", {}).get("id")

                    if batter_team_id == METS_TEAM_ID:
                        return {
                            "home_run": True,
                            "gamePk": gamePk,
                            "inning": about.get("inning"),
                            "half": about.get("halfInning"),
                            "batter": matchup.get("batter", {}).get("fullName"),
                            "description": result.get("description")
                        }

            await asyncio.sleep(5)
            elapsed += 5

    return {
        "home_run": False,
        "gamePk": gamePk,
        "message": "No Mets home run detected in polling window"
    }
@app.get("/mets/homers/{gamePk}")
async def get_mets_home_runs(gamePk: int):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(MLB_LIVE_FEED.format(gamePk=gamePk))

    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Live feed error")

    data = r.json()

    plays = data.get("liveData", {}).get("plays", {}).get("allPlays", [])
    teams = data.get("gameData", {}).get("teams", {})

    home_id = teams.get("home", {}).get("id")
    away_id = teams.get("away", {}).get("id")

    mets_homers = []

    for play in plays:
        result = play.get("result", {})
        about = play.get("about", {})
        matchup = play.get("matchup", {})

        # ✅ Detect home run
        if result.get("eventType") != "home_run":
            continue

        # ✅ Determine batting team correctly
        half = about.get("halfInning")
        batting_team_id = away_id if half == "top" else home_id

        if batting_team_id == METS_TEAM_ID:
            mets_homers.append({
                "inning": about.get("inning"),
                "half": half,
                "batter": matchup.get("batter", {}).get("fullName"),
                "description": result.get("description")
            })

    return {
        "gamePk": gamePk,
        "total_mets_home_runs": len(mets_homers),
        "home_runs": mets_homers
    }
