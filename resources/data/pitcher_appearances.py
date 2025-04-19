import asyncio
import aiohttp
import pandas as pd
import time
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
OUTPUT_FILE = "pitcher_appearances.csv"
# -------------------------------

# Async function to fetch the live feed for a given game and extract pitcher IDs along with team info.
async def fetch_game_data(session, game_pk, semaphore):
    url = f"{BASE_URL_GAME}/game/{game_pk}/feed/live"
    async with semaphore:
        try:

            # Handle unwanted status
            async with session.get(url) as response:
                if response.status != 200:
                    print(f"Failed to fetch live feed for game {game_pk}. Status: {response.status}")
                    return None
                data = await response.json()
        except Exception as e:
            print(f"Exception for game {game_pk}: {e}")
            return None

    # Extract game ID and datetime
    game_data = data.get("gameData", {})
    game_info = game_data.get("game", {})
    game_id = game_info.get("pk")
    
    datetime_info = game_data.get("datetime", {})
    game_datetime = datetime_info.get("dateTime")
    
    if not game_id or not game_datetime:
        print(f"Missing game id or dateTime for game {game_pk}")
        return None

    # Navigate to the boxscore section for teams and their pitchers
    boxscore = data.get("liveData", {}).get("boxscore", {})
    teams = boxscore.get("teams", {})

    # Process both home and away team data
    game_pitcher_entries = []
    for side in ["home", "away"]:
        # Game and pitcher information
        team_data = teams.get(side, {})
        team_info = team_data.get("team", {})
        team_name = team_info.get("name")
        pitchers = team_data.get("pitchers", [])

        # Append one entry per pitcher ID
        for pitcher_id in pitchers:
            game_pitcher_entries.append({
                "game_datetime": game_datetime,
                "game_id": game_id,
                "pitcher_id": pitcher_id,
                "team_name": team_name
            })
    return game_pitcher_entries

# Async function to fetch all game primary keys (gamePk) for a given season.
async def fetch_season_games(session, season):
    schedule_url = f"{BASE_URL_SCHEDULE}/schedule"
    params = {
        "sportId": 1, # MLB level of play
        "season": season,
        "gameTypes": GAME_TYPES
    }
    try:
        async with session.get(schedule_url, params=params) as response:

            # Handle unwanted status
            if response.status != 200:
                print(f"Failed to fetch schedule for season {season}. Status: {response.status}")
                return []
            schedule = await response.json()
    except Exception as e:
        print(f"Exception while fetching schedule for season {season}: {e}")
        return []

    # Compile list of game IDs
    game_pks = []
    for day in schedule.get("dates", []):
        for game in day.get("games", []):
            game_pk = game.get("gamePk")
            if game_pk:
                game_pks.append(game_pk)
    return game_pks

# Run tasks to fetch data
async def main():
    semaphore = asyncio.Semaphore(10)  # Limit concurrent requests to 10
    all_game_pitcher_data = []

    async with aiohttp.ClientSession() as session:
        for season in range(FIRST_SEASON, LAST_SEASON):
            print(f"Processing season {season}...")
            game_pks = await fetch_season_games(session, season)
            print(f"Found {len(game_pks)} games for season {season}")

            tasks = [fetch_game_data(session, game_pk, semaphore) for game_pk in game_pks]
            
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
            
            # Extend the event list with non-empty results.
            for events in season_results:
                if events:
                    all_game_pitcher_data.extend(events)
    
    # Build a DataFrame from the collected records
    df = pd.DataFrame(all_game_pitcher_data)
    df['game_datetime'] = pd.to_datetime(df['game_datetime'])
    df['year'] = df['game_datetime'].dt.year
    
    # Output data to CSV
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"Data collection complete. Saved to '{OUTPUT_FILE}'.")

# Run async functions and report the elapsed time
if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(main())
    elapsed_time = time.time() - start_time
    print(f"Time elapsed: {elapsed_time:.2f} seconds")
