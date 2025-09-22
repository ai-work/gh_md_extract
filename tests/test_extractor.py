from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import pytest

from gh_md_extract import GitHubAPIError, extract_markdown_files


@dataclass
class _FakeResponse:
    status_code: int
    _json: object | None = None
    content: bytes = b""

    def json(self):
        return self._json


class _FakeSession:
    def __init__(self, responses: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], _FakeResponse]):
        self._responses = responses
        self.calls: list[Tuple[str, dict | None, dict | None]] = []

    def get(self, url: str, headers: dict | None = None, params: dict | None = None):
        params_tuple = tuple(sorted((params or {}).items()))
        key = (url, params_tuple)
        self.calls.append((url, headers, params))
        try:
            return self._responses[key]
        except KeyError as exc:  # pragma: no cover - protective assertion
            raise AssertionError(f"Unexpected request for {url} with {params}") from exc

    def close(self):
        pass


def _build_key(url: str, params: dict | None = None) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
    params_tuple: Tuple[Tuple[str, str], ...] = tuple(sorted((params or {}).items()))
    return url, params_tuple


def test_extract_markdown_files(tmp_path: Path) -> None:
    repo_api = "https://api.github.com/repos/octocat/hello-world"
    responses_map = {
        _build_key(f"{repo_api}/contents/docs", {"ref": "main"}): _FakeResponse(
            200,
            [
                {
                    "name": "README.md",
                    "path": "docs/README.md",
                    "type": "file",
                    "url": f"{repo_api}/contents/docs/README.md",
                },
                {
                    "name": "guides",
                    "path": "docs/guides",
                    "type": "dir",
                },
                {
                    "name": "image.png",
                    "path": "docs/image.png",
                    "type": "file",
                    "url": f"{repo_api}/contents/docs/image.png",
                },
            ],
        ),
        _build_key(f"{repo_api}/contents/docs/guides", {"ref": "main"}): _FakeResponse(
            200,
            [
                {
                    "name": "setup.md",
                    "path": "docs/guides/setup.md",
                    "type": "file",
                    "url": f"{repo_api}/contents/docs/guides/setup.md",
                }
            ],
        ),
        _build_key(f"{repo_api}/contents/docs/README.md", {"ref": "main"}): _FakeResponse(
            200,
            content=b"Root docs",
        ),
        _build_key(
            f"{repo_api}/contents/docs/guides/setup.md", {"ref": "main"}
        ): _FakeResponse(200, content=b"Setup guide"),
    }

    fake_session = _FakeSession(responses_map)

    files = extract_markdown_files(
        "octocat/hello-world",
        "docs",
        tmp_path,
        token="token",
        ref="main",
        session=fake_session,
    )

    expected = {tmp_path / "README.md", tmp_path / "guides" / "setup.md"}
    assert set(files) == expected
    assert (tmp_path / "README.md").read_text() == "Root docs"
    assert (tmp_path / "guides" / "setup.md").read_text() == "Setup guide"
    assert not (tmp_path / "image.png").exists()


def test_missing_directory_raises_error(tmp_path: Path) -> None:
    repo_api = "https://api.github.com/repos/octocat/hello-world"
    responses_map = {
        _build_key(f"{repo_api}/contents/docs", None): _FakeResponse(404, {"message": "Not Found"})
    }
    fake_session = _FakeSession(responses_map)

    with pytest.raises(GitHubAPIError):
        extract_markdown_files("octocat/hello-world", "docs", tmp_path, session=fake_session)


def test_invalid_repository_string(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        extract_markdown_files("invalid-repo", "docs", tmp_path)

