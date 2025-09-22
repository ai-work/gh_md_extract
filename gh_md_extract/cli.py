"""Command line entry point for :mod:`gh_md_extract`."""

from __future__ import annotations

import argparse
import os
import sys

from .extractor import GitHubAPIError, extract_markdown_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download all Markdown files from a subdirectory in a GitHub repository"
        )
    )
    parser.add_argument(
        "repository",
        help="GitHub repository in the form 'owner/name' or HTTPS URL",
    )
    parser.add_argument(
        "subdirectory",
        help="Repository subdirectory to scan (use '.' for the repository root)",
    )
    parser.add_argument(
        "destination",
        help="Local destination directory where Markdown files will be written",
    )
    parser.add_argument(
        "--token",
        help=(
            "GitHub personal access token. If omitted the GITHUB_TOKEN environment "
            "variable is used when available."
        ),
    )
    parser.add_argument(
        "--ref",
        help="Git reference (branch, tag, or commit) to use. Defaults to default branch.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    token = args.token or os.getenv("GITHUB_TOKEN")

    try:
        files = extract_markdown_files(
            args.repository,
            args.subdirectory,
            args.destination,
            token=token,
            ref=args.ref,
        )
    except (GitHubAPIError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")

    for path in files:
        print(path)

    return 0


if __name__ == "__main__":  # pragma: no cover - convenience for manual use
    sys.exit(main())

