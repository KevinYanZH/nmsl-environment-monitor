Files in this package:
- collect_latest_supabase.py
- .github/workflows/collect_sensorpush.yml

Upload BOTH into the root of your existing GitHub repo.

Then add GitHub repository secrets:
- SENSORPUSH_EMAIL
- SENSORPUSH_PASSWORD
- DATABASE_URL
- SENSORPUSH_POLL_LIMIT = 300

The workflow runs every 5 minutes and can also be started manually from GitHub Actions.
