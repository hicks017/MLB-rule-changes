import asyncio
import aiohttp
import pandas as pd
import time

# -------------------------------
# Constants
#
# BASE_URL: MLB stats API location
# GAME_TYPES: S = Spring training, R = Regular season, P = Post season
# FIRST_SEASON: Year to start (included)
# LAST_SEASON: Year to end (not included)
# OUTPUT_FILE: File name and extension for export
# -------------------------------
BASE_URL = "https://statsapi.mlb.com/api/v1"
GAME_TYPES = "R"
FIRST_SEASON = 2014
LAST_SEASON = 2025
OUTPUT_FILE = "team_games_per_year.csv"
# -------------------------------

# Async function to fetch the schedule for a given season,
# extract each game’s teams, game id (gamePk), and game datetime.
async def fetch_season_games(session, season, semaphore):
    schedule_url = f"{BASE_URL}/schedule"
    params = {
        "sportId": 1,         # MLB
        "season": season,
        "gameTypes": GAME_TYPES
    }
    
    async with semaphore:
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
    
    # Gather desired data
    game_entries = []
    for day in schedule.get("dates", []):
        for game in day.get("games", []):
            
            # Extract game metadata
            game_pk = game.get("gamePk")
            game_datetime = game.get("gameDate")
            
            # Extract the away and home teams
            teams_data = game.get("teams", {})
            away_team = teams_data.get("away", {}).get("team", {}).get("name")
            home_team = teams_data.get("home", {}).get("team", {}).get("name")
                 
            # Append one entry per team appearance
            if away_team and game_pk:
                game_entries.append({
                    "team_name": away_team,
                    "game_datetime": game_datetime,
                    "season": season,
                    "game_pk": game_pk
                })
            if home_team and game_pk:
                game_entries.append({
                    "team_name": home_team,
                    "game_datetime": game_datetime,
                    "season": season,
                    "game_pk": game_pk
                })
    return game_entries

# Run tasks to fetch data
async def main():
    semaphore = asyncio.Semaphore(10)  # Limit concurrent schedule requests.
    all_game_entries = []

    async with aiohttp.ClientSession() as session:
      
        # Process seasons 2014 through 2024.
        tasks = []
        for season in range(FIRST_SEASON, LAST_SEASON):
            print(f"Processing season {season}...")
            tasks.append(fetch_season_games(session, season, semaphore))
        
        seasons_results = await asyncio.gather(*tasks)
        for result in seasons_results:
            if result is not None:
                all_game_entries.extend(result)
    
    # Handle empty entries
    if not all_game_entries:
        print("No game data collected.")
        return

    # Build a DataFrame and convert game_datetime to datetime objects.
    df = pd.DataFrame(all_game_entries)
    df['game_datetime'] = pd.to_datetime(df['game_datetime'], errors='coerce')
    df['year'] = df['game_datetime'].dt.year
    
    # Remove duplicate game records (if the same game_pk appears more than once for a team)
    df = df.drop_duplicates(subset=['team_name', 'season', 'game_pk'])
    
    # Group by team_name and season to count unique games played.
    game_counts = (
        df.groupby(['team_name', 'season'])
          .size()
          .reset_index(name='games_played')
    )

    # Output to CSV
    game_counts.to_csv(OUTPUT_FILE, index=False)
    print(f"Data collection complete. Saved to '{OUTPUT_FILE}'.")

if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(main())
    elapsed_time = time.time() - start_time
    print(f"Time elapsed: {elapsed_time:.2f} seconds")
