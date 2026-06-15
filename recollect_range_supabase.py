"""
Recollect a missing SensorPush date range into Supabase.

Use this when Supabase is missing data for a specific period, for example a weekend.
It queries SensorPush one sensor at a time and in small chunks, then upserts rows into Supabase.

Required environment variables / GitHub secrets:
  SENSORPUSH_EMAIL
  SENSORPUSH_PASSWORD
  DATABASE_URL

Optional:
  RECOLLECT_START=2026-06-13       # local date or ISO time
  RECOLLECT_END=2026-06-16         # local date, ISO time, or now
  RECOLLECT_CHUNK_HOURS=12
  RECOLLECT_LIMIT=10000
  RECOLLECT_DELETE_EXISTING=0      # set to 1 to delete rows in the range first
  LOCAL_TIMEZONE=America/Toronto
"""

from __future__ import annotations

import os
import sys
import time
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import requests
import psycopg2
import psycopg2.extras

BASE_URL = "https://api.sensorpush.com/api/v1"

EMAIL = (os.environ.get("SENSORPUSH_EMAIL") or "").strip()
PASSWORD = (os.environ.get("SENSORPUSH_PASSWORD") or "").strip()
DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()
LOCAL_TIMEZONE = (os.environ.get("LOCAL_TIMEZONE") or "America/Toronto").strip() or "America/Toronto"

RECOLLECT_START = (os.environ.get("RECOLLECT_START") or "2026-06-13").strip()
RECOLLECT_END = (os.environ.get("RECOLLECT_END") or "now").strip()
RECOLLECT_CHUNK_HOURS = float(os.environ.get("RECOLLECT_CHUNK_HOURS") or "12")
RECOLLECT_LIMIT = int(os.environ.get("RECOLLECT_LIMIT") or "10000")
RECOLLECT_SLEEP_SECONDS = int(os.environ.get("RECOLLECT_SLEEP_SECONDS") or "65")
RECOLLECT_DELETE_EXISTING = (os.environ.get("RECOLLECT_DELETE_EXISTING") or "0").strip().lower() in {"1", "true", "yes", "y"}
MAX_SPLIT_DEPTH = int(os.environ.get("RECOLLECT_MAX_SPLIT_DEPTH") or "7")


def local_tz() -> dt.tzinfo:
    if ZoneInfo is not None:
        try:
            return ZoneInfo(LOCAL_TIMEZONE)
        except Exception:
            pass
    return dt.datetime.now().astimezone().tzinfo or dt.timezone.utc


def parse_time(value: str, *, end_of_day: bool = False) -> dt.datetime:
    value = value.strip()
    if not value or value.lower() == "now":
        return dt.datetime.now(dt.timezone.utc)
    tz = local_tz()
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        y, m, d = map(int, value.split("-"))
        if end_of_day:
            out = dt.datetime(y, m, d, 23, 59, 59, tzinfo=tz)
        else:
            out = dt.datetime(y, m, d, 0, 0, 0, tzinfo=tz)
        return out.astimezone(dt.timezone.utc)
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(dt.timezone.utc)


def sp_time(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def normalize_database_url(url: str) -> str:
    if not url:
        raise RuntimeError("Missing DATABASE_URL")
    url = url.strip().strip('"').strip("'")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def db_connect():
    return psycopg2.connect(normalize_database_url(DATABASE_URL))


def setup_database() -> None:
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id BIGSERIAL PRIMARY KEY,
                sensor_id TEXT NOT NULL,
                sensor_name TEXT,
                observed_at TIMESTAMPTZ,
                timestamp TIMESTAMPTZ,
                temperature_c DOUBLE PRECISION,
                humidity DOUBLE PRECISION,
                barometric_pressure_inhg DOUBLE PRECISION,
                pressure_mb DOUBLE PRECISION,
                voltage DOUBLE PRECISION,
                source TEXT DEFAULT 'sensorpush_recollect',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                stored_at TIMESTAMPTZ DEFAULT NOW()
            )
            """)
            for col_sql in [
                "ALTER TABLE readings ADD COLUMN IF NOT EXISTS observed_at TIMESTAMPTZ",
                "ALTER TABLE readings ADD COLUMN IF NOT EXISTS timestamp TIMESTAMPTZ",
                "ALTER TABLE readings ADD COLUMN IF NOT EXISTS pressure_mb DOUBLE PRECISION",
                "ALTER TABLE readings ADD COLUMN IF NOT EXISTS voltage DOUBLE PRECISION",
                "ALTER TABLE readings ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'sensorpush_recollect'",
                "ALTER TABLE readings ADD COLUMN IF NOT EXISTS stored_at TIMESTAMPTZ DEFAULT NOW()",
                "ALTER TABLE readings ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
            ]:
                cur.execute(col_sql)
            # In case the original schema made timestamp not-null but this script also uses observed_at.
            try:
                cur.execute("ALTER TABLE readings ALTER COLUMN timestamp DROP NOT NULL")
            except Exception:
                conn.rollback()
                with conn.cursor() as cur2:
                    cur2.execute("SELECT 1")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_readings_observed_at ON readings(observed_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_readings_sensor_observed_at ON readings(sensor_id, observed_at)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_readings_sensor_observed_unique ON readings(sensor_id, observed_at) WHERE observed_at IS NOT NULL")
        conn.commit()


def delete_existing_range(start: dt.datetime, end: dt.datetime) -> int:
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM readings WHERE observed_at >= %s AND observed_at < %s",
                (start, end),
            )
            deleted = cur.rowcount
        conn.commit()
    return int(deleted)


def sensorpush_post(endpoint: str, token: Optional[str], payload: Dict[str, Any], timeout: int = 120) -> Dict[str, Any]:
    headers = {"accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = token
    response = requests.post(f"{BASE_URL}{endpoint}", headers=headers, json=payload, timeout=timeout)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        print(f"HTTP error calling {endpoint}: {response.status_code}")
        print(response.text[:1000])
        raise
    return response.json()


def get_access_token() -> str:
    if not EMAIL or not PASSWORD:
        raise RuntimeError("Missing SENSORPUSH_EMAIL or SENSORPUSH_PASSWORD")
    auth = sensorpush_post("/oauth/authorize", None, {"email": EMAIL, "password": PASSWORD}, timeout=30)
    authorization = auth.get("authorization")
    if not authorization:
        raise RuntimeError("No authorization returned from SensorPush")
    access = sensorpush_post("/oauth/accesstoken", None, {"authorization": authorization}, timeout=30)
    token = access.get("accesstoken")
    if not token:
        raise RuntimeError("No accesstoken returned from SensorPush")
    return token


def get_sensors(token: str) -> Dict[str, Dict[str, Any]]:
    sensors = sensorpush_post("/devices/sensors", token, {}, timeout=30)
    if not isinstance(sensors, dict) or not sensors:
        raise RuntimeError("No sensors returned from SensorPush")
    return sensors


def get_samples(token: str, sensor_id: str, start: dt.datetime, stop: dt.datetime) -> Dict[str, Any]:
    payload = {
        "sensors": [sensor_id],
        "limit": int(RECOLLECT_LIMIT),
        "startTime": sp_time(start),
        "stopTime": sp_time(stop),
    }
    return sensorpush_post("/samples", token, payload, timeout=180)


def f_to_c(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return (float(value) - 32.0) * 5.0 / 9.0


def rows_from_samples(sensor_id: str, sensor_name: str, samples: Dict[str, Any]) -> List[Tuple[Any, ...]]:
    rows: List[Tuple[Any, ...]] = []
    for sample in samples.get("sensors", {}).get(sensor_id, []) or []:
        observed = sample.get("observed")
        if not observed:
            continue
        pressure_inhg = sample.get("barometric_pressure")
        pressure_mb = float(pressure_inhg) * 33.8639 if pressure_inhg is not None else None
        rows.append((
            sensor_id,
            sensor_name,
            observed,
            observed,
            f_to_c(sample.get("temperature")) if sample.get("temperature") is not None else None,
            float(sample.get("humidity")) if sample.get("humidity") is not None else None,
            float(pressure_inhg) if pressure_inhg is not None else None,
            pressure_mb,
            float(sample.get("voltage")) if sample.get("voltage") is not None else None,
            "sensorpush_recollect",
        ))
    return rows


def insert_rows(rows: List[Tuple[Any, ...]]) -> int:
    if not rows:
        return 0
    with db_connect() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO readings (
                    sensor_id, sensor_name, observed_at, timestamp,
                    temperature_c, humidity, barometric_pressure_inhg,
                    pressure_mb, voltage, source
                ) VALUES %s
                ON CONFLICT (sensor_id, observed_at) WHERE observed_at IS NOT NULL
                DO UPDATE SET
                    sensor_name = EXCLUDED.sensor_name,
                    timestamp = EXCLUDED.timestamp,
                    temperature_c = EXCLUDED.temperature_c,
                    humidity = EXCLUDED.humidity,
                    barometric_pressure_inhg = EXCLUDED.barometric_pressure_inhg,
                    pressure_mb = EXCLUDED.pressure_mb,
                    voltage = EXCLUDED.voltage,
                    source = EXCLUDED.source,
                    stored_at = NOW()
                """,
                rows,
                page_size=1000,
            )
            changed = cur.rowcount
        conn.commit()
    return int(changed)


def sleep_between(first_done: bool) -> None:
    if first_done and RECOLLECT_SLEEP_SECONDS > 0:
        print(f"Sleeping {RECOLLECT_SLEEP_SECONDS}s before next SensorPush request...")
        time.sleep(RECOLLECT_SLEEP_SECONDS)


def query_window(token: str, sensor_id: str, sensor_name: str, start: dt.datetime, stop: dt.datetime, depth: int, first_done_ref: List[bool]) -> Tuple[int, int]:
    sleep_between(first_done_ref[0])
    first_done_ref[0] = True
    samples = get_samples(token, sensor_id, start, stop)
    rows = rows_from_samples(sensor_id, sensor_name, samples)
    returned = len(rows)

    span = stop - start
    if returned >= RECOLLECT_LIMIT and depth < MAX_SPLIT_DEPTH and span > dt.timedelta(minutes=10):
        mid = start + span / 2
        print(f"LIMIT HIT: {sensor_name} {sp_time(start)} -> {sp_time(stop)} returned {returned}; splitting")
        r1, i1 = query_window(token, sensor_id, sensor_name, start, mid, depth + 1, first_done_ref)
        r2, i2 = query_window(token, sensor_id, sensor_name, mid, stop, depth + 1, first_done_ref)
        return r1 + r2, i1 + i2

    inserted = insert_rows(rows)
    print(f"{sensor_name}: {sp_time(start)} -> {sp_time(stop)} | API {returned}; inserted/updated {inserted}")
    return returned, inserted


def summary(start: dt.datetime, end: dt.datetime) -> None:
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sensor_name, COUNT(*), MIN(observed_at), MAX(observed_at)
                FROM readings
                WHERE observed_at >= %s AND observed_at < %s
                GROUP BY sensor_name
                ORDER BY sensor_name
                """,
                (start, end),
            )
            rows = cur.fetchall()
    print("\nSupabase rows in recollected range:")
    for sensor_name, count, oldest, newest in rows:
        print(f"- {sensor_name}: {count} rows | {oldest} -> {newest}")


def main() -> None:
    start = parse_time(RECOLLECT_START, end_of_day=False)
    end = parse_time(RECOLLECT_END, end_of_day=True)
    if start >= end:
        raise RuntimeError("RECOLLECT_START must be earlier than RECOLLECT_END")

    print("SensorPush → Supabase missing-range recollector")
    print("Range UTC:", sp_time(start), "->", sp_time(end))
    print("Chunk hours:", RECOLLECT_CHUNK_HOURS)
    print("Limit:", RECOLLECT_LIMIT)
    print("Delete existing first:", RECOLLECT_DELETE_EXISTING)

    setup_database()
    if RECOLLECT_DELETE_EXISTING:
        deleted = delete_existing_range(start, end)
        print(f"Deleted existing Supabase rows in range: {deleted}")

    token = get_access_token()
    sensors = get_sensors(token)
    print("Sensors:")
    for sid, meta in sensors.items():
        print(f"- {meta.get('name', sid)} ({sid})")

    chunk = dt.timedelta(hours=RECOLLECT_CHUNK_HOURS)
    first_done_ref = [False]
    total_returned = 0
    total_changed = 0
    for sensor_id, meta in sensors.items():
        sensor_name = str(meta.get("name", sensor_id))
        window_start = start
        while window_start < end:
            window_stop = min(window_start + chunk, end)
            returned, changed = query_window(token, sensor_id, sensor_name, window_start, window_stop, 0, first_done_ref)
            total_returned += returned
            total_changed += changed
            window_start = window_stop

    print("\nFinished.")
    print("Total API rows returned:", total_returned)
    print("Total inserted/updated:", total_changed)
    summary(start, end)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise
