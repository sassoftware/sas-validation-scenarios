# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Resolve access tokens for private release repositories."""

import os
import subprocess
from dataclasses import dataclass
from typing import Callable, Mapping, Optional
from urllib.parse import urlparse

from .providers import RepositoryAlias

RELEASE_TOKEN_ENV = "SAS_VALIDATION_RELEASE_TOKEN"
SUBPROCESS_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class ResolvedToken:
    value: str
    source: str


def repository_host(repository: RepositoryAlias) -> str:
    """Host of the GitLab instance; one token serves every alias on that host."""
    base_url = repository.base_url or "https://gitlab.com"
    parsed = urlparse(base_url if "//" in base_url else f"https://{base_url}")
    return parsed.netloc or base_url


def _run(command: list[str], stdin: Optional[str] = None, env: Optional[Mapping[str, str]] = None):
    try:
        return subprocess.run(
            command,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def glab_token(host: str) -> Optional[str]:
    result = _run(["glab", "config", "get", "token", "--host", host])
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip() or None


def git_credential_token(host: str) -> Optional[str]:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    result = _run(
        ["git", "credential", "fill"],
        stdin=f"protocol=https\nhost={host}\n\n",
        env=env,
    )
    if result is None or result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("password="):
            return line[len("password="):].strip() or None
    return None


def resolve_gitlab_token(
    repository: RepositoryAlias, environ: Optional[Mapping[str, str]] = None
) -> Optional[ResolvedToken]:
    """Return the first token found, preferring explicit sources over discovered ones."""
    environ = os.environ if environ is None else environ
    host = repository_host(repository)
    env_token = environ.get(RELEASE_TOKEN_ENV)
    if env_token:
        return ResolvedToken(env_token, f"environment variable {RELEASE_TOKEN_ENV}")

    sources: list[tuple[str, Callable[[str], Optional[str]]]] = [
        ("the glab CLI configuration", glab_token),
        ("the git credential helper", git_credential_token),
    ]
    for description, lookup in sources:
        token = lookup(host)
        if token:
            return ResolvedToken(token, f"{description} for {host}")
    return None
