# Cloudflare Pages Cleanup

Deletes old Cloudflare Pages deployments, keeping only the most recent N production and preview deployments.

## Configuration

Copy `.env.example` to `.env` and set your Cloudflare credentials and project name.

## Run

```bash
python -m venv venv
source venv/bin/activate
pip install -r <(echo "requests\npython-dotenv")
python main.py
```
