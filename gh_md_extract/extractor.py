"""Core extraction utilities for :mod:`gh_md_extract`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional, Protocol
from urllib import parse, request
from urllib.parse import urlparse

__all__ = ["GitHubAPIError", "extract_markdown_files"]


class GitHubAPIError(RuntimeError):
    """Raised when the GitHub API returns an error response."""


class _ResponseProtocol(Protocol):
    status_code: int
    content: bytes

    def json(self) -> object:
        """Return the JSON-decoded payload."""


class _SessionProtocol(Protocol):
    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> _ResponseProtocol:
        ...

    def close(self) -> None:
        ...


@dataclass(frozen=True)
class _RepoSpec:
    owner: str
    name: str

    @property
    def api_base(self) -> str:
        return f"https://api.github.com/repos/{self.owner}/{self.name}"


class _UrllibResponse:
    def __init__(self, status_code: int, data: bytes):
        self.status_code = status_code
        self._data = data

    @property
    def content(self) -> bytes:
        return self._data

    def json(self) -> object:
        try:
            text = self._data.decode("utf-8")
        except UnicodeDecodeError as exc:  # pragma: no cover - unexpected
            raise GitHubAPIError("Unable to decode GitHub response as UTF-8") from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:  # pragma: no cover - unexpected
            raise GitHubAPIError("Unable to parse JSON payload from GitHub") from exc


class _UrllibSession:
    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> _UrllibResponse:
        if params:
            query = parse.urlencode(params)
            separator = "&" if parse.urlparse(url).query else "?"
            url = f"{url}{separator}{query}"
        req = request.Request(url, headers=headers or {}, method="GET")
        with request.urlopen(req) as resp:  # type: ignore[call-arg]
            data = resp.read()
            status = getattr(resp, "status", 200)
        return _UrllibResponse(status, data)

    def close(self) -> None:  # pragma: no cover - nothing to clean up
        return None


def extract_markdown_files(
    repository: str,
    subdirectory: str,
    destination: str | Path,
    *,
    token: str | None = None,
    ref: str | None = None,
    session: Optional[_SessionProtocol] = None,
) -> list[Path]:
    """Download all Markdown files from ``subdirectory`` within ``repository``.

    Parameters
    ----------
    repository:
        The repository identifier. Either ``"owner/name"`` or a GitHub HTTPS URL.
    subdirectory:
        The path to search within the repository. Use ``"."`` or ``""`` for the
        repository root.
    destination:
        Directory where the Markdown files will be written. The directory is
        created if it does not yet exist.
    token:
        Optional GitHub personal access token used for authenticating to private
        repositories or to avoid rate limits.
    ref:
        Optional Git reference (branch, tag, or commit SHA). Defaults to the
        repository's default branch.
    session:
        Optional HTTP session-like object with a :py:meth:`get` method returning a
        response that implements :py:meth:`json` and the ``content`` attribute.

    Returns
    -------
    list[Path]
        A list of file paths that were written to the local filesystem.
    """

    repo_spec = _parse_repository(repository)
    base_subdir = _normalise_subdirectory(subdirectory)
    destination_path = Path(destination)
    destination_path.mkdir(parents=True, exist_ok=True)

    req_session = session or _UrllibSession()
    headers = _build_headers(token)
    params = {"ref": ref} if ref else None

    collected: list[Path] = []
    try:
        for item in _iter_markdown_items(
            req_session, repo_spec, base_subdir, headers, params
        ):
            relative_path = _relative_to_subdir(item.path, base_subdir)
            local_path = destination_path.joinpath(Path(*relative_path.parts))
            local_path.parent.mkdir(parents=True, exist_ok=True)
            content = _download_file(req_session, item.url, headers, params)
            local_path.write_bytes(content)
            collected.append(local_path)
    finally:
        if session is None:
            req_session.close()

    return collected


@dataclass(frozen=True)
class _ContentItem:
    path: PurePosixPath
    url: str


def _build_headers(token: str | None) -> dict[str, str]:
    headers = {"User-Agent": "gh-md-extract"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _download_file(
    session: _SessionProtocol,
    url: str,
    headers: dict[str, str],
    params: Optional[dict[str, str]] = None,
) -> bytes:
    raw_headers = {**headers, "Accept": "application/vnd.github.raw"}
    response = session.get(url, headers=raw_headers, params=params)
    if response.status_code != 200:
        raise GitHubAPIError(
            f"GitHub returned status {response.status_code} while downloading {url}"
        )
    return response.content


def _iter_markdown_items(
    session: _SessionProtocol,
    repo_spec: _RepoSpec,
    subdirectory: str,
    headers: dict[str, str],
    params: Optional[dict[str, str]],
) -> Iterable[_ContentItem]:
    queue = [_as_posix(subdirectory)]
    base_url = repo_spec.api_base + "/contents"

    while queue:
        current = queue.pop()
        url = base_url if current == "" else f"{base_url}/{current}"
        response = session.get(url, headers=headers, params=params)
        if response.status_code == 404:
            raise GitHubAPIError(
                f"Path '{current or '.'}' was not found in repository"
            )
        if response.status_code != 200:
            raise GitHubAPIError(
                f"GitHub returned status {response.status_code} for {url}"
            )

        payload = response.json()
        if isinstance(payload, dict) and payload.get("type") == "file":
            if _is_markdown_file(payload.get("name", "")):
                yield _ContentItem(PurePosixPath(payload["path"]), payload["url"])
            continue

        if not isinstance(payload, list):
            raise GitHubAPIError("Unexpected response format from GitHub API")

        for item in payload:
            item_type = item.get("type")
            if item_type == "dir":
                queue.append(item["path"])
            elif item_type == "file" and _is_markdown_file(item.get("name", "")):
                yield _ContentItem(PurePosixPath(item["path"]), item["url"])


def _is_markdown_file(filename: str) -> bool:
    lower = filename.lower()
    return lower.endswith(".md") or lower.endswith(".markdown")


def _relative_to_subdir(path: PurePosixPath, subdirectory: str) -> PurePosixPath:
    base = PurePosixPath(_as_posix(subdirectory))
    if str(base) in ("", "."):
        return path
    try:
        return path.relative_to(base)
    except ValueError as exc:  # pragma: no cover - safeguard, should not occur
        raise GitHubAPIError(
            f"Unable to compute relative path for '{path}' within '{base}'"
        ) from exc


def _normalise_subdirectory(subdirectory: str) -> str:
    as_posix = _as_posix(subdirectory)
    if as_posix in ("", "."):
        return ""
    return as_posix


def _as_posix(path: str) -> str:
    return str(PurePosixPath(path.strip().strip("/"))) if path else ""


def _parse_repository(repository: str) -> _RepoSpec:
    repository = repository.strip()
    if not repository:
        raise ValueError("Repository must be provided")

    if repository.startswith("http://") or repository.startswith("https://"):
        parsed = urlparse(repository)
        path = parsed.path.rstrip("/")
        parts = [part for part in path.split("/") if part]
        if len(parts) < 2:
            raise ValueError(
                "Repository URL must be in the form https://github.com/owner/name"
            )
        owner, name = parts[0], parts[1]
    else:
        parts = [part for part in repository.split("/") if part]
        if len(parts) != 2:
            raise ValueError(
                "Repository must be provided as 'owner/name' or a GitHub URL"
            )
        owner, name = parts

    if name.endswith(".git"):
        name = name[:-4]

    return _RepoSpec(owner=owner, name=name)


