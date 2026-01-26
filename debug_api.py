import json
import os
import pymysql
from datetime import datetime
from database import get_daily_selections, get_connection

# Mock get_db_config to ensure it works in script
import database

print("--- Test 1: get_daily_selections(None) ---")
res1 = get_daily_selections(None)
print(f"Count: {len(res1)}")
if res1:
    print(f"Sample: {res1[0]['symbol']} Date: {res1[0]['selection_date']}")

print("\n--- Test 2: get_daily_selections('') ---")
res2 = get_daily_selections("")
print(f"Count: {len(res2)}")
if res2:
    print(f"Sample: {res2[0]['symbol']} Date: {res2[0]['selection_date']}")

print("\n--- Test 3: get_daily_selections('2026-01-21') ---")
res3 = get_daily_selections('2026-01-21')
print(f"Count: {len(res3)}")
if res3:
    print(f"Sample: {res3[0]['symbol']} Date: {res3[0]['selection_date']}")
