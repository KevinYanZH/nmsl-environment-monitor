Missing-range recollector for NMSL SensorPush cloud setup

Files:
- recollect_range_supabase.py
- .github/workflows/recollect_sensorpush_range.yml

Upload both to your GitHub repo. The workflow file must be located at:
.github/workflows/recollect_sensorpush_range.yml

Use:
1. Commit both files to GitHub.
2. Go to GitHub → Actions → Recollect SensorPush range → Run workflow.
3. Enter start/end dates for the missing period.
4. Use delete_existing=0 first. If the existing bad rows need to be replaced, rerun with delete_existing=1.

Required GitHub Actions secrets:
- SENSORPUSH_EMAIL
- SENSORPUSH_PASSWORD
- DATABASE_URL

Notes:
- Dates are interpreted as America/Toronto local time.
- The script respects SensorPush API limits by sleeping between requests.
- It upserts rows by sensor_id + observed_at.
