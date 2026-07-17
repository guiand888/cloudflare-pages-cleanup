from workers import Response, WorkerEntrypoint

import cleanup


class Default(WorkerEntrypoint):
    async def scheduled(self, controller, env, ctx):
        # The runtime unconditionally calls scheduled() with (controller, env,
        # ctx) - narrowing this signature (as tried previously) causes a hard
        # "takes N positional arguments but 3 were given" TypeError. But the
        # positional `env` arg itself has repeatedly come through as None in
        # production despite correct dashboard bindings (see incident log
        # from 2026-07-17) - a known-flaky part of the Python Workers FFI for
        # scheduled() (cloudflare/workers-py#27). self.env, set by
        # WorkerEntrypoint's constructor and already proven reliable by
        # fetch() below, doesn't go through that same per-call marshalling.
        print(f"cloudflare-pages-cleanup: cron triggered ({controller.cron})")
        try:
            await cleanup.run(self.env)
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
