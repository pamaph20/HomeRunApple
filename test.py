import requests
import time
import json
import logging

# --- Configuration ---
HOST = "http://127.0.0.1:8000"
GAME_PK = "776259"
POLLING_INTERVAL = 1

ENDPOINT = f"{HOST}/replay/game/{GAME_PK}/live"

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')

# Store the last processed at-bat index to prevent repeated output
last_processed_at_bat_index = -1

# Dictionary to store team names globally once fetched
TEAM_NAMES = {"home": "Unknown Home", "away": "Unknown Away"}


def get_current_team_name(data, last_play):
    """
    Determines the name of the team currently batting based on the 'halfInning' 
    and the 'teams' object provided by the API.
    """
    global TEAM_NAMES
    
    # Update global team names if available in the current response (from root level)
    root_teams = data.get("teams", {})
    if root_teams.get("home") and root_teams.get("away"):
        TEAM_NAMES["home"] = root_teams["home"]
        TEAM_NAMES["away"] = root_teams["away"]

    # Determine which team is batting from the 'about' section of the play
    half_inning = last_play.get("about", {}).get("halfInning")
    
    if half_inning == "top":
        # Top of the inning = Away Team is batting
        return TEAM_NAMES["away"]
    elif half_inning == "bottom":
        # Bottom of the inning = Home Team is batting
        return TEAM_NAMES["home"]
    else:
        return "Unknown Team"


def fetch_and_process_game_data():
    """
    Fetches game data, determines the team batting, and prints the result 
    or "AT BAT IN PROGRESS" with the correct team name.
    """
    global last_processed_at_bat_index
    
    try:
        response = requests.get(ENDPOINT)
        response.raise_for_status()
        data = response.json()
        
    except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError, json.JSONDecodeError) as e:
        logging.error(f"Error fetching data: {e}")
        return

    # 1. Check for the 'status' flag (Game Complete)
    if data.get("status") == "COMPLETE":
        logging.info("--- GAME COMPLETE. Simulation finished. Exiting. ---")
        return False

    # 2. Locate the LAST Play Object
    all_plays = data.get("allPlays")
    if not isinstance(all_plays, list) or not all_plays:
        logging.info("Waiting for first play data.")
        return True

    last_play = all_plays[-1]
    
    # 3. Extract critical identification data
    play_result = last_play.get("result")
    at_bat_index = last_play.get("about", {}).get("atBatIndex")
    batter_name = last_play.get("matchup", {}).get("batter", {}).get("fullName", "Unknown Batter")
    
    # 4. Determine the Batting Team Name
    batting_team_name = get_current_team_name(data, last_play)

    # --- DECISION LOGIC ---

    if play_result:
        # At-bat is finished (result object exists)
        
        # Check if we've already printed this exact at-bat result
        if at_bat_index == last_processed_at_bat_index:
            return True
            
        description = play_result.get("description")
        
        if description:
            last_processed_at_bat_index = at_bat_index
            
            output_team_context = f"({batting_team_name})"

            # Check for Home Run on the final result
            if "Home Run" in description:
                print("\n" + "="*70)
                print(f"🎉 FINAL RESULT (At-Bat {at_bat_index}) {output_team_context}: HOME RUN! -> {description}")
                print("="*70 + "\n")
            else:
                logging.info(f"FINAL RESULT (At-Bat {at_bat_index}) {output_team_context}: {description}")
        
    else:
        # The 'result' field is missing, meaning the at-bat is still in progress
        pitch_count = len(last_play.get('playEvents', []))
        logging.info(f"Current At-Bat ({at_bat_index}) {batting_team_name} - {batter_name} (Pitch: {pitch_count}): AT BAT IN PROGRESS")
        
    return True

def main():
    """
    Main loop to poll the endpoint.
    """
    logging.info(f"Starting MLB Replay simulation against {ENDPOINT}...")

    continue_polling = True
    try:
        while continue_polling:
            continue_polling = fetch_and_process_game_data()
            if continue_polling:
                time.sleep(POLLING_INTERVAL)
    except KeyboardInterrupt:
        logging.info("Simulation stopped by user.")

if __name__ == "__main__":
    main()
