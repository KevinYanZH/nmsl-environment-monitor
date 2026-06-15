import os
import sys
from datetime import datetime, timezone

import requests
import psycopg2
import psycopg2.extras

BASE_URL = "https://api.sensorpush.com/api/v1"

SENSORPUSH_EMAIL = os.environ.get("SENSORPUSH_EMAIL")
SENSORPUSH_PASSWORD = os.environ.get("SENSORPUSH_PASSWORD")
DATABASE_URL = os.environ.get("DATABASE_URL")
POLL_LIMIT = int(os.environ.get("SENSORPUSH_POLL_LIMIT", "300"))


def normalize_database_url(url: str) -> str:
    if not url:
        raise RuntimeError("Missing DATABASE_URL")
    url = str(url).strip().strip('"').strip("'")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def db_connect():
    return psycopg2.connect(normalize_database_url(DATABASE_URL))


def setup_database():
    """Make the table compatible with both the earlier timestamp schema and the newer observed_at schema."""
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
                source TEXT DEFAULT 'github_actions',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                stored_at TIMESTAMPTZ DEFAULT NOW()
            )
            """)
            cur.execute("ALTER TABLE readings ADD COLUMN IF NOT EXISTS observed_at TIMESTAMPTZ")
            cur.execute("ALTER TABLE readings ADD COLUMN IF NOT EXISTS timestamp TIMESTAMPTZ")
            cur.execute("ALTER TABLE readings ADD COLUMN IF NOT EXISTS pressure_mb DOUBLE PRECISION")
            cur.execute("ALTER TABLE readings ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'github_actions'")
            cur.execute("ALTER TABLE readings ADD COLUMN IF NOT EXISTS stored_at TIMESTAMPTZ DEFAULT NOW()")
            cur.execute("ALTER TABLE readings ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_readings_observed_at ON readings (observed_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON readings (timestamp)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_readings_sensor_observed_unique ON readings(sensor_id, observed_at) WHERE observed_at IS NOT NULL")
        conn.commit()


def fahrenheit_to_celsius(temp_f):
    return (float(temp_f) - 32.0) * 5.0 / 9.0


def get_access_token():
    if not SENSORPUSH_EMAIL or not SENSORPUSH_PASSWORD:
        raise RuntimeError("Missing SENSORPUSH_EMAIL or SENSORPUSH_PASSWORD")

    r = requests.post(
        f"{BASE_URL}/oauth/authorize",
        headers={"accept": "application/json", "Content-Type": "application/json"},
        json={"email": SENSORPUSH_EMAIL, "password": SENSORPUSH_PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    authorization = r.json()["authorization"]

    r = requests.post(
        f"{BASE_URL}/oauth/accesstoken",
        headers={"accept": "application/json", "Content-Type": "application/json"},
        json={"authorization": authorization},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["accesstoken"]


def sensorpush_post(path, token, payload):
    r = requests.post(
        f"{BASE_URL}{path}",
        headers={"accept": "application/json", "Authorization": token, "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def get_rows():
    token = get_access_token()
    sensors = sensorpush_post("/devices/sensors", token, {})
    samples = sensorpush_post("/samples", token, {"limit": POLL_LIMIT})

    rows = []
    for sensor_id, readings in samples.get("sensors", {}).items():
        sensor_name = sensors.get(sensor_id, {}).get("name", sensor_id)
        for reading in readings or []:
            observed = reading.get("observed")
            temp_f = reading.get("temperature")
            humidity = reading.get("humidity")
            pressure_inhg = reading.get("barometric_pressure")
            voltage = reading.get("voltage")

            if not observed:
                continue

            temp_c = fahrenheit_to_celsius(temp_f) if temp_f is not None else None
            pressure_mb = float(pressure_inhg) * 33.8639 if pressure_inhg is not None else None

            rows.append((
                sensor_id,
                sensor_name,
                observed,
                observed,
                temp_c,
                float(humidity) if humidity is not None else None,
                float(pressure_inhg) if pressure_inhg is not None else None,
                pressure_mb,
                float(voltage) if voltage is not None else None,
                "github_actions",
            ))
    return rows


def insert_rows(rows):
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
    return changed


def main():
    print(f"Collector run started: {datetime.now(timezone.utc).isoformat()}")
    print(f"Polling latest SensorPush samples with limit={POLL_LIMIT}")
    setup_database()
    rows = get_rows()
    print(f"Rows returned from SensorPush: {len(rows)}")
    changed = insert_rows(rows)
    print(f"Inserted/updated rows in Supabase: {changed}")
    print("Collector run finished.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
