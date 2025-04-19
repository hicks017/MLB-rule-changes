import asyncio
import aiohttp
import pandas as pd
import time

# -------------------------------
# Constants
# -------------------------------
BASE_URL = "https://statsapi.mlb.com/api/v1/"
SCHEDULE_ENDPOINT = f"{BASE_URL}schedule"
GAME_TYPES = "R"
FIRST_SEASON = 2014
LAST_SEASON = 2025
OUTPUT_FILE = "team_games_per_year.csv"
# -------------------------------
