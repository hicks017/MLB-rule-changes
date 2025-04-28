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
OUTPUT_FILE  = "team_steals.csv"
# -------------------------------

async def fetch_season_team_stats(session, season, sem):
    """
    Fetch MLB team stolen-base stats for a given season.
    Returns a list of dicts with:
      season, team_id, team_name,
      stolen_bases, caught_stealing, sb_success_rate
    """
    url = f"{BASE_URL}/teams/stats"
    params = {
        "season":     season,
        "gameType":   GAME_TYPES,
        "stats":      "season",
        "group":  "hitting",
        "sportIds":   "1",            # ensure MLB only
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
        out.append({
            "season":           season,
            "team_id":          team.get("id"),
            "team_name":        team.get("name"),
            "stolen_bases":     stat.get("stolenBases", 0),
            "caught_stealing":  stat.get("caughtStealing", 0),
            "sb_success_rate":  stat.get("stolenBasePercentage"),
        })
    return out

async def main():
    start_time = time.time()
    sem = asyncio.Semaphore(10)

    async with aiohttp.ClientSession() as session:
        # 1) Schedule one task per season
        tasks = [
            asyncio.create_task(fetch_season_team_stats(session, yr, sem))
            for yr in range(FIRST_SEASON, LAST_SEASON)
        ]

        # 2) Gather results with tqdm
        all_records = []
        for fut in tqdm(asyncio.as_completed(tasks),
                        total=len(tasks),
                        desc="Fetching seasons"):
            recs = await fut
            if recs:
                all_records.extend(recs)

    if not all_records:
        print("No data returned.")
        return

    # 3) Build DataFrame & write CSV
    df = pd.DataFrame(all_records, columns=[
        "season", "team_id", "team_name",
        "stolen_bases", "caught_stealing", "sb_success_rate"
    ])
    df.to_csv(OUTPUT_FILE, index=False)

    elapsed = time.time() - start_time
    print(f"Done: {len(df)} rows → {OUTPUT_FILE} ({elapsed:.1f}s)")

if __name__ == "__main__":
    asyncio.run(main())
