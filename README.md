# gh_md_extract

A small Python package that provides both a library function and command line tool
for extracting every Markdown file from a chosen subdirectory in a GitHub
repository. The utility supports private repositories via GitHub personal access
tokens (PATs) and can be embedded in other Python projects.

## Installation

```bash
pip install .
```

To run the automated tests the optional "test" extras can be installed:

```bash
pip install .[test]
```

## Command line usage

```bash
gh-md-extract <repository> <subdirectory> <destination> [--token TOKEN] [--ref REF]
```

* `repository` – GitHub repository in the form `owner/name` or a HTTPS URL.
* `subdirectory` – Directory under the repository to scan. Use `.` for the root.
* `destination` – Local directory where downloaded Markdown files will be stored.
* `--token` – Optional GitHub personal access token. Falls back to `GITHUB_TOKEN`.
* `--ref` – Optional branch, tag, or commit SHA to download from.

The command prints the local path of every Markdown file written to disk.

## Library usage

```python
from gh_md_extract import extract_markdown_files

files = extract_markdown_files(
    "octocat/hello-world",
    "docs",
    "/tmp/output",
    token="ghp_your_token_here",
    ref="main",
)

for path in files:
    print(path)
```

The function returns the list of :class:`pathlib.Path` objects pointing to the
files that were written. Authentication is optional for public repositories but
recommended to avoid hitting unauthenticated rate limits.

## Development

Run the unit test suite using:

```bash
pytest
```

