import asyncio
import aiohttp
import pandas as pd
import time
from tqdm import tqdm

# -------------------------------
# Constants
#
# BASE_URL:      MLB stats API for schedules
# LIVE_FEED_URL: MLB stats API for live game data
# GAME_TYPES:    S = Spring training, R = Regular season, P = Post season
# FIRST_SEASON:  Year to start (inclusive)
# LAST_SEASON:   Year to end   (exclusive)
# OUTPUT_FILE:   CSV output filename
# -------------------------------
BASE_URL      = "https://statsapi.mlb.com/api/v1"
LIVE_FEED_URL = "https://statsapi.mlb.com/api/v1.1/game"
GAME_TYPES    = "R"
FIRST_SEASON  = 2014
LAST_SEASON   = 2025
OUTPUT_FILE   = "nl_ops.csv"

# National League ID in MLB API
NL_LEAGUE_ID  = 104

# Seasons with DH rule in NL
DH_SEASONS = {2020} | set(range(2022, LAST_SEASON))

# NL teams
NL_TEAM_IDS = {
    109, 144, 112, 113, 115, # AZ, ATL, CHC, CIN, COL
    119, 146, 158, 121, 143, # LAD, MIA, MIL, NYM, PHI
    134, 135, 137, 138, 120 # PIT, SD, SF, STL, WSH
}
# -------------------------------

async def fetch_season_games(session, season, sem):
    """Fetch all game PKs for a given season."""
    url = f"{BASE_URL}/schedule"
    params = {"sportId": 1, "season": season, "gameTypes": GAME_TYPES}
    async with sem:
        resp = await session.get(url, params=params)
        if resp.status != 200:
            print(f"[Season {season}] schedule error {resp.status}")
            return []
        data = await resp.json()
    games = []
    for date_entry in data.get("dates", []):
        for g in date_entry.get("games", []):
            home_team = g.get("teams", {}) \
                         .get("home", {}) \
                         .get("team", {}) \
                         .get("id")
            if home_team not in NL_TEAM_IDS:
                continue
            pk = g.get("gamePk")
            if pk:
                games.append({"season": season, "game_pk": pk})
    return games

async def fetch_and_compute_ops(session, info, sem):
    """
    Fetch live feed for game_pk, determine position ('P' or 'DH'),
    then compute OPS for that position among the home (NL) team.
    """
    season = info["season"]
    pk     = info["game_pk"]
    pos    = "DH" if season in DH_SEASONS else "P"
    url    = f"{LIVE_FEED_URL}/{pk}/feed/live"

    async with sem:
        resp = await session.get(url)
        if resp.status != 200:
            print(f"[Game {pk}] error {resp.status}")
            return None
        data = await resp.json()

    try:
        box = data["liveData"]["boxscore"]["teams"]["home"]
        gdt = data["gameData"]["datetime"].get("dateTime")
        batters = box["batters"]                # List of player IDs
        players = box["players"]                # List of player ID details

        # Initialize aggregates
        AB = H = BB = HBP = SF = TB = 0

        for pid in batters:
            pinfo = players.get(f"ID{pid}")
            if not pinfo:
                continue
            if pinfo["position"]["abbreviation"] != pos:
                continue
            stats = pinfo.get("stats", {}).get("batting", {})
            ab   = stats.get("atBats", 0)
            h    = stats.get("hits", 0)
            bb   = stats.get("baseOnBalls", 0)
            hbp  = stats.get("hitByPitch", 0)
            sf   = stats.get("sacrificeFlies", 0)
            dbls = stats.get("doubles", 0)
            trp  = stats.get("triples", 0)
            hr   = stats.get("homeRuns", 0)
            # Accumulate
            AB  += ab
            H   += h
            BB  += bb
            HBP += hbp
            SF  += sf
            # Total bases: singles + 2*doubles + 3*triples + 4*homerun
            singles = h - dbls - trp - hr
            TB += singles + 2*dbls + 3*trp + 4*hr

        # Calculate on-base percentage (OBP) and slugging (SLG)
        obp_denom = AB + BB + HBP + SF
        obp = (H + BB + HBP) / obp_denom if obp_denom > 0 else float("nan")
        slg = TB / AB if AB > 0 else float("nan")
        ops = obp + slg

        return {
            "year": season,
            "game_datetime": gdt,
            "game_pk": pk,
            "position": pos,
            "AB": AB,
            "OBP": round(obp, 3),
            "SLG": round(slg, 3),
            "OPS": round(ops, 3)
        }

    except Exception as e:
        print(f"[Game {pk}] processing error: {e}")
        return None

async def main():
    semaphore = asyncio.Semaphore(10)  # Limit concurrent HTTP requests.
    games = []

    async with aiohttp.ClientSession() as session:
        # Process seasons as defined.
        season_tasks = []
        for season in range(FIRST_SEASON, LAST_SEASON):
            print(f"Fetching schedule for season {season}...")
            season_tasks.append(fetch_season_games(session, season, semaphore))
        
        seasons_results = await asyncio.gather(*season_tasks)
        for season_games in seasons_results:
            if season_games:
                games.extend(season_games)

        if not games:
            print("No games found in schedules.")
            return
        
        print(f"Total games found: {len(games)}. Fetching game details...")
        # Launch detail tasks for each game and wrap them with a progress bar.
        detail_tasks = [asyncio.create_task(fetch_and_compute_ops(session, g, semaphore))
                        for g in games]
        
        results = []
        for fut in tqdm(asyncio.as_completed(detail_tasks), total=len(detail_tasks)):
            res = await fut
            if res:
                results.append(res)
    
    if not results:
        print("Error in results.")
        return

    # Build DataFrame & save
    df = pd.DataFrame(results, columns=["year", "game_datetime", "game_pk", "position", "AB", "OBP", "SLG", "OPS"])
    df.to_csv(OUTPUT_FILE, index=False)

    print(f"Data collection complete. Games saved to '{OUTPUT_FILE}'.")
    print(df.head())

# Run async functions and report the elapsed time.
if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(main())
    elapsed_time = time.time() - start_time
    print(f"Time elapsed: {elapsed_time:.2f} seconds")
