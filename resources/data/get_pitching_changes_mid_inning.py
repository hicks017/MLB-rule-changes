import asyncio
import aiohttp
import pandas as pd
import time
from datetime import datetime
from tqdm import tqdm

# -------------------------------
# Constants
#
# BASE_URL_GAME: MLB stats API location for live game data
# BASE_URL_SCHEDULE: MLB stats API location for schedules
# GAME_TYPES: S = Spring training, R = Regular season, P = Post season
# FIRST_SEASON: Year to start (included)
# LAST_SEASON: Year to end (not included)
# OUTPUT_FILE: File name and extension for export
# -------------------------------
BASE_URL_GAME = "https://statsapi.mlb.com/api/v1.1"
BASE_URL_SCHEDULE = "https://statsapi.mlb.com/api/v1"
GAME_TYPES = "R"
FIRST_SEASON = 2014
LAST_SEASON = 2025
OUTPUT_FILE = "pitcher_changes.csv"
# -------------------------------

# Ensure datetime columns are in proper format.
def parse_iso_time(timestr):
    return datetime.fromisoformat(timestr.replace("Z", "+00:00"))

# Define function to identify and process mid-inning pitching changes.
def identify_mid_inning_pitching_changes(game_feed):
    events = []
    all_plays = game_feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
    game_data = game_feed.get("gameData", {})
    game_id = game_data.get("game", {}).get("pk")
    
    # Extract season year from game dateTime; if missing, year remains None.
    datetime_str = game_data.get("datetime", {}).get("dateTime")
    if datetime_str:
        game_dt = parse_iso_time(datetime_str)
        year = game_dt.year
    else:
        year = None

    # Determine team names from game data.
    teams = game_data.get("teams", {})
    home_team = teams.get("home", {}).get("name")
    away_team = teams.get("away", {}).get("name")
    
    prev_inning = None
    prev_half = None
    prev_pitcher = None

    # Process plays sequentially.
    for play in all_plays:
        about = play.get("about", {})
        inning = about.get("inning")
        isTopInning = about.get("isTopInning")
        
        # Get current pitcher id (if available) from the matchup field.
        current_pitcher = play.get("matchup", {}).get("pitcher", {}).get("id")
        
        # Look into the nested playEvents to see
        # if a pitching change is indicated.
        for pe in play.get("playEvents", []):
            details = pe.get("details", {})
            description = details.get("description", "").lower()
            if "pitching change" in description:
              
                # Only consider if it is truly a mid-inning event
                # and the pitcher has indeed changed.
                if (prev_inning is not None and inning == prev_inning and isTopInning == prev_half and
                    prev_pitcher is not None and current_pitcher is not None and prev_pitcher != current_pitcher):
                    
                    # Determine which team made the pitching change.
                    # If top half (away batting) then the home team is pitching.
                    team_name = home_team if isTopInning else away_team
                    events.append({
                        "game_id": game_id,
                        "year": year,
                        "team_name": team_name,
                        "pitcher_id_old": prev_pitcher,
                        "pitcher_id_new": current_pitcher
                    })
                    
                # Once a pitching change event is found in this play, move on.
                break
              
        # Update previous play details.
        prev_inning = inning
        prev_half = isTopInning
        if current_pitcher is not None:
            prev_pitcher = current_pitcher

    return events

# Async function to fetch the live feed for a given game
# and process identified pitching changes.
async def fetch_game_events(session, game_id, semaphore):
    url = f"{BASE_URL_GAME}/game/{game_id}/feed/live"
    async with semaphore:
        try:
            async with session.get(url) as response:
              
                # Handle unwanted status
                if response.status != 200:
                    print(f"Failed to fetch game {game_id}. Status: {response.status}")
                    return []
                data = await response.json()
        except Exception as e:
            print(f"Error fetching game {game_id}: {e}")
            return []
    return identify_mid_inning_pitching_changes(data)

# Async function to fetch game IDs for each season.
async def fetch_season_games(session, season):
    schedule_url = f"{BASE_URL_SCHEDULE}/schedule"
    params = {
        "sportId": 1, # MLB
        "season": season,
        "gameTypes": GAME_TYPES
    }
    try:
        async with session.get(schedule_url, params=params) as response:
          
            # Handle unwanted status.
            if response.status != 200:
                print(f"Failed to fetch schedule for season {season}. Status: {response.status}")
                return []
            schedule = await response.json()
    except Exception as e:
        print(f"Exception while fetching schedule for season {season}: {e}")
        return []
    
    game_ids = []
    for date_info in schedule.get("dates", []):
        for game in date_info.get("games", []):
            game_pk = game.get("gamePk")
            if game_pk:
                game_ids.append(str(game_pk))
    return game_ids

# Run tasks to fetch data.
async def main():
    semaphore = asyncio.Semaphore(10)  # Limit concurrent requests to 10.
    all_events = []

    async with aiohttp.ClientSession() as session:
        for season in range(FIRST_SEASON, LAST_SEASON):
            print(f"Processing season {season}...")
            game_ids = await fetch_season_games(session, season)
            print(f"Found {len(game_ids)} games for season {season}.")
            
            # Define the tasks for each game.
            tasks = [fetch_game_events(session, game_id, semaphore) for game_id in game_ids]
            
            # Use tqdm to track progress as tasks complete.
            season_results = []
            for task in tqdm(
                asyncio.as_completed(tasks), 
                total=len(tasks), 
                desc=f"Season {season} progress",
                dynamic_ncols=True
            ):
                result = await task
                season_results.append(result)
            
            # Extend our event list with non-empty results.
            for events in season_results:
                if events:
                    all_events.extend(events)

    # Handle empty entries.
    if not all_events:
        print("No mid-inning pitching change events detected.")
        return

    # Build a DataFrame from the list of event dictionaries.
    df_events = pd.DataFrame(all_events, columns=["game_id", "year", "team_name", "pitcher_id_old", "pitcher_id_new"])
    
    # Save the aggregated results to CSV.
    df_events.to_csv(OUTPUT_FILE, index=False)
    print(f"Results saved to '{OUTPUT_FILE}'.")

# Run async functions and report the elapsed time.
if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(main())
    elapsed_time = time.time() - start_time
    print(f"Time elapsed: {elapsed_time:.2f} seconds")
