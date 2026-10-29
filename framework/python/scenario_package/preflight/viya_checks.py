# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Checks against the SAS Viya environment under test.

DISABLED: not registered in preflight.all_checks(). These probes talk to the REST API directly
and need to be rewritten on the sas-viya admin CLI before they are re-enabled.
"""

import base64
from typing import List, Optional, Tuple

from . import k8s
from .core import Check, CheckResult, PreflightContext, fail, ok, skipped, warn
from .http import HttpError

CLIENT_ID_VAR = "SAS_VALIDATION_CLIENT_ID"
CLIENT_SECRET_VAR = "SAS_VALIDATION_CLIENT_SECRET"
STUDIO_CONTEXT = "SAS Studio compute context"
HTML_COMMONS_SETTINGS = ("disableAutoOpenWhatsNew", "disableWelcomeScreens")


def _token(context: PreflightContext) -> Optional[str]:
    return context.state.get("viya.token")


def _authorized(context: PreflightContext, path: str):
    return context.http.request(
        f"{context.hostname.rstrip('/')}{path}",
        headers={
            "Authorization": f"Bearer {_token(context)}",
            "Accept": "application/json",
        },
    )


def _sample_user(context: PreflightContext) -> Tuple[Optional[str], Optional[str], str]:
    """One username/password to probe with, taken from the users file or the cluster secret."""
    if context.users_file is not None:
        users = k8s.users_from_csv(context.users_file)
        name = next(iter(users))
        return name, users[name], str(context.users_file)
    try:
        secret = k8s.read_or_none(
            context.kube().core.read_namespaced_secret, k8s.SECRET_NAME, context.namespace
        )
    except Exception:
        return None, None, "unavailable"
    if secret is None:
        return None, None, "unavailable"
    users = k8s.decode_users(secret)
    if not users:
        return None, None, "unavailable"
    name = next(iter(users))
    return name, users[name], f"secret '{k8s.SECRET_NAME}'"


def _reachable(context: PreflightContext) -> CheckResult:
    url = f"{context.hostname.rstrip('/')}/SASLogon/login"
    try:
        response = context.http.request(url)
    except HttpError as error:
        return fail(
            f"{url} is not reachable: {error}",
            remedy="Check the hostname, DNS, VPN and the trusted-certs setting",
        )
    if response.status >= 400:
        return fail(
            f"{url} returned HTTP {response.status}",
            remedy="Confirm SASLogon is running on this Viya deployment",
        )
    return ok(f"{url} returned HTTP {response.status}")


def _login(context: PreflightContext) -> CheckResult:
    client_id = context.environ.get(CLIENT_ID_VAR)
    client_secret = context.environ.get(CLIENT_SECRET_VAR, "")
    if not client_id:
        return skipped(
            f"set {CLIENT_ID_VAR} and {CLIENT_SECRET_VAR} to probe a test user login"
        )
    username, password, source = _sample_user(context)
    if username is None:
        return skipped("no test user credentials available (pass --users-file)")
    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode("utf-8")
    ).decode("utf-8")
    try:
        response = context.http.request(
            f"{context.hostname.rstrip('/')}/SASLogon/oauth/token",
            method="POST",
            headers={
                "Authorization": f"Basic {credentials}",
                "Accept": "application/json",
            },
            form={"grant_type": "password", "username": username, "password": password},
        )
    except HttpError as error:
        return fail(f"token request failed: {error}")
    if response.status == 401:
        return fail(
            f"user '{username}' (from {source}) was rejected by SASLogon",
            remedy="Confirm the user exists in the identity provider and the password is current",
        )
    if response.status != 200:
        return skipped(
            f"token request returned HTTP {response.status}; the OAuth client in "
            f"{CLIENT_ID_VAR} may not allow the password grant"
        )
    context.state["viya.token"] = response.json().get("access_token")
    context.state["viya.user"] = username
    return ok(f"user '{username}' (from {source}) authenticated")


def _not_admin(context: PreflightContext) -> CheckResult:
    username = context.state.get("viya.user")
    response = _authorized(context, f"/identities/users/{username}/memberships?depth=-1")
    if response.status != 200:
        return skipped(f"membership lookup returned HTTP {response.status}")
    groups = [
        item.get("name") for item in response.json().get("items", []) if isinstance(item, dict)
    ]
    if "SASAdministrators" in groups:
        return warn(
            f"user '{username}' is a member of SASAdministrators",
            remedy="Run validation scenarios with non-admin users",
        )
    return ok(f"user '{username}' is not a SAS administrator")


def _compute_contexts(context: PreflightContext) -> CheckResult:
    response = _authorized(context, "/compute/contexts?limit=100")
    if response.status != 200:
        return fail(
            f"/compute/contexts returned HTTP {response.status}",
            remedy="Confirm the compute service is running and the user may list contexts",
        )
    names = [
        item.get("name") for item in response.json().get("items", []) if isinstance(item, dict)
    ]
    if STUDIO_CONTEXT not in names:
        return fail(
            f"'{STUDIO_CONTEXT}' is not available (found: {', '.join(names) or 'none'})",
            remedy="Confirm SAS Studio is deployed and compute contexts are published",
        )
    return ok(f"{len(names)} compute context(s) including '{STUDIO_CONTEXT}'")


def _html_commons(context: PreflightContext) -> CheckResult:
    response = _authorized(
        context,
        "/configuration/configurations?filter=eq(definitionName,'sas.htmlcommons')",
    )
    if response.status in (401, 403):
        return skipped("reading sas.htmlcommons requires an administrator token")
    if response.status != 200:
        return skipped(f"configuration lookup returned HTTP {response.status}")
    remedy = (
        "Environment Manager -> Configurations -> Definitions -> sas.htmlcommons: set "
        "disableAutoOpenWhatsNew and disableWelcomeScreens to true"
    )
    items = response.json().get("items", [])
    settings = {}
    for item in items:
        if isinstance(item, dict):
            settings.update(item.get("attributes") or {})
    if not settings:
        return warn("no sas.htmlcommons configuration instance found", remedy=remedy)
    disabled = [name for name in HTML_COMMONS_SETTINGS if settings.get(name) is not True]
    if disabled:
        return warn(
            f"welcome screens are not disabled: {', '.join(disabled)}",
            remedy=remedy,
        )
    return ok("welcome screens and the new user tour are disabled")


def checks() -> List[Check]:
    return [
        Check("viya.reachable", "viya", "Viya reachable", _reachable, requires=("client.config",)),
        Check("viya.user-login", "viya", "Test user login", _login, requires=("viya.reachable",)),
        Check(
            "viya.user-not-admin",
            "viya",
            "Test user is not an administrator",
            _not_admin,
            requires=("viya.user-login",),
        ),
        Check(
            "viya.compute-contexts",
            "viya",
            "Compute contexts",
            _compute_contexts,
            requires=("viya.user-login",),
        ),
        Check(
            "viya.html-commons",
            "viya",
            "Welcome screens disabled",
            _html_commons,
            requires=("viya.user-login",),
        ),
    ]
