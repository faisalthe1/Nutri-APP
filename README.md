# FastFuel / Nutri-APP

A Django app for exploring restaurant meals, comparing nutrition, and saving favorites. The interface uses local CSS and JavaScript, with optional Google Fonts and system-font fallbacks. No frontend build tool is needed. Decorative motion runs briefly and respects reduced-motion preferences.

## Local development

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY='your-local-secret'
export FATSECRET_CLIENT_ID='your-client-id'
export FATSECRET_CLIENT_SECRET='your-client-secret'
python manage.py migrate
python manage.py runserver
```

`.env.example` documents variables; `.env` files are not automatically loaded. With no API credentials, the interface works and meal searches show a clear unavailable state.

## Existing Render service

Keep the existing service connected to this repository. This update does not provision or replace infrastructure.

Before deploying:

1. Set `SECRET_KEY` to a strong, stable secret and `DEBUG=False` in Environment. Keep an existing production secret to preserve sessions.
2. Set `FATSECRET_CLIENT_ID` and `FATSECRET_CLIENT_SECRET`. Use the OAuth 2.0 credentials from your FatSecret developer account, and authorize the outbound IP ranges shown under Render’s Connect menu in FatSecret’s IP allowlist. Store secrets only in Render, never in Git.
3. Use build command `bash build.sh`, start command `bash start.sh`, and health check `/healthz/`. `start.sh` applies migrations before binding Gunicorn to Render's `$PORT`; this works with the free web service plan, which does not support pre-deploy commands.
4. Set `DATABASE_URL` to your existing PostgreSQL database if available. This is optional for compatibility; without it the app keeps using SQLite. **SQLite on Render's ephemeral filesystem does not persist across deployments/restarts.** Back up existing data before deploying. Moving to PostgreSQL requires a deliberate export/import; setting the URL does not migrate existing records. No database is automatically created by this Blueprint.
5. If you use custom domains, set comma-separated `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` (origins include `https://`). Render's default hostname is included automatically.

For a manually configured existing service, apply these settings in its dashboard; changing `render.yaml` alone will not update manual service settings. For a Blueprint-managed service, sync the existing Blueprint. Do not create a duplicate service.

The Blueprint retains a free web service. Credentials use `sync: false`, and a secret is generated for new Blueprint setups. Render CLI users can validate with `render blueprints validate render.yaml`.

References: [Render Django guide](https://render.com/docs/deploy-django), [Blueprint specification](https://render.com/docs/blueprint-spec).

## Checks

```sh
python manage.py test
python manage.py check
python manage.py collectstatic --noinput
node --check nutrition/static/js/main.js
```

The regression suite mocks FatSecret, so it needs no live credentials. It covers guest and account flows, input validation, saved-meal ownership, API failures, token refresh, and malformed responses. `/healthz/` checks that the web process responds; it does not assert third-party API or database readiness.

Daily macro targets are contextual; bulking results use protein density and cutting results use the daily calorie ceiling. Allergy choices are stored for reference but are **not used to filter meals** because the current search data does not verify allergens.

## Nutrition provider

Uses FatSecret Basic OAuth 2.0 with `foods/search/v1` and `food/v5`, US data. Only access tokens are cached, with expiry and one retry for expired authentication. Food content is fetched fresh. Favorites persist only namespaced food IDs; their display data is fetched on demand, six per page. Legacy Nutritionix favorites retain their original snapshots. Search shows each provider serving size; generic foods normally use 100 g. Missing nutrition is never presented as zero. FatSecret attribution appears in the shared footer.
