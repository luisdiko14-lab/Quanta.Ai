# Quanta AI — free cloud deployment

This setup is intended for a personal/test deployment on free tiers. It is not an always-on production SLA: Render free web services can spin down when idle, and free vendor quotas can change. Check each provider's current limits before relying on it.

## Architecture

- Frontend: Vercel Hobby, connected to this GitHub repository with the project root set to `frontend`.
- Python API: Render free Docker web service from the root `render.yaml`.
- PostgreSQL: Neon free project; use its pooled connection string and keep the `postgresql+asyncpg://` scheme.
- Redis: Upstash Redis free database; use its TLS URL (`rediss://...`) as `REDIS_URL`.
- Uploaded files: Cloudflare R2 Standard bucket, accessed privately through its S3-compatible API.
- AI providers: Gemini, Groq and DeepSeek API keys configured only as Render environment secrets.

The Vercel rewrite proxies `/api/*` and `/health/*` to the Render API so the browser talks to one origin. This keeps the existing strict, secure session cookies usable without cross-site cookie workarounds.

## 1. Create Cloudflare R2 storage

1. Create/sign in to a Cloudflare account and open **Storage & databases → R2**.
2. Create a Standard bucket named `quanta-ai-files` (or another name you prefer).
3. Open **Manage R2 API Tokens** and create an Object Read & Write token scoped only to that bucket.
4. Copy the Access Key ID and Secret Access Key once. Keep them private.
5. Record your Cloudflare Account ID. The default endpoint is `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.
6. Do not enable public bucket access or publish an R2.dev URL. Downloads are proxied through the authenticated Quanta API.

R2's published free allowance currently includes 10 GB-month Standard storage, 1 million Class A operations and 10 million Class B operations per month; egress is free. Usage beyond the allowance can be billed, so configure account billing/alerts and monitor usage.

## 2. Create PostgreSQL on Neon

1. Create a free Neon project.
2. Create a database named `quanta`.
3. Copy the pooled connection string.
4. In Render, set `DATABASE_URL` to that connection string after changing its prefix from `postgresql://` to `postgresql+asyncpg://` if necessary. Keep the provider's query parameters.

## 3. Create Redis on Upstash

1. Create a free Redis database.
2. Copy its TLS connection URL.
3. Set it as `REDIS_URL` in Render. It should normally begin with `rediss://`.

## 4. Deploy the backend on Render

1. Sign in to Render and choose **New → Blueprint**.
2. Connect `luisdiko14-lab/Quanta.Ai` and select branch `main` after the deployment PR has been merged.
3. Render reads `render.yaml` and creates the `quanta-ai-api` free web service.
4. Fill every environment variable marked **sync: false** in the Render service's Environment page:
   - `FRONTEND_BASE_URL`: the Vercel URL, e.g. `https://quanta-ai.vercel.app`.
   - `CORS_ORIGINS`: the same exact origin, with no trailing slash.
   - `DATABASE_URL`, `REDIS_URL`.
   - `R2_ACCOUNT_ID`, `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`; `R2_ENDPOINT_URL` can be left blank to use the default endpoint.
   - Provider keys and actual model IDs after you create provider accounts.
   - SMTP values if you want verification and password-reset emails to be delivered.
5. Keep `STORAGE_BACKEND=r2`. Do not set the R2 credentials in Vercel or in frontend variables.
6. Wait for the Render health check at `/health/live` to pass. The API hostname should be `https://quanta-ai-api.onrender.com`.

## 5. Deploy the frontend on Vercel

1. Import `luisdiko14-lab/Quanta.Ai` into Vercel.
2. Set the project **Root Directory** to `frontend`.
3. Keep the Vercel project configuration from `frontend/vercel.json`.
4. Deploy. Vercel provides a free `*.vercel.app` address.
5. If Vercel gives the project a hostname other than `quanta-ai.vercel.app`, update `FRONTEND_BASE_URL` and `CORS_ORIGINS` in Render to the exact Vercel origin, then redeploy the Render service.
6. If the Render service hostname differs from `quanta-ai-api.onrender.com`, update both external rewrite destinations in `frontend/vercel.json` and push the change.

## 6. GitHub Actions

The repository CI workflow runs backend lint/tests and the frontend build on pushes and pull requests. Vercel and Render can deploy automatically from GitHub after you connect the repository. No deployment tokens need to be committed to the repository.

## Important free-tier limitations

- Render free web services sleep after inactivity, so the first request can be slow. They are not suitable for a strict 24/7 requirement.
- Free database/cache/storage quotas and provider free plans have limits and can change.
- Cloudflare R2 is configured as private object storage. Never make the bucket public or expose its access keys in browser code.
- SMTP and AI provider accounts/keys are separate from hosting. A hosted app without valid provider keys can load but cannot generate AI responses.
- The current product is still an early foundation. This deployment does not imply that the planned billing, admin, OCR, malware scanning, image generation, voice, or every other requested feature is finished.
