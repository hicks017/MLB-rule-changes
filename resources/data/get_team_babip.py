import asyncio
import aiohttp
import pandas as pd
import time
from tqdm import tqdm

# -------------------------------
# Constants
#
# BASE_URL      : MLB stats API for team stats
# GAME_TYPES    : R = Regular season
# FIRST_SEASON  : Year to start (inclusive)
# LAST_SEASON   : Year to end   (exclusive)
# OUTPUT_FILE   : CSV output filename
# -------------------------------
BASE_URL     = "https://statsapi.mlb.com/api/v1"
GAME_TYPES   = "R"
FIRST_SEASON = 2014
LAST_SEASON  = 2025
OUTPUT_FILE  = "team_babip.csv"
# -------------------------------

async def fetch_season_team_babip(session, season, sem):
    """
    Fetch MLB team BABIP for a given season.
    Returns a list of dicts with:
      season, team_id, team_name, babip
    """
    url = f"{BASE_URL}/teams/stats"
    params = {
        "season":     season,
        "gameType":   GAME_TYPES,
        "stats":      "season",
        "group":  "hitting",
        "sportIds":   "1",            # MLB only
    }

    async with sem:
        resp = await session.get(url, params=params)
        if resp.status != 200:
            print(f"[Season {season}] stats error: {resp.status}")
            return []
        data = await resp.json()

    out = []
    for split in data.get("stats", [])[0].get("splits", []):
        team = split.get("team", {})
        stat = split.get("stat", {})
        # The API field name for BABIP is "babip"
        out.append({
            "season":    season,
            "team_id":   team.get("id"),
            "team_name": team.get("name"),
            "babip":     stat.get("babip", None)
        })
    return out

async def main():
    start_time = time.time()
    sem = asyncio.Semaphore(10)

    async with aiohttp.ClientSession() as session:
        # 1) One task per season
        tasks = [
            asyncio.create_task(fetch_season_team_babip(session, yr, sem))
            for yr in range(FIRST_SEASON, LAST_SEASON)
        ]

        # 2) Gather and flatten with a progress bar
        all_records = []
        for fut in tqdm(asyncio.as_completed(tasks),
                        total=len(tasks),
                        desc="Fetching BABIP by season"):
            recs = await fut
            if recs:
                all_records.extend(recs)

    if not all_records:
        print("No BABIP records found.")
        return

    # 3) Build DataFrame & write CSV
    df = pd.DataFrame(all_records, columns=[
        "season", "team_id", "team_name", "babip"
    ])
    df.to_csv(OUTPUT_FILE, index=False)

    elapsed = time.time() - start_time
    print(f"Done: {len(df)} rows → '{OUTPUT_FILE}' ({elapsed:.1f}s)")

if __name__ == "__main__":
    asyncio.run(main())
