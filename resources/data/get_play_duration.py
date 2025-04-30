import asyncio
import aiohttp
import pandas as pd
import time
from tqdm import tqdm

# -------------------------------
# Constants
#
# BASE_URL      : MLB stats API for schedules
# LIVE_FEED_URL : MLB stats API for live game data
# GAME_TYPES    : S = Spring training, R = Regular season, P = Post season
# FIRST_SEASON  : Year to start (inclusive)
# LAST_SEASON   : Year to end   (exclusive)
# OUTPUT_FILE   : CSV output filename
# -------------------------------
BASE_URL      = "https://statsapi.mlb.com/api/v1"
LIVE_FEED_URL = "https://statsapi.mlb.com/api/v1.1/game"
GAME_TYPES    = "R"
FIRST_SEASON  = 2014
LAST_SEASON   = 2025
OUTPUT_FILE   = "play_duration.csv"
# -------------------------------

async def fetch_season_games(session, season, sem):
    """Fetch all regular-season games for a given season."""
    url = f"{BASE_URL}/schedule"
    params = {"sportId": 1, "season": season, "gameTypes": GAME_TYPES}

    async with sem:
        resp = await session.get(url, params=params)
        if resp.status != 200:
            print(f"[Season {season}] schedule error: {resp.status}")
            return []
        data = await resp.json()

    return [
        {"season": season, "game_pk": g["gamePk"]}
        for d in data.get("dates", [])
        for g in d.get("games", [])
        if g.get("gamePk")
    ]

async def fetch_play_durations(session, info, sem):
    """
    For a given game_pk, fetch allPlays and return only:
      - season
      - game_pk
      - startTime of each play
      - duration_sec between startTime and endTime
    """
    season = info["season"]
    pk     = info["game_pk"]
    url    = f"{LIVE_FEED_URL}/{pk}/feed/live"

    async with sem:
        resp = await session.get(url)
        if resp.status != 200:
            print(f"[Game {pk}] detail error: {resp.status}")
            return []
        data = await resp.json()

    results = []
    for play in data["liveData"]["plays"]["allPlays"]:
        about = play.get("about", {})
        start = about.get("startTime")
        end   = about.get("endTime")
        if not start or not end:
            continue

        start_ts = pd.to_datetime(start)
        duration = (pd.to_datetime(end) - start_ts).total_seconds()
        results.append({
            "season":       season,
            "game_pk":      pk,
            "startTime":    start_ts,
            "duration_sec": duration
        })
    return results

async def main():
    start_time = time.time()
    sem = asyncio.Semaphore(10)

    async with aiohttp.ClientSession() as session:
        # 1) Gather all games across seasons
        sched_tasks = [
            asyncio.create_task(fetch_season_games(session, yr, sem))
            for yr in range(FIRST_SEASON, LAST_SEASON)
        ]
        all_games = []
        for season_games in await asyncio.gather(*sched_tasks):
            all_games.extend(season_games)

        # 2) Fetch play startTimes & durations
        play_tasks = [
            asyncio.create_task(fetch_play_durations(session, g, sem))
            for g in all_games
        ]

        all_records = []
        for fut in tqdm(asyncio.as_completed(play_tasks),
                        total=len(play_tasks),
                        desc="Processing games"):
            recs = await fut
            if recs:
                all_records.extend(recs)

    if not all_records:
        print("No play records found.")
        return

    # Build DataFrame with only the retained columns
    df = pd.DataFrame(all_records, columns=[
        "season", "game_pk", "startTime", "duration_sec"
    ])
    df.to_csv(OUTPUT_FILE, index=False)

    elapsed = time.time() - start_time
    print(f"Done: {len(df)} records → '{OUTPUT_FILE}' ({elapsed:.1f}s)")

if __name__ == "__main__":
    asyncio.run(main())
