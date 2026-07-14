from workers import WorkerEntrypoint

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
