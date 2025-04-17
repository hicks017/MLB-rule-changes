"""
Objective:
------------
This script collects MLB game data over multiple seasons (2014-2024) by querying the official MLB stats API.
The libraries pybaseball and MLB-StatsAPI were unavailable at the time of creating this file, possibly due to changes in the MLB API formatting.
Therefore a script with fewer specialized libraries was required.

Specifically, this script:
1. Retrieves the schedule for each season to obtain the game identifiers.
2. Asynchronously fetches detailed game data for each game.
3. Extracts key metadata including the game datetime, game ID, team name, and the pitcher IDs used.
4. Aggregates the mean pitcher appearances in a game per team and per year.
5. Outputs a summarized CSV file with one row per team-year combination and the mean pitcher count.

Imported Libraries and Their Purposes:
----------------------------------------
- asyncio: Enables asynchronous programming, allowing concurrent HTTP requests to speed up data retrieval.
- aiohttp: Handles asynchronous HTTP requests to the MLB API endpoints, offering a non-blocking way to collect data.
- pandas: Facilitates data manipulation, aggregation, and exporting the final results into a CSV file.
- time: Used to measure and print the script's execution time for performance monitoring.

How the Script Works:
---------------------
1. For each season, the MLB schedule is fetched to extract a list of game primary keys (gamePk).
2. Using asyncio and aiohttp, the script sends concurrent HTTP requests to retrieve live feed data for each game.
3. From the live feed data, the script extracts the necessary metadata:
   - Game information (game ID from "gameData -> game -> pk" and the game datetime from "gameData -> datetime -> dateTime")
   - For each team in a game ("home" and "away"), the team name and a list of pitchers (pitcher IDs) are used.
4. The collected data is compiled into a list of records, then converted into a pandas DataFrame.
5. The DataFrame is grouped by team and year to summarize the mean number of pitcher appearances in a game per team per year.
6. The aggregated results are then saved to a CSV file, and the total processing time is printed at the end.

This script is designed to be run within a Docker container or any standard terminal environment, ensuring efficient data collection and processing.
"""
import asyncio
import aiohttp
import pandas as pd
import time

# Async function to fetch the live feed for a given game and extract pitcher IDs along with team info.
async def fetch_game_data(session, game_pk, semaphore):
    url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
    async with semaphore:
        try:
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

    game_pitcher_entries = []
    # Process both home and away team data
    for side in ["home", "away"]:
        team_data = teams.get(side, {})
        # Extract team name
        team_info = team_data.get("team", {})
        team_name = team_info.get("name")
        
        pitchers = team_data.get("pitchers", [])
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
    schedule_url = "https://statsapi.mlb.com/api/v1/schedule"
    params = {
        "sportId": 1, # MLB level of play
        "season": season,
        "gameTypes": "R"  # Only regular season games
    }
    try:
        async with session.get(schedule_url, params=params) as response:
            if response.status != 200:
                print(f"Failed to fetch schedule for season {season}. Status: {response.status}")
                return []
            schedule = await response.json()
    except Exception as e:
        print(f"Exception while fetching schedule for season {season}: {e}")
        return []
    
    game_pks = []
    for day in schedule.get("dates", []):
        for game in day.get("games", []):
            game_pk = game.get("gamePk")
            if game_pk:
                game_pks.append(game_pk)
    return game_pks

async def main():
    semaphore = asyncio.Semaphore(10)  # Limit concurrent requests to 10
    all_game_pitcher_data = []

    async with aiohttp.ClientSession() as session:
        for season in range(2014, 2014):
            print(f"Processing season {season}...")
            game_pks = await fetch_season_games(session, season)
            print(f"Found {len(game_pks)} games for season {season}")

            tasks = [fetch_game_data(session, game_pk, semaphore) for game_pk in game_pks]
            season_results = await asyncio.gather(*tasks)

            # Append results if available
            for result in season_results:
                if result is not None:
                    all_game_pitcher_data.extend(result)
    
    # Build a DataFrame from the collected records
    df = pd.DataFrame(all_game_pitcher_data)
    df['game_datetime'] = pd.to_datetime(df['game_datetime'])
    df['year'] = df['game_datetime'].dt.year

    # Aggregate grouped mean unique pitcher appearances
    game_pitcher_counts = (
        df.groupby(['team_name', 'year', 'game_id'])['pitcher_id']
          .nunique()
          .reset_index(name='pitcher_count')
    )
    avg_pitcher_counts = (
        game_pitcher_counts.groupby(['team_name', 'year'])['pitcher_count']
          .mean()
          .reset_index(name='avg_pitcher_count')
    )

    # Output data to CSV
    avg_pitcher_counts.to_csv("resources/data/pitchers_avg_per_team_year.csv", index=False)
    print("Data collection complete. Saved to 'pitchers_avg_per_team_year.csv'.")

# Run async function and report the elapsed time
if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(main())
    elapsed_time = time.time() - start_time
    print(f"Time elapsed: {elapsed_time:.2f} seconds")
