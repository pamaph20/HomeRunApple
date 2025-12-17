import logging
import copy
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MLB Play-by-Play Slicing Simulator")

# Store game state in memory
# { 
#   game_pk: { 
#     "full_plays": [], 
#     "total_events": int, 
#     "cursor": 0, 
#     "teams": {"home": str, "away": str}  <-- NEW
#   } 
# }
GAME_SESSIONS: Dict[int, Dict[str, Any]] = {}

MLB_API_BASE = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"

async def load_game_session(game_pk: int):
    """
    Fetches the completed game data once and extracts the list of Play Objects (allPlays) 
    AND the Home and Away team names.
    """
    url = MLB_API_BASE.format(game_pk=game_pk)
    logger.info(f"Fetching historical data for GamePK: {game_pk}")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        
    if response.status_code != 200:
        raise HTTPException(status_code=404, detail="Game not found")

    full_data = response.json()
    
    # --- 🎯 NEW: Extract Home and Away Team Names ---
    try:
        team_data = full_data.get("gameData", {}).get("teams", {})
        home_team_name = team_data.get("home", {}).get("name", "Unknown Home Team")
        away_team_name = team_data.get("away", {}).get("name", "Unknown Away Team")
    except Exception as e:
        logger.error(f"Could not extract team names: {e}")
        home_team_name = "Error Fetching Home Team"
        away_team_name = "Error Fetching Away Team"
    # --------------------------------------------------
    
    # Extract the full list of plays
    source_plays = full_data.get("liveData", {}).get("plays", {}).get("allPlays", [])
    
    # Calculate total events to set the bounds for our simulation
    total_events = sum(len(play.get("playEvents", [])) for play in source_plays)

    GAME_SESSIONS[game_pk] = {
        "full_plays": source_plays,
        "total_events": total_events,
        "cursor": 0,  # Represents total number of atomic events revealed so far
        "teams": {
            "home": home_team_name,
            "away": away_team_name
        }
    }
    logger.info(f"Session loaded. Total atomic events: {total_events}. Teams: {home_team_name} (H), {away_team_name} (A)")

@app.get("/replay/game/{game_pk}/live")
async def replay_game_plays(game_pk: int, reset: bool = False):
    """
    Returns an array of Play Objects (simulated allPlays array), 
    where only the current play's playEvents list is growing.
    
    The response now includes the 'teams' object at the root.
    """
    # 1. Initialize or Reset
    if reset or game_pk not in GAME_SESSIONS:
        await load_game_session(game_pk)
    
    session = GAME_SESSIONS[game_pk]
    
    # 2. Advance Time (Increment Cursor)
    if session["cursor"] < session["total_events"]:
        session["cursor"] += 1
    
    current_cursor = session["cursor"]
    
    # 3. Construct the "Time-Travel" array of plays (Logic remains the same)
    source_plays = session["full_plays"]
    simulated_plays = []
    events_processed = 0
    
    for play in source_plays:
        events_in_this_play = play.get("playEvents", [])
        num_events = len(events_in_this_play)
        
        # Scenario A: The cursor is past this entire play. (Play is COMPLETE)
        if events_processed + num_events <= current_cursor:
            simulated_plays.append(play)
            events_processed += num_events
            
        # Scenario B: The cursor is INSIDE this play. (Play is LIVE)
        elif events_processed < current_cursor < events_processed + num_events:
            partial_play = copy.deepcopy(play)
            
            # Calculate how many events from this play to show
            events_to_show = current_cursor - events_processed
            
            # Slice the playEvents array to simulate events happening
            partial_play["playEvents"] = events_in_this_play[:events_to_show]
            
            simulated_plays.append(partial_play)
            # Break here, as future plays haven't started yet
            break 
            
        # Scenario C: The cursor hasn't reached this play yet.
        else:
            break

    # 4. Final Response Structure
    response_data = {
        # --- 🎯 NEW: Include Teams at the Root ---
        "teams": session["teams"], 
        # ----------------------------------------
        "allPlays": simulated_plays,
        "current_cursor": current_cursor # For debugging
    }

    # Add the mandatory status flag when exhausted
    if current_cursor >= session["total_events"]:
        response_data["status"] = "COMPLETE"

    return response_data

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
