# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from scenario_package import cli, credentials
from scenario_package.credentials import resolve_gitlab_token, repository_host
from scenario_package.providers import ProviderError, RepositoryAlias

REPO = RepositoryAlias(
    "internal", "gitlab-release", "group/project", base_url="https://gitlab.example.com/"
)


def _completed(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, returncode=returncode)


class ResolveTokenTests(unittest.TestCase):
    def test_host_comes_from_base_url_or_defaults_to_gitlab_com(self):
        self.assertEqual(repository_host(REPO), "gitlab.example.com")
        self.assertEqual(
            repository_host(RepositoryAlias("a", "gitlab-release", "g/p")), "gitlab.com"
        )

    def test_environment_variable_wins_over_discovered_sources(self):
        with patch.object(credentials, "glab_token", return_value="from-glab"):
            token = resolve_gitlab_token(REPO, {"SAS_VALIDATION_RELEASE_TOKEN": "from-env"})

        self.assertEqual(token.value, "from-env")

    def test_glab_then_git_credential(self):
        with patch.object(credentials, "glab_token", return_value="g"), patch.object(
            credentials, "git_credential_token", return_value="c"
        ):
            self.assertEqual(resolve_gitlab_token(REPO, {}).value, "g")
        with patch.object(credentials, "glab_token", return_value=None), patch.object(
            credentials, "git_credential_token", return_value="c"
        ):
            token = resolve_gitlab_token(REPO, {})
        self.assertEqual(token.value, "c")
        self.assertIn("gitlab.example.com", token.source)

    def test_returns_none_when_nothing_is_found(self):
        with patch.object(credentials, "glab_token", return_value=None), patch.object(
            credentials, "git_credential_token", return_value=None
        ):
            self.assertIsNone(resolve_gitlab_token(REPO, {}))

    def test_glab_token_queries_the_host(self):
        with patch.object(credentials, "_run", return_value=_completed("glpat-1\n")) as run:
            self.assertEqual(credentials.glab_token("gitlab.example.com"), "glpat-1")
        self.assertEqual(
            run.call_args.args[0],
            ["glab", "config", "get", "token", "--host", "gitlab.example.com"],
        )

    def test_glab_token_is_none_when_glab_is_missing_or_fails(self):
        with patch.object(credentials, "_run", return_value=None):
            self.assertIsNone(credentials.glab_token("h"))
        with patch.object(credentials, "_run", return_value=_completed("", returncode=1)):
            self.assertIsNone(credentials.glab_token("h"))

    def test_git_credential_token_reads_password_without_prompting(self):
        output = "protocol=https\nhost=h\nusername=me\npassword=secret\n"
        with patch.object(credentials, "_run", return_value=_completed(output)) as run:
            self.assertEqual(credentials.git_credential_token("h"), "secret")
        self.assertEqual(run.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")
        self.assertIn("host=h", run.call_args.kwargs["stdin"])


class AuthCommandTests(unittest.TestCase):
    def _invoke(self, *args, input=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        repositories = Path(directory.name) / "repositories.yaml"
        repositories.write_text(
            "scenario-repositories:\n"
            "  internal: {provider: gitlab-release, repository: group/project,"
            " base-url: 'https://gitlab.example.com'}\n"
            "  public: {provider: github-release, repository: org/repo}\n",
            encoding="utf-8",
        )
        return CliRunner().invoke(
            cli.app, ["--repositories", str(repositories), "auth", *args], input=input
        )

    def test_status_rejects_non_gitlab_repository(self):
        result = self._invoke("status", "--repo", "public")

        self.assertEqual(result.exit_code, 2)
        self.assertIn("not a GitLab repository", result.output)

    def test_status_fails_with_guidance_when_no_token_is_found(self):
        with patch.object(cli, "resolve_gitlab_token", return_value=None):
            result = self._invoke("status", "--repo", "internal")

        self.assertEqual(result.exit_code, 2)
        self.assertIn("glab auth login --hostname gitlab.example.com", result.output)

    def test_status_names_the_source_without_printing_the_token(self):
        token = credentials.ResolvedToken("glpat-secret", "the glab CLI configuration")
        with patch.object(cli, "resolve_gitlab_token", return_value=token):
            result = self._invoke("status", "--repo", "internal")

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("the glab CLI configuration", result.output)
        self.assertNotIn("glpat-secret", result.output)

    def test_unauthorized_response_names_the_token_source(self):
        token = credentials.ResolvedToken("t", "the glab CLI configuration")
        message = cli._with_token_hint(ProviderError("HTTP 401", status=401), token)

        self.assertIn("the glab CLI configuration", message)
        self.assertIn("glab auth login", message)
        self.assertEqual(cli._with_token_hint(ProviderError("HTTP 404", status=404), token), "HTTP 404")


if __name__ == "__main__":
    unittest.main()
