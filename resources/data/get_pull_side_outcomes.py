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
OUTPUT_FILE   = "pull_side_outcomes.csv"
# -------------------------------

# Pull‐side locations by batter hand
PULL_LOCATIONS = {
    "R": {"25", "5S", "56S", "15", "6S", "6MS", "5", "56", "6", "6M"},
    "L": {"23", "3S", "34S", "13", "4S", "4MS", "3", "34", "4", "4M"},
}

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

async def fetch_pull_outcomes(session, info, sem):
    """
    For a given game_pk, fetch allPlays and return only those where
    the ball was hit to the batter's pull side near the infield.
    Returns rows with:
      - season
      - game_datetime
      - game_pk
      - bat_side ("R" or "L")
      - hit_location (str)
      - play_outcome ("hit", "out", or "error")
    """
    season   = info["season"]
    pk       = info["game_pk"]
    url      = f"{LIVE_FEED_URL}/{pk}/feed/live"

    async with sem:
        resp = await session.get(url)
        if resp.status != 200:
            print(f"[Game {pk}] live feed error: {resp.status}")
            return []
        data = await resp.json()

    # game start datetime
    game_dt = data.get("gameData", {}) \
                  .get("datetime", {}) \
                  .get("dateTime")

    records = []
    for play in data.get("liveData", {}) \
                    .get("plays", {}) \
                    .get("allPlays", []):
        # batter hand: "R" or "L"
        bat_side = play.get("matchup", {}) \
                       .get("batSide", {}) \
                       .get("code")
        if bat_side not in PULL_LOCATIONS:
            continue

        # look for any playEvent with matching pull-side location
        for ev in play.get("playEvents", []):
            hit_data = ev.get("hitData", {})
            loc      = hit_data.get("location")
            if loc is None:
                continue

            loc_str = str(loc)
            if loc_str not in PULL_LOCATIONS[bat_side]:
                continue

            # classify outcome from play-level result
            evt_id = play.get("result", {}) \
                         .get("eventType", "")
            if evt_id in {"single", "double", "triple", "home_run", "fielders_choice"}:
                outcome = "hit"
            elif evt_id in {"field_error", "error"}:
                outcome = "error"
            elif evt_id in {"double_play", "field_out", "fielders_choice_out", "force_out", "grounded_into_double_play", "grounded_into_triple_play", "triple_play", "cs_double_play", "sac_fly", "sac_bunt", "sac_bunt_double_play"}:
                outcome = "out"
            else:
                outcome = "unknown"

            records.append({
                "season":        season,
                "game_datetime": game_dt,
                "game_pk":       pk,
                "bat_side":      bat_side,
                "hit_location":  loc_str,
                "play_outcome":  outcome
            })
            # one record per play
            break

    return records

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

        # 2) Fetch pull‐side outcomes for each game
        outcome_tasks = [
            asyncio.create_task(fetch_pull_outcomes(session, g, sem))
            for g in all_games
        ]

        all_records = []
        for fut in tqdm(asyncio.as_completed(outcome_tasks),
                        total=len(outcome_tasks),
                        desc="Processing games"):
            recs = await fut
            if recs:
                all_records.extend(recs)

    if not all_records:
        print("No pull-side plays found.")
        return

    # Build DataFrame & write CSV
    df = pd.DataFrame(all_records, columns=[
        "season",
        "game_datetime",
        "game_pk",
        "bat_side",
        "hit_location",
        "play_outcome"
    ])
    df.to_csv(OUTPUT_FILE, index=False)

    elapsed = time.time() - start_time
    print(f"Done: {len(df)} records → '{OUTPUT_FILE}' ({elapsed:.1f}s)")

if __name__ == "__main__":
    asyncio.run(main())
