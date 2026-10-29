# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Release-provider interfaces for GitHub and GitLab scenario packages."""

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    """Raised when a release provider cannot resolve an asset."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class RepositoryAlias:
    name: str
    provider: str
    repository: str
    visibility: str = "public"
    base_url: Optional[str] = None


@dataclass(frozen=True)
class ReleaseAsset:
    repository: RepositoryAlias
    version: str
    name: str
    url: str
    checksum_url: Optional[str] = None


@dataclass(frozen=True)
class ReleaseSummary:
    repository: RepositoryAlias
    version: str
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    created_at: Optional[str] = None
    published_at: Optional[str] = None
    draft: bool = False
    prerelease: bool = False
    assets: tuple[Mapping[str, Any], ...] = ()

    @property
    def display_version(self) -> str:
        """The version without the tag's leading 'v', as users type and see it elsewhere."""
        value = self.version.strip()
        if len(value) > 1 and value[0] in "vV" and value[1].isdigit():
            return value[1:]
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository.name,
            "version": self.display_version,
            "tag": self.version,
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "created-at": self.created_at,
            "published-at": self.published_at,
            "draft": self.draft,
            "prerelease": self.prerelease,
            "assets": [dict(asset) for asset in self.assets],
        }


Transport = Callable[[Request], bytes]


def candidate_tags(version: str) -> list[str]:
    """Release tags to try for a user-supplied version: as given, then with/without 'v'."""
    value = version.strip()
    if len(value) > 1 and value[0] in "vV" and value[1].isdigit():
        return [value, value[1:]]
    if value[:1].isdigit():
        return [value, f"v{value}"]
    return [value]


def default_transport(request: Request) -> bytes:
    try:
        with urlopen(request) as response:
            return response.read()
    except HTTPError as error:
        raise ProviderError(f"Release request failed: {error}", status=error.code) from error
    except URLError as error:
        raise ProviderError(f"Release request failed: {error}") from error


class ReleaseProvider:
    """Resolve a named release asset from one repository."""

    def __init__(
        self,
        repository: RepositoryAlias,
        token: Optional[str] = None,
        transport: Transport = default_transport,
    ):
        self.repository = repository
        self.token = token
        self.transport = transport

    def _fetch_assets(self, version: str) -> list[ReleaseAsset]:
        """Fetch release assets, accepting the version with or without a leading 'v'.

        The version is tried exactly as given first; on a 404 the alternate form is tried
        (``2026.09`` -> ``v2026.09`` and vice versa). The returned assets carry the tag that
        actually matched. Releases are looked up by tag, so same-named branches never match.
        """
        first_error: Optional[ProviderError] = None
        for tag in candidate_tags(version):
            try:
                return self._fetch_release_assets(tag)
            except ProviderError as error:
                if error.status != 404:
                    raise
                if first_error is None:
                    first_error = error
        assert first_error is not None
        raise first_error

    def _fetch_release_assets(self, tag: str) -> list[ReleaseAsset]:
        raise NotImplementedError

    def find_asset(self, version: str, asset_name: str) -> ReleaseAsset:
        for asset in self._fetch_assets(version):
            if asset.name == asset_name:
                return asset
        raise ProviderError(
            f"Release '{version}' does not contain asset '{asset_name}'"
        )

    def find_tar_asset(self, version: str) -> ReleaseAsset:
        assets = self._fetch_assets(version)
        matches = [a for a in assets if a.name.endswith(".tar.gz")]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ProviderError(f"Release '{version}' contains no .tar.gz asset")
        names = ", ".join(a.name for a in matches)
        raise ProviderError(
            f"Release '{version}' has multiple .tar.gz assets ({names}); use --asset to specify one"
        )

    def list_releases(self) -> list[ReleaseSummary]:
        raise NotImplementedError

    def _request_json_list(self, url: str) -> list:
        request = Request(url, headers=self._headers())
        try:
            payload = json.loads(self.transport(request).decode("utf-8"))
        except ProviderError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderError(f"Invalid release response from {url}") from error
        if not isinstance(payload, list):
            raise ProviderError(f"Release list response from {url} is not an array")
        return payload

    def _request_json(self, url: str) -> Mapping[str, Any]:
        request = Request(url, headers=self._headers())
        try:
            payload = json.loads(self.transport(request).decode("utf-8"))
        except ProviderError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderError(f"Invalid release response from {url}") from error
        if not isinstance(payload, Mapping):
            raise ProviderError(f"Release response from {url} is not an object")
        return payload

    def _request_release(self, url: str, version: str) -> Mapping[str, Any]:
        try:
            return self._request_json(url)
        except ProviderError as error:
            if error.status != 404:
                raise
            raise ProviderError(
                f"Release '{version}' was not found in repository '{self.repository.name}' "
                f"({self.repository.repository}){self._not_found_note()}",
                status=404,
            ) from error

    def _not_found_note(self) -> str:
        # GitHub and GitLab answer 404 rather than 403 for private repositories the caller cannot see.
        if self.token or self.repository.visibility == "public":
            return ""
        return ". If the repository is private, make sure a valid access token is available"

    def _download_request(self, url: str) -> Request:
        return Request(url, headers=self._headers())

    def _headers(self) -> Mapping[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "sas-validation"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers


class GitHubReleaseProvider(ReleaseProvider):
    """Resolve assets from a GitHub Release identified by tag."""

    def _fetch_release_assets(self, version: str) -> list[ReleaseAsset]:
        base_url = self.repository.base_url or "https://api.github.com"
        endpoint = (
            f"{base_url.rstrip('/')}/repos/{self.repository.repository}/releases/tags/"
            f"{quote(version, safe='')}"
        )
        release = self._request_release(endpoint, version)
        raw_assets = release.get("assets")
        if not isinstance(raw_assets, list):
            raise ProviderError(f"GitHub release '{version}' has no asset list")
        result = []
        for asset in raw_assets:
            if isinstance(asset, Mapping):
                name = asset.get("name")
                url = asset.get("browser_download_url")
                if isinstance(name, str) and name and isinstance(url, str) and url:
                    result.append(ReleaseAsset(self.repository, version, name, url))
        return result

    def list_releases(self) -> list[ReleaseSummary]:
        base_url = self.repository.base_url or "https://api.github.com"
        endpoint = f"{base_url.rstrip('/')}/repos/{self.repository.repository}/releases?per_page=100"
        releases = self._request_json_list(endpoint)
        result = []
        for release in releases:
            if not isinstance(release, Mapping):
                continue
            version = release.get("tag_name")
            if not isinstance(version, str) or not version:
                continue
            assets = []
            for asset in release.get("assets", []):
                if not isinstance(asset, Mapping) or not isinstance(asset.get("name"), str):
                    continue
                assets.append(
                    {
                        "name": asset["name"],
                        "url": asset.get("browser_download_url"),
                        "size": asset.get("size"),
                        "download-count": asset.get("download_count"),
                    }
                )
            result.append(
                ReleaseSummary(
                    repository=self.repository,
                    version=version,
                    name=release.get("name") if isinstance(release.get("name"), str) else None,
                    description=release.get("body") if isinstance(release.get("body"), str) else None,
                    url=release.get("html_url") if isinstance(release.get("html_url"), str) else None,
                    created_at=release.get("created_at") if isinstance(release.get("created_at"), str) else None,
                    published_at=release.get("published_at") if isinstance(release.get("published_at"), str) else None,
                    draft=release.get("draft") is True,
                    prerelease=release.get("prerelease") is True,
                    assets=tuple(assets),
                )
            )
        return result


class GitLabReleaseProvider(ReleaseProvider):
    """Resolve assets from a GitLab Release identified by tag."""

    def _headers(self) -> Mapping[str, str]:
        headers = dict(super()._headers())
        if self.token:
            headers.pop("Authorization", None)
            headers["PRIVATE-TOKEN"] = self.token
        return headers

    def _fetch_release_assets(self, version: str) -> list[ReleaseAsset]:
        project = quote(self.repository.repository, safe="")
        base_url = self.repository.base_url or "https://gitlab.com"
        endpoint = f"{base_url.rstrip('/')}/api/v4/projects/{project}/releases/{quote(version, safe='')}"
        release = self._request_release(endpoint, version)
        assets = release.get("assets")
        links = assets.get("links") if isinstance(assets, Mapping) else None
        if not isinstance(links, list):
            raise ProviderError(f"GitLab release '{version}' has no asset links")
        result = []
        for asset in links:
            if isinstance(asset, Mapping):
                name = asset.get("name")
                url = asset.get("direct_asset_url") or asset.get("url")
                if isinstance(name, str) and name and isinstance(url, str) and url:
                    result.append(ReleaseAsset(self.repository, version, name, url))
        return result

    def list_releases(self) -> list[ReleaseSummary]:
        project = quote(self.repository.repository, safe="")
        base_url = self.repository.base_url or "https://gitlab.com"
        endpoint = f"{base_url.rstrip('/')}/api/v4/projects/{project}/releases?per_page=100"
        releases = self._request_json_list(endpoint)
        result = []
        for release in releases:
            if not isinstance(release, Mapping):
                continue
            version = release.get("tag_name")
            if not isinstance(version, str) or not version:
                continue
            raw_assets = release.get("assets")
            assets = []
            for asset in raw_assets.get("links", []) if isinstance(raw_assets, Mapping) else []:
                if not isinstance(asset, Mapping) or not isinstance(asset.get("name"), str):
                    continue
                assets.append(
                    {
                        "name": asset["name"],
                        "url": asset.get("direct_asset_url") or asset.get("url"),
                        "size": asset.get("size"),
                        "download-count": asset.get("download_count"),
                    }
                )
            result.append(
                ReleaseSummary(
                    repository=self.repository,
                    version=version,
                    name=release.get("name") if isinstance(release.get("name"), str) else None,
                    description=release.get("description") if isinstance(release.get("description"), str) else None,
                    url=(release.get("_links", {}).get("self") if isinstance(release.get("_links"), Mapping) else None),
                    created_at=release.get("created_at") if isinstance(release.get("created_at"), str) else None,
                    published_at=release.get("released_at") if isinstance(release.get("released_at"), str) else None,
                    assets=tuple(assets),
                )
            )
        return result


def create_provider(
    repository: RepositoryAlias,
    token: Optional[str] = None,
    transport: Transport = default_transport,
) -> ReleaseProvider:
    """Create a provider from a configured repository alias."""
    providers = {
        "github-release": GitHubReleaseProvider,
        "gitlab-release": GitLabReleaseProvider,
    }
    provider_class = providers.get(repository.provider)
    if provider_class is None:
        raise ProviderError(f"Unsupported release provider '{repository.provider}'")
    return provider_class(repository, token=token, transport=transport)
