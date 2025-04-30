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
LAST_SEASON = 2025
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
        linescore = data["liveData"]["linescore"]
        innings   = linescore.get("innings", [])
        if len(innings) <= 9:
            return None  # Game did not go extra innings.

        # Final inning number
        final_inning = innings[-1].get("num", len(innings))

        # Total runs scored after the 9th
        total_extra_runs = sum(
            (inn.get("home", {}).get("runs", 0) +
             inn.get("away", {}).get("runs", 0))
            for inn in innings
            if inn.get("num", 0) > 9
        )

        # Count batters until first run in extras
        plays = data["liveData"]["plays"]["allPlays"]
        batters = 0
        batters_until_first_run = None
        for pl in plays:
            inn = pl["about"]["inning"]
            if inn <= 9:
                continue
            batters += 1
            rbi = pl["result"].get("rbi", 0)
            if rbi and batters_until_first_run is None:
                batters_until_first_run = batters
                break

        # Teams & winner/loser
        home = data["gameData"]["teams"]["home"]["name"]
        away = data["gameData"]["teams"]["away"]["name"]
        runs_home = linescore["teams"]["home"]["runs"]
        runs_away = linescore["teams"]["away"]["runs"]

        if runs_home > runs_away:
            winner, loser = home, away
        else:
            winner, loser = away, home

        # Game datetime
        gdt = data["gameData"]["datetime"].get("dateTime")

        return {
            "year": game["season"],
            "game_datetime": gdt,
            "game_pk":       game_pk,
            "team_winner":   winner,
            "team_loser":    loser,
            "final_inning":  final_inning,
            "batters_until_first_run": batters_until_first_run,
            "total_extra_runs": total_extra_runs
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
    df["game_datetime"] = pd.to_datetime(df["game_datetime"])
    df = df[[
        "year", "game_datetime", "game_pk",
        "team_winner", "team_loser", "final_inning",
        "total_extra_runs", "batters_until_first_run"
    ]]
    
    # Export the results to CSV.
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"Data collection complete. Extra inning games saved to '{OUTPUT_FILE}'.")
    print(df.head())

if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(main())
    elapsed_time = time.time() - start_time
    print(f"Time elapsed: {elapsed_time:.2f} seconds")
