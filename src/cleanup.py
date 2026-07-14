"""Core logic for pruning old Cloudflare Pages deployments across an account.

Called from the scheduled() handler in entry.py. Kept separate so the retention
logic can be reasoned about (and eventually tested) without the Workers runtime.
"""

from workers import fetch

API_BASE = "https://api.cloudflare.com/client/v4"


class CloudflareApiError(Exception):
    def __init__(self, method, url, status, errors):
        super().__init__(f"{method} {url} -> {status}: {errors}")
        self.status = status


async def _request(token, method, path, params=None):
    url = f"{API_BASE}{path}"
    if params:
        query = "&".join(f"{key}={value}" for key, value in params.items() if value is not None)
        if query:
            url = f"{url}?{query}"

    response = await fetch(
        url,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    data = await response.json()
    if not data.get("success", False):
        raise CloudflareApiError(method, url, response.status, data.get("errors"))
    return data


async def _list_paginated(token, path, params=None):
    """Walks every page of a Cloudflare list endpoint and returns the combined result."""
    items = []
    page = 1
    params = dict(params or {})
    while True:
        params["page"] = page
        params["per_page"] = 25
        data = await _request(token, "GET", path, params)
        items.extend(data["result"])
        info = data.get("result_info") or {}
        total_pages = info.get("total_pages", page)
        if page >= total_pages:
            break
        page += 1
    return items


async def list_projects(token, account_id):
    return await _list_paginated(token, f"/accounts/{account_id}/pages/projects")


async def list_deployments(token, account_id, project_name, environment):
    return await _list_paginated(
        token,
        f"/accounts/{account_id}/pages/projects/{project_name}/deployments",
        {"env": environment},
    )


async def delete_deployment(token, account_id, project_name, deployment_id):
    # force=true is required to delete a deployment that's still aliased
    # (e.g. the newest deployment for a branch). Our retention logic already
    # decided this deployment is expendable, so it's safe to always force it.
    await _request(
        token,
        "DELETE",
        f"/accounts/{account_id}/pages/projects/{project_name}/deployments/{deployment_id}",
        {"force": "true"},
    )


def _newest_first(deployments):
    return sorted(deployments, key=lambda deployment: deployment["created_on"], reverse=True)


def _select_for_deletion(deployments, keep):
    return _newest_first(deployments)[keep:]


def _group_preview_by_branch(deployments):
    """Groups preview deployments by branch so retention is applied per branch.

    A deployment with no branch metadata (e.g. an ad-hoc/API deploy) gets its
    own singleton group instead of being lumped in with unrelated deployments,
    so it's never accidentally caught in someone else's retention count.
    """
    groups = {}
    for deployment in deployments:
        trigger = deployment.get("deployment_trigger") or {}
        branch = (trigger.get("metadata") or {}).get("branch")
        key = branch if branch else f"__no_branch_{deployment['id']}"
        groups.setdefault(key, []).append(deployment)
    return groups


async def _delete_one(token, account_id, project_name, deployment, dry_run, summary):
    label = f"{project_name}/{deployment['environment']}/{deployment['id'][:8]}"
    if dry_run:
        print(f"[dry-run] would delete {label} (created_on={deployment['created_on']})")
        return
    try:
        await delete_deployment(token, account_id, project_name, deployment["id"])
        print(f"deleted {label}")
    except Exception as exc:  # noqa: BLE001 - one bad deployment shouldn't stop the run
        summary["errors"] += 1
        print(f"failed to delete {label}: {exc}")


async def clean_project(token, account_id, project_name, keep_production, keep_preview_per_branch, dry_run):
    summary = {
        "production_kept": 0,
        "production_deleted": 0,
        "preview_kept": 0,
        "preview_deleted": 0,
        "errors": 0,
    }

    production = await list_deployments(token, account_id, project_name, "production")
    production_to_delete = _select_for_deletion(production, keep_production)
    summary["production_kept"] = len(production) - len(production_to_delete)
    summary["production_deleted"] = len(production_to_delete)
    for deployment in production_to_delete:
        await _delete_one(token, account_id, project_name, deployment, dry_run, summary)

    preview = await list_deployments(token, account_id, project_name, "preview")
    for _branch, branch_deployments in _group_preview_by_branch(preview).items():
        branch_to_delete = _select_for_deletion(branch_deployments, keep_preview_per_branch)
        summary["preview_kept"] += len(branch_deployments) - len(branch_to_delete)
        summary["preview_deleted"] += len(branch_to_delete)
        for deployment in branch_to_delete:
            await _delete_one(token, account_id, project_name, deployment, dry_run, summary)

    return summary


def _parse_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes")


def _parse_exclude_list(value):
    return {name.strip() for name in str(value or "").split(",") if name.strip()}


async def run(env):
    """Entry point called from the scheduled() handler. Raises if any deletion failed,
    so a failed cleanup run is visible in the Cron Trigger's Past Events table."""
    token = env.CLOUDFLARE_API_TOKEN
    account_id = env.CLOUDFLARE_ACCOUNT_ID
    keep_production = int(env.KEEP_PRODUCTION)
    keep_preview_per_branch = int(env.KEEP_PREVIEW_PER_BRANCH)
    dry_run = _parse_bool(getattr(env, "DRY_RUN", None), default=True)
    exclude = _parse_exclude_list(getattr(env, "EXCLUDE_PROJECTS", None))

    if dry_run:
        print("DRY_RUN is enabled - no deployments will actually be deleted")

    projects = await list_projects(token, account_id)
    had_errors = False

    for project in projects:
        name = project["name"]
        if name in exclude:
            print(f"{name}: skipped (excluded)")
            continue
        try:
            summary = await clean_project(
                token, account_id, name, keep_production, keep_preview_per_branch, dry_run
            )
            print(
                f"{name}: production kept={summary['production_kept']} "
                f"deleted={summary['production_deleted']}, "
                f"preview kept={summary['preview_kept']} deleted={summary['preview_deleted']}"
                + (f", errors={summary['errors']}" if summary["errors"] else "")
            )
            if summary["errors"]:
                had_errors = True
        except Exception as exc:  # noqa: BLE001 - one bad project shouldn't stop the run
            had_errors = True
            print(f"{name}: failed to clean up: {exc}")

    if had_errors:
        raise RuntimeError("cleanup run completed with errors, see logs above")
