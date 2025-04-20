import asyncio
import aiohttp
import pandas as pd
import time
from tqdm import tqdm

# -------------------------------
# Constants
#
# BASE_URL: MLB stats API location for schedules
# LIVE_FEED_URL: MLB stats API live feed location for game details
# GAME_TYPES: S = Spring training, R = Regular season, P = Post season
# FIRST_SEASON: Year to start (included)
# LAST_SEASON: Year to end (not included)
# OUTPUT_FILE: File name and extension for export
# -------------------------------
BASE_URL = "https://statsapi.mlb.com/api/v1"
LIVE_FEED_URL = "https://statsapi.mlb.com/api/v1.1/game"
GAME_TYPES = "R"
FIRST_SEASON = 2014
LAST_SEASON = 2015
OUTPUT_FILE = "extra_innings_games.csv"
# -------------------------------

async def fetch_season_games(session, season, semaphore):
    """
    Fetch the MLB schedule for a given season and return unique game entries.
    Each entry is a dict with season and game_pk.
    """
    schedule_url = f"{BASE_URL}/schedule"
    params = {
        "sportId": 1,  # MLB
        "season": season,
        "gameTypes": GAME_TYPES
    }
    
    async with semaphore:
        try:
            async with session.get(schedule_url, params=params) as response:
                if response.status != 200:
                    print(f"Failed to fetch schedule for season {season}. Status: {response.status}")
                    return []
                data = await response.json()
        except Exception as e:
            print(f"Exception while fetching schedule for season {season}: {e}")
            return []
    
    # Extract unique game info from the schedule output.
    games = []
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            game_pk = game.get("gamePk")
            if game_pk:
                games.append({
                    "season": season,
                    "game_pk": game_pk
                })
    return games

async def fetch_game_details(session, game, semaphore):
    """
    Fetch game details (via the live feed) for a given game_pk.
    If the game went over 9 innings, extract and return the desired info:
    year, game_pk, team_winner, team_loser, final_inning.
    """
    game_pk = game["game_pk"]
    feed_url = f"{LIVE_FEED_URL}/{game_pk}/feed/live"
    
    async with semaphore:
        try:
            async with session.get(feed_url) as response:
                if response.status != 200:
                    print(f"Failed to fetch details for game_pk {game_pk}. Status: {response.status}")
                    return None
                data = await response.json()
        except Exception as e:
            print(f"Exception while fetching details for game_pk {game_pk}: {e}")
            return None

    try:
        innings = data["liveData"]["linescore"].get("innings", [])
        if len(innings) <= 9:
            return None  # Game did not go extra innings.
        
        final_inning = innings[-1].get("num", len(innings))
        
        # Extract team names from gameData.
        home_team = data["gameData"]["teams"]["home"]["name"]
        away_team = data["gameData"]["teams"]["away"]["name"]
        
        # Extract final runs from linescore.
        home_runs = data["liveData"]["linescore"]["teams"].get("home", {}).get("runs", 0)
        away_runs = data["liveData"]["linescore"]["teams"].get("away", {}).get("runs", 0)
        
        if home_runs > away_runs:
            team_winner = home_team
            team_loser = away_team
        else:
            team_winner = away_team
            team_loser = home_team
        
        return {
            "year": game["season"],
            "game_pk": game_pk,
            "team_winner": team_winner,
            "team_loser": team_loser,
            "final_inning": final_inning
        }
    except Exception as e:
        print(f"Error processing game_pk {game_pk}: {e}")
        return None

async def main():
    semaphore = asyncio.Semaphore(10)  # Limit concurrent HTTP requests.
    all_games = []

    async with aiohttp.ClientSession() as session:
        # Process seasons 2014 through 2024.
        season_tasks = []
        for season in range(FIRST_SEASON, LAST_SEASON):
            print(f"Fetching schedule for season {season}...")
            season_tasks.append(fetch_season_games(session, season, semaphore))
        
        seasons_results = await asyncio.gather(*season_tasks)
        for season_games in seasons_results:
            if season_games:
                all_games.extend(season_games)

        if not all_games:
            print("No games found in schedules.")
            return
        
        print(f"Total games found: {len(all_games)}. Fetching game details...")
        # Launch detail tasks for each game and wrap them with a progress bar.
        detail_tasks = [asyncio.create_task(fetch_game_details(session, game, semaphore))
                        for game in all_games]
        
        results = []
        for fut in tqdm(asyncio.as_completed(detail_tasks), total=len(detail_tasks)):
            res = await fut
            if res:
                results.append(res)
    
    if not results:
        print("No extra inning games found.")
        return
    
    # Build the DataFrame with the selected columns.
    df = pd.DataFrame(results)
    df = df[["year", "game_pk", "team_winner", "team_loser", "final_inning"]]
    
    # Export the results to CSV.
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"Data collection complete. Extra inning games saved to '{OUTPUT_FILE}'.")
    print(df.head())

if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(main())
    elapsed_time = time.time() - start_time
    print(f"Time elapsed: {elapsed_time:.2f} seconds")
