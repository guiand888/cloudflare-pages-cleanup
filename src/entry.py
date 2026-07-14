from workers import Response, WorkerEntrypoint

import cleanup


class Default(WorkerEntrypoint):
    async def scheduled(self, controller, env, ctx):
        print(f"cloudflare-pages-cleanup: cron triggered ({controller.cron})")
        try:
            await cleanup.run(env)
        except Exception as exc:
            # Re-raise after logging so the invocation shows as failed in the
            # Cron Trigger's Past Events table, instead of silently vanishing.
            print(f"cloudflare-pages-cleanup: run failed: {exc}")
            raise

    async def fetch(self, request):
        # This Worker only does work via its Cron Trigger and has no HTTP
        # surface. workers_dev/preview_urls are disabled in wrangler.jsonc
        # so it shouldn't be publicly reachable, but this handler is kept
        # as a fallback so any request that does reach it (e.g. a route
        # added later) gets a clean 404 instead of crashing with
        # "Method fetch does not exist".
        return Response("Not found", status=404)
