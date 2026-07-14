# Cloudflare Pages Cleanup

[![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg)](https://github.com/RichardLitt/standard-readme)

A scheduled Cloudflare Worker that prunes old [Cloudflare Pages](https://developers.cloudflare.com/pages/) deployments across an entire account, keeping only the most recent production deployments and the most recent preview deployments per branch.

## Background

Cloudflare Pages keeps every deployment a project has ever produced, which piles up quickly on actively developed sites. This Worker runs on its own [Cron Trigger](https://developers.cloudflare.com/workers/configuration/cron-triggers/), independent of any site's build pipeline: it wakes up on a schedule, lists every Pages project on the account, and deletes deployments beyond the configured retention.

It's deployed once for the whole account rather than wired into each site repo:

- Production deployments: keep the last `KEEP_PRODUCTION` (default `3`), oldest deleted first.
- Preview deployments: keep the last `KEEP_PREVIEW_PER_BRANCH` (default `3`) **per git branch**, since preview deployments are branch-scoped and a global cutoff would wipe out other branches' history whenever one branch was pushed more often.

No site's build command, CI config, or deploy pipeline needs to change for this to work.

## Install

1. Install [uv](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org/), then install dependencies:

   ```sh
   uv sync
   ```

2. Create a scoped Cloudflare API token — dashboard → **My Profile → API Tokens → Create Custom Token**:
   - Permissions: **Account / Cloudflare Pages / Edit**
   - Account Resources: restrict to your one account (not "All accounts")
   - No zone permissions needed

   Never commit this token. It's provisioned as an encrypted Worker secret in the next step:

   ```sh
   uv run pywrangler secret put CLOUDFLARE_API_TOKEN
   ```

3. Deploy, with `DRY_RUN` left at its default `"true"`:

   ```sh
   uv run pywrangler deploy
   ```

4. Set your account ID — dashboard → **Workers & Pages → cloudflare-pages-cleanup → Settings → Variables and Secrets → Add**, type **Text** (not **Secret** — the account ID isn't a credential on its own, and a plain Text variable stays visible/editable in the dashboard instead of being write-only). Name it `CLOUDFLARE_ACCOUNT_ID`, paste your account ID, and deploy the change from the dashboard. It's set via the dashboard rather than committed to `wrangler.jsonc` purely so it doesn't end up in a public repo; `keep_vars: true` in `wrangler.jsonc` means future `pywrangler deploy` runs won't wipe it back out.

5. Trigger a run (wait for the daily schedule, or use the dashboard's Cron Trigger test action) and check the logs — `uv run pywrangler tail` — to confirm the dry-run plan matches what's actually in the Pages dashboard. Only then flip `DRY_RUN` to `"false"` in `wrangler.jsonc` and redeploy.

## Usage

All configuration lives in `wrangler.jsonc` under `vars`, except `CLOUDFLARE_ACCOUNT_ID` (set via the dashboard, step 4 above) and `CLOUDFLARE_API_TOKEN` (a secret, step 2 above):

| Variable                  | Default | Meaning                                                                 |
| -------------------------- | ------- | ------------------------------------------------------------------------ |
| `CLOUDFLARE_ACCOUNT_ID` *(dashboard Text var)* | —       | Account whose Pages projects get cleaned up.       |
| `CLOUDFLARE_API_TOKEN` *(secret)*  | —       | Scoped API token, see step 2 above.                              |
| `KEEP_PRODUCTION`           | `3`     | Production deployments to keep per project.                             |
| `KEEP_PREVIEW_PER_BRANCH`   | `3`     | Preview deployments to keep, per branch, per project.                   |
| `EXCLUDE_PROJECTS`          | *(empty)* | Comma-separated Pages project names to skip entirely.                 |
| `DRY_RUN`                   | `true`  | When `true`, logs what would be deleted without deleting anything.      |

For local development, copy `.dev.vars.example` to `.dev.vars` (gitignored) and fill in a real token, then pass the account ID on the command line (it isn't loaded from `.dev.vars` since it's a plain var, not a secret):

```sh
uv run pywrangler dev --test-scheduled --var CLOUDFLARE_ACCOUNT_ID:<your-account-id>
curl "http://localhost:8787/cdn-cgi/handler/scheduled?cron=*+*+*+*+*"
```

Running against a second Cloudflare account means deploying a second, separate copy of this Worker with its own token and account ID — a single API token cannot span accounts.

## License

[AGPL-3.0](LICENSE)
