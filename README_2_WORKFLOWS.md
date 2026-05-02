# Trading Bot - 2 Workflow Setup

## Files in this pack

1. `update_cache_daily.py`
   - Updates `cache_stock/*.csv` using API.
   - Only this file should call API.

2. `v10_market_data_SWITCH.py`
   - Auto switch data layer.
   - Rename to `v10_market_data.py`.
   - Supports:
     - `DATA_MODE=CACHE_ONLY`
     - `DATA_MODE=AUTO`
     - `DATA_MODE=API_ONLY`

3. `update-cache.yml`
   - GitHub Actions workflow to update cache daily.
   - Put into `.github/workflows/update-cache.yml`.

4. `run-daily-cache-only.yml`
   - GitHub Actions workflow to run bot from cache only.
   - Put into `.github/workflows/run-daily-cache-only.yml`.

## Recommended use

### Workflow 1: update-cache
- Runs at 16:30 Vietnam time.
- Calls API and updates cache.

### Workflow 2: run-daily-cache-only
- Runs at 17:00 Vietnam time.
- Reads cache only.
- Sends Telegram + dashboard.

## Upload steps

1. Rename:
   - `v10_market_data_SWITCH.py` -> `v10_market_data.py`

2. Upload to repo root:
   - `update_cache_daily.py`
   - `v10_market_data.py`

3. Upload workflows:
   - `.github/workflows/update-cache.yml`
   - `.github/workflows/run-daily-cache-only.yml`

4. Commit.

5. Run manually first:
   - Run `update-cache`
   - Then run `run-daily-cache-only`

## Important

Do not delete old workflow immediately. Disable old workflow only after this new setup works.
