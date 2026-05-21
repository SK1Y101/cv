#!/usr/bin/env python3
"""
Daily synchronisation script: fetches public repos from configured GitHub owners and
parses sk1y101.github.io/projects/ for new entries, detects ones not yet in
details.tex, generates descriptions via LLM, and inserts new \addproject
entries. Also marks stale projects (6+ months without commits) as completed.

Usage:
    python3 scripts/sync_repos.py [--dry-run]

Environment:
    GITHUB_TOKEN      - GitHub API token (required for API calls)
    LLM_API_KEY       - LLM API key (defaults to GITHUB_TOKEN for GitHub Models)
    LLM_MODEL         - Model name (default: deepseek/deepseek-v4-flash:free)
    LLM_ENDPOINT      - API endpoint (default: https://openrouter.ai/api/v1)
"""

import time
import random
import os
import sys
import re
import json
import subprocess
import urllib.request
import urllib.error
import urllib.parse
import html.parser
from datetime import date
from pathlib import Path
from typing import Optional

REPO_DIR = Path(__file__).resolve().parent.parent
DETAILS_TEX = REPO_DIR / "details.tex"
TEX2JSON = REPO_DIR / "scripts/tex2json.py"

STALENESS_DAYS = 180  # 6 months
WEBSITE_URL = "https://sk1y101.github.io/projects/"

# Minimum start dates per organisation (GitHub owner).
# When a repo's `created_at` falls after this date, the organisation date is
# used instead — handles projects that migrated to GitHub long after they
# began (e.g. MAAS repos that lived on Launchpad for 15+ years).
# The value is the user's employment start at that organisation.
ORG_START_DATES = {
    "canonical": "2022-06-14",
    "maas": "2022-06-14",
}

# GitHub owners to scan for new repos
OWNERS = [
    "SK1Y101",
    "SkiylianSoftware",
]

# Orgs to scan for repos the user has personally committed to
CONTRIBUTION_ORGS = ["canonical"]

# The user's GitHub username, used to filter contribution orgs and to find
# their first/last commit dates in a repo.
GITHUB_USERNAME = "SK1Y101"

# Fallback models for OpenRouter – tried in order when the primary is
# rate-limited upstream.  All must be free-tier variants (queried from
# ``/api/v1/models`` on 2026-05-20).
FALLBACK_MODELS = [
    "deepseek/deepseek-v4-flash:free",
    "google/gemma-4-26b-a4b-it:free",
    "qwen/qwen3-coder:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "minimax/minimax-m2.5:free",
    "openai/gpt-oss-20b:free",
]

# Icon mapping by repo topics / language
ICON_MAP = {
    "code": "code",
    "terraform": "code",
    "hcl": "code",
    "ansible": "code",
    "jenkins": "code",
    "ci": "code",
    "packer": "code",
    "documentation": "code",
    "docs": "code",
    "cli": "code",
    "api": "code",
    "sdk": "code",
    "library": "code",
    "python": "code",
    "go": "code",
    "compiler": "proj",
    "language": "proj",
    "interpreter": "proj",
    "game": "proj",
    "hardware": "proj",
    "watchface": "proj",
    "clock": "proj",
    "fitbit": "proj",
    "publication": "pub",
    "paper": "pub",
    "thesis": "pub",
    "research": "pub",
    "arxiv": "pub",
    "talk": "talk",
    "webinar": "talk",
    "presentation": "talk",
    "conference": "talk",
    "ml": None,
    "machine-learning": None,
    "data-science": None,
    "data": None,
    "computer-vision": None,
    "cv": None,
    "deep-learning": None,
    "tensorflow": None,
    "keras": None,
}

LANGUAGE_ICON = {
    "Python": "code",
    "Go": "code",
    "Rust": "code",
    "C": "code",
    "C++": "code",
    "Java": "code",
    "TypeScript": "code",
    "JavaScript": "code",
    "HTML": None,
    "CSS": None,
    "Shell": "code",
    "Makefile": "code",
    "Dockerfile": "code",
    "HCL": "code",
    "KerboScript": "proj",
}

# Example descriptions for LLM style prompting
EXAMPLE_DESCRIPTIONS = """\
Python automation suite managing YouTube channel operations. Handles automatic playlist population from video titles, two-way Google Calendar synchronisation for release scheduling, and automated background music selection for video editing in Shotcut. Demonstrates OAuth, Google APIs, and event-driven pipeline architecture.

Locally-hosted web application that streams YouTube audio to Bluetooth-connected devices, curated by weather and time of day. Successor to AutoBreezeBeats (2024), adding an orchestrator for automatic queuing from a database, a song metadata UI, and multi-process architecture managed through nox. Uses OpenWeatherMap API for context-aware music selection and ffmpeg for audio processing.

CLI tooling providing automated documentation quality checks for the MAAS team. Wraps aspell, proselint, linkchecker, and style-checking utilities in a unified interface, enabling CI pipeline integration for doc PRs.\
"""


def log(msg: str):
    print(f"[sync] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Rate-limit state tracking for LLM (OpenRouter) and GitHub API
# ---------------------------------------------------------------------------
_RATE_LIMIT = {
    "remaining": None,  # X-RateLimit-Remaining
    "reset_at": None,   # X-RateLimit-Reset (unix timestamp)
}

_GH_RATE_LIMIT = {
    "remaining": None,
    "reset_at": None,
}


def _update_rate_limit(headers: dict, *, gh: bool = False) -> None:
    """Track rate-limit state from response headers returned on every request."""
    state = _GH_RATE_LIMIT if gh else _RATE_LIMIT
    remaining = headers.get("X-RateLimit-Remaining")
    reset = headers.get("X-RateLimit-Reset")
    if remaining is not None:
        try:
            state["remaining"] = int(remaining)
        except (ValueError, TypeError):
            pass
    if reset is not None:
        try:
            state["reset_at"] = int(reset)
        except (ValueError, TypeError):
            pass


def _proactive_delay(gh: bool = False) -> None:
    """If fewer than 2 requests remain, wait until the reset window."""
    state = _GH_RATE_LIMIT if gh else _RATE_LIMIT
    remaining = state["remaining"]
    reset_at = state["reset_at"]
    if remaining is not None and reset_at is not None and remaining < 2:
        wait = max(0, reset_at - time.time())
        if wait > 0:
            tag = "GitHub" if gh else "LLM"
            log(f"{tag} rate limit low ({remaining} remaining), pausing {wait:.0f}s until reset")
            time.sleep(wait + 1)


def _retry_after_from_response(e: urllib.error.HTTPError, body: str) -> float | None:
    """Extract exact retry-after seconds from a 429/503 response.

    Priority:
    1. ``Retry-After`` HTTP response header (standard).
    2. ``X-RateLimit-Reset`` HTTP header (Unix timestamp — compute ``reset - now``).
    3. ``error.metadata.retry_after_seconds`` in the JSON body (OpenRouter).
    4. ``error.metadata.headers.Retry-After`` in the JSON body (deep fallback).
    5. Parse a number from ``error.metadata.raw`` string (OpenRouter upstream).

    Returns ``None`` when the wait would exceed 1 hour — retrying then is
    pointless (it signals a daily-limit exhaustion rather than an RPM blip).
    """
    now = time.time()

    # 1. HTTP Retry-After header (seconds or HTTP-date)
    http_retry = e.headers.get("Retry-After")
    if http_retry is not None:
        try:
            seconds = float(http_retry)
            return None if seconds > 3600 else seconds
        except (ValueError, TypeError):
            pass

    # 2. X-RateLimit-Reset header (Unix timestamp)
    reset_ts = e.headers.get("X-RateLimit-Reset")
    if reset_ts is not None:
        try:
            seconds = float(reset_ts) - now
            return None if seconds > 3600 else max(seconds, 1)
        except (ValueError, TypeError):
            pass

    # 3 / 4 / 5. JSON body
    if body:
        try:
            parsed = json.loads(body)
            meta = parsed.get("error", {}).get("metadata", {})

            raw_seconds = meta.get("retry_after_seconds") or meta.get("retry_after_seconds_raw")
            if raw_seconds is not None:
                seconds = float(raw_seconds)
                return None if seconds > 3600 else seconds

            body_retry = meta.get("headers", {}).get("Retry-After")
            if body_retry is not None:
                seconds = float(body_retry)
                return None if seconds > 3600 else seconds

            # OpenRouter upstream rate limits put a human-readable string in
            # ``raw``; try to extract any numeric seconds value from it.
            raw_text = meta.get("raw", "")
            m = re.search(r"(\d+)\s*(?:second|sec|s)", raw_text, re.I)
            if m:
                seconds = float(m.group(1))
                return None if seconds > 3600 else seconds
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    return None


def _api_request(
    payload: dict,
    llm_key: str,
    models: list[str],
    endpoint: str,
    *,
    max_retries: int = 3,
    title: str = "CV-Sync",
) -> str | None:
    """POST *payload* to the LLM endpoint with rate-limit-aware retry and
    model fallback.

    * Tries each model in *models* in order.
    * On 429/503: reads ``Retry-After`` / ``X-RateLimit-Reset`` headers for
      the exact wait time.  If the wait would exceed 1 hour (daily limit)
      retries are skipped entirely for that model.
    * Tracks ``X-RateLimit-*`` headers from every response so we can delay
      proactively before the window is exhausted.
    * Falls back to exponential backoff (5, 10, 20 s) if no retry timing
      information is available.

    Returns the response content text, or ``None`` if all models and all
    retries were exhausted.
    """
    for model in models:
        _proactive_delay(gh=False)
        log(f"  LLM call: {model}")

        for attempt in range(max_retries + 1):
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {llm_key}",
                    "User-Agent": "cv-sync/1.0",
                }
                if "openrouter" in endpoint:
                    headers["HTTP-Referer"] = "https://github.com/SK1Y101/cv"
                    headers["X-Title"] = title
                req = urllib.request.Request(
                    f"{endpoint}/chat/completions",
                    data=json.dumps({**payload, "model": model}).encode(),
                    headers=headers,
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    _update_rate_limit(resp.headers, gh=False)
                    result = json.loads(resp.read())
                    return result["choices"][0]["message"]["content"].strip()

            except urllib.error.HTTPError as e:
                body = e.read().decode() if hasattr(e, "read") else ""

                if e.code in (429, 503) and attempt < max_retries:
                    retry_after = _retry_after_from_response(e, body)
                    if retry_after is None:
                        retry_after = 5 * (2**attempt)

                    jitter = random.uniform(0.9, 1.1)
                    sleep_time = retry_after * jitter
                    log(
                        f"    Rate limited ({e.code}), retrying in "
                        f"{sleep_time:.0f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(sleep_time)
                    continue

                log(f"    {model} failed: HTTP {e.code}- {body[:200]}")

                # Non-retryable status or retries exhausted — try next model
                break

            except Exception as e:
                log(f"    {model} failed: {e}")
                break

    return None


def gh_api(path: str, token: str) -> dict | list:
    """Make a GitHub API GET request with rate-limit-aware retry.

    * Reads ``X-RateLimit-Remaining`` / ``X-RateLimit-Reset`` from every
      response and delays proactively when the limit is near exhaustion.
    * On 403 (rate limit) or 429: reads the ``Retry-After`` header or falls
      back to exponential backoff (5, 10, 20 s).
    * Returns the parsed JSON body, or ``[]`` if all retries are exhausted.
    """
    data, _headers = _gh_api_raw(path, token)
    return data


def _gh_api_raw(path: str, token: str) -> tuple:
    """Like ``gh_api`` but also returns the HTTP response headers.

    Returns ``(parsed_json, http_headers)``, or ``([], {})`` on failure.
    """
    _proactive_delay(gh=True)

    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            url = f"https://api.github.com{path}"
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Bearer {token}")
            accept = "application/vnd.github.cloak-preview" if path.startswith("/search/") else "application/vnd.github.v3+json"
            req.add_header("Accept", accept)
            req.add_header("User-Agent", "cv-sync/1.0")
            with urllib.request.urlopen(req) as resp:
                _update_rate_limit(resp.headers, gh=True)
                return json.loads(resp.read()), resp.headers

        except urllib.error.HTTPError as e:
            body = e.read().decode() if hasattr(e, "read") else ""

            if e.code in (403, 429) and attempt < max_retries:
                retry_after = _retry_after_from_response(e, body)
                if retry_after is None:
                    retry_after = 5 * (2**attempt)

                jitter = random.uniform(0.9, 1.1)
                sleep_time = retry_after * jitter
                log(
                    f"GitHub rate limited ({e.code}) for {path}, "
                    f"retrying in {sleep_time:.0f}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(sleep_time)
                continue

            log(f"GitHub API error {e.code} for {path}: {body[:200]}")
            return [], {}

    return [], {}


def _last_page_from_link(headers: dict) -> int | None:
    """Extract the last page number from a ``Link`` response header.

    The GitHub API includes a ``Link`` header on paginated responses:
      ``<...?page=2>; rel="next", <...?page=5>; rel="last"``
    """
    link = headers.get("Link", "")
    if not link:
        return None
    m = re.search(r'page=(\d+)>;\s*rel="last"', link)
    if m:
        return int(m.group(1))
    return None


def fetch_all_repos(owner: str, token: str) -> list[dict]:
    """Fetch all public repos for an owner (paginated)."""
    repos = []
    page = 1
    while True:
        data = gh_api(f"/users/{owner}/repos?per_page=100&page={page}&type=public", token)
        if not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    return repos


def fetch_user_contributed_repos(org: str, username: str, token: str) -> list[dict]:
    """Fetch repos in *org* that *username* has committed to.

    Uses the commit search API to find every org repo the user has touched,
    then fetches full repo metadata for each.  This avoids pulling hundreds
    of unrelated repos.
    """
    seen = set()
    repos = []
    page = 1

    while True:
        data = gh_api(
            f"/search/commits?q=author:{username}+org:{org}&per_page=100&page={page}",
            token,
        )
        if not data or not isinstance(data, dict):
            break

        for item in data.get("items", []):
            full_name = item.get("repository", {}).get("full_name", "")
            if full_name and full_name not in seen:
                seen.add(full_name)
                repo_data = gh_api(f"/repos/{full_name}", token)
                if repo_data and isinstance(repo_data, dict):
                    repos.append(repo_data)

        if len(data.get("items", [])) < 100:
            break
        page += 1

    log(f"  Found {len(repos)} repos with contributions by {username}")
    return repos


def fetch_commit_dates(
    repo_full: str,
    token: str,
    *,
    only_user: bool = True,
) -> tuple[Optional[str], Optional[str]]:
    """Get the user's first and latest commit dates in *repo_full*.

    Looks up commits authored by ``GITHUB_USERNAME`` on the default branch.
    Paginates via the ``Link`` header to find the user's earliest commit,
    even in repos with 500+ of their commits.

    For organisations in ``ORG_START_DATES`` the first date is clamped to
    that day (handles projects that migrated to GitHub from Launchpad).

    Falls back to the ``created_at`` date from the repo metadata when no
    user commits are found.

    When *only_user* is ``False`` the latest-commit lookup uses any author
    (needed by ``check_staleness``, where we care about project-wide
    activity rather than just the user's).
    """
    username = GITHUB_USERNAME
    first_date = None
    last_date = None

    # ── Latest commit by the user (page 1, first item) ──────────────
    commits, headers = _gh_api_raw(
        f"/repos/{repo_full}/commits?author={username}&per_page=100", token
    )
    if commits and isinstance(commits, list) and commits:
        cd = commits[0].get("commit", {}).get("committer", {}).get("date", "")
        if cd:
            last_date = cd[:10]

    # ── Earliest commit by the user ─────────────────────────────────
    # If fewer than 100 items came back, the last item on page 1 is the
    # earliest.  Otherwise jump to the last page.
    earliest_commits = commits
    if commits and isinstance(commits, list) and len(commits) >= 100:
        last_page = _last_page_from_link(headers)
        if last_page and last_page > 1:
            last_commits, _ = _gh_api_raw(
                f"/repos/{repo_full}/commits?author={username}&per_page=100&page={last_page}",
                token,
            )
            if last_commits and isinstance(last_commits, list) and last_commits:
                earliest_commits = last_commits

    if earliest_commits and isinstance(earliest_commits, list) and earliest_commits:
        cd = earliest_commits[-1].get("commit", {}).get("committer", {}).get("date", "")
        if cd:
            first_date = cd[:10]

    # Fallback: repo creation date
    if not first_date:
        repo_data, _ = _gh_api_raw(f"/repos/{repo_full}", token)
        if repo_data and isinstance(repo_data, dict):
            created = repo_data.get("created_at", "")
            if created:
                first_date = created[:10]

    # Clamp first_date to the organisation start date for migrated repos
    owner = repo_full.split("/")[0] if "/" in repo_full else ""
    org_min = ORG_START_DATES.get(owner.lower())
    if org_min and first_date and first_date < org_min:
        first_date = org_min

    # For staleness checks: overwrite last_date with the latest commit by
    # anyone, so we can detect if the project as a whole is inactive.
    if not only_user:
        any_commits, _ = _gh_api_raw(
            f"/repos/{repo_full}/commits?per_page=1", token
        )
        if any_commits and isinstance(any_commits, list) and any_commits:
            cd = any_commits[0].get("commit", {}).get("committer", {}).get("date", "")
            if cd:
                last_date = cd[:10]

    return first_date, last_date


def determine_icon(repo: dict) -> str:
    """Determine the icon for a repo based on topics and language."""
    topics = [t.lower() for t in repo.get("topics", [])]
    language = (repo.get("language") or "").lower()
    name = repo.get("name", "").lower()

    # Check topics first
    for topic in topics:
        if topic in ICON_MAP:
            icon = ICON_MAP[topic]
            if icon is not None:
                return icon
            break

    # Check language
    if language in LANGUAGE_ICON:
        icon = LANGUAGE_ICON[language]
        if icon is not None:
            return icon

    # Check name keywords
    for keyword in ["paper", "thesis", "publication", "dissertation"]:
        if keyword in name:
            return "pub"
    for keyword in ["talk", "webinar", "presentation"]:
        if keyword in name:
            return "talk"
    for keyword in ["compiler", "language", "interpreter"]:
        if keyword in name:
            return "proj"

    # Default
    return ""


def determine_affiliation(repo: dict) -> str:
    """Determine the affiliation for a repo."""
    owner = repo.get("owner", {}).get("login", "")
    # Personal repos — use the owner name verbatim for orgs
    if owner.lower() in ("sk1y101", "skyecasolw"):
        return "Personal"
    return owner


def format_date_range(first: Optional[str], last: Optional[str]) -> str:
    """Format date range for the CV entry.

    If the last commit is older than STALENESS_DAYS, uses that date as end
    rather than "Present".
    """
    if not first:
        return ""

    if last:
        try:
            last_dt = date.fromisoformat(last[:10])
            days_since = (date.today() - last_dt).days
            is_active = days_since < STALENESS_DAYS
        except (ValueError, TypeError):
            is_active = False

        if is_active:
            return f"{first}--Present"

        if last != first:
            return f"{first}--{last}"

    # Single date or same-day
    return first


def _collect_addproject_args(text: str, start_idx: int) -> tuple[list[str], int]:
    """Collect 6 brace-delimited arguments from \addproject at start_idx.

    Returns (args, end_idx) where end_idx is position after closing brace of arg 6.
    Returns ([], start_idx) if parsing fails.
    """
    idx = start_idx + len("\\addproject{")  # consume opening { of arg 1
    args = []

    for arg_i in range(6):
        # Skip whitespace
        while idx < len(text) and text[idx] in " \n\r\t":
            idx += 1

        # For args 2-6, consume the opening {
        if arg_i > 0:
            if idx >= len(text) or text[idx] != "{":
                return [], start_idx
            idx += 1

        # Balance braces to find closing }
        depth = 0
        start = idx
        while idx < len(text):
            if text[idx] == "{":
                depth += 1
            elif text[idx] == "}":
                if depth == 0:
                    args.append(text[start:idx])
                    idx += 1
                    break
                depth -= 1
            idx += 1
        else:
            return [], start_idx  # ran out of text

    return args, idx


def extract_existing_urls(tex_path: Path) -> set[str]:
    """Extract all URLs from existing \addproject entries."""
    text = tex_path.read_text()
    urls = set()

    idx = 0
    while True:
        idx = text.find("\\addproject{", idx)
        if idx == -1:
            break

        # Skip if this is a commented line
        line_start = text.rfind("\n", 0, idx) + 1
        line_prefix = text[line_start:idx].strip()
        if line_prefix.startswith("%"):
            idx += 1
            continue

        args, end = _collect_addproject_args(text, idx)
        if len(args) >= 6:
            url = args[5].strip()
            if url:
                urls.add(url)
        idx += 1

    return urls


def generate_description_llm(repo: dict, token: str, model: str, endpoint: str) -> str:
    """Generate a CV-style description using an LLM."""
    name = repo.get("name", "")
    desc = repo.get("description") or ""
    topics = ", ".join(repo.get("topics", []))
    language = repo.get("language") or ""
    readme = repo.get("readme", "")

    prompt = f"""You are writing entries for a LaTeX CV. Write a 1-3 sentence project description matching this style:

{EXAMPLE_DESCRIPTIONS}

Write a description for this project:
- Name: {name}
- GitHub description: {desc}
- Topics: {topics}
- Language: {language}

{"- README excerpt: " + readme[:500] if readme else ""}

Rules:
- Write in present tense for ongoing projects, past tense for completed ones
- Focus on what the project DOES, not just what it IS
- Use technical language appropriate for a DevOps/Software Engineering CV
- Do NOT use first person ("I", "my")
- Keep it to 1-3 sentences
- Be specific about technologies and architecture where relevant
- Do not wrap in quotes
- Do not use em-dashes"""

    payload = {
        "messages": [
            {"role": "system", "content": "You are a technical writer for CVs. Write concise, informative project descriptions."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 200,
        "temperature": 0.7,
    }

    models = [model] + [m for m in FALLBACK_MODELS if m.lower() != model.lower()]
    text = _api_request(payload, token, models, endpoint)
    if text is not None:
        text = text.strip('"').strip("'")
        return text

    # Fallback: use the GitHub description directly
    if desc:
        return f"{name}: {desc}"
    return f"{name}. Written in {language}." if language else f"{name}."


def generate_description_template(repo: dict) -> str:
    """Fallback template-based description."""
    name = repo.get("name", "")
    desc = repo.get("description") or ""
    language = repo.get("language") or ""
    topics = repo.get("topics", [])

    parts = []
    if desc:
        parts.append(desc.rstrip("."))
    if language:
        parts.append(f"Built with {language}")
    if topics:
        topic_str = ", ".join(t for t in topics if t.lower() != language.lower())
        if topic_str:
            parts.append(f"Topics: {topic_str}")

    if parts:
        return ". ".join(parts) + "."
    return f"{''.join(w.capitalize() for w in name.replace('-', ' ').split())} project."


# Mapping from GitHub languages/topics to CV skill (category, name)
GITHUB_SKILL_MAP = {
    # Languages
    "python": ("Languages", "Python"),
    "go": ("Languages", "Go"),
    "rust": ("Languages", "C++"),  # close enough; C++ maps broadly
    "c++": ("Languages", "C++"),
    "c": ("Languages", "C++"),
    "typescript": ("Languages", "Javascript"),
    "javascript": ("Languages", "Javascript"),
    "java": ("Languages", "Groovy"),
    "groovy": ("Languages", "Groovy"),
    "shell": ("Languages", "Bash"),
    "bash": ("Languages", "Bash"),
    "html": ("Languages", "HTML/CSS"),
    "css": ("Languages", "HTML/CSS"),
    "dockerfile": ("Languages", "Bash"),
    "makefile": ("Languages", "Bash"),
    "kerboscript": ("Languages", "Kerboscript"),
    "latex": ("Languages", r"\LaTeX"),
    "markdown": ("Languages", "Markdown"),
    "sql": ("Languages", "SQL"),
    # DevOps & Cloud
    "terraform": ("DevOps & Cloud", "Terraform HCL"),
    "hcl": ("DevOps & Cloud", "Terraform HCL"),
    "packer": ("DevOps & Cloud", "Packer"),
    "ansible": ("DevOps & Cloud", "Ansible"),
    "maas": ("DevOps & Cloud", "MAAS"),
    "docker": ("DevOps & Cloud", "Docker"),
    "kubernetes": ("DevOps & Cloud", "Docker"),
    "k8s": ("DevOps & Cloud", "Docker"),
    "jenkins": ("DevOps & Cloud", "Jenkins / CI"),
    "ci/cd": ("DevOps & Cloud", "Jenkins / CI"),
    "ci": ("DevOps & Cloud", "Jenkins / CI"),
    "cd": ("DevOps & Cloud", "Jenkins / CI"),
    "github actions": ("DevOps & Cloud", "Jenkins / CI"),
    "api": ("DevOps & Cloud", "REST APIs"),
    "rest": ("DevOps & Cloud", "REST APIs"),
    "rest api": ("DevOps & Cloud", "REST APIs"),
    "cli": ("DevOps & Cloud", "CLI Development"),
    "aws": ("DevOps & Cloud", "AWS"),
    "amazon web services": ("DevOps & Cloud", "AWS"),
    "linux": ("DevOps & Cloud", "Linux"),
    "networking": ("DevOps & Cloud", "Networking"),
    "git": ("DevOps & Cloud", "Git"),
    "yaml": ("DevOps & Cloud", "YAML"),
    "yml": ("DevOps & Cloud", "YAML"),
    # Web & Data
    "machine learning": ("Web & Data", "TensorFlow / Keras"),
    "deep learning": ("Web & Data", "TensorFlow / Keras"),
    "tensorflow": ("Web & Data", "TensorFlow / Keras"),
    "keras": ("Web & Data", "TensorFlow / Keras"),
    "data science": ("Web & Data", "NumPy / SciPy"),
    "data": ("Web & Data", "NumPy / SciPy"),
    "numpy": ("Web & Data", "NumPy / SciPy"),
    "scipy": ("Web & Data", "NumPy / SciPy"),
    "pandas": ("Web & Data", "NumPy / SciPy"),
    "jupyter": ("Web & Data", "Jupyter"),
    "jupyter notebook": ("Web & Data", "Jupyter"),
    "opencv": ("Web & Data", "OpenCV"),
    "computer-vision": ("Web & Data", "OpenCV"),
    "cv": ("Web & Data", "OpenCV"),
    "selenium": ("Web & Data", "Selenium"),
    "web": ("Web & Data", "Web Development"),
    "react": ("Web & Data", "Web Development"),
    "vue": ("Web & Data", "Web Development"),
    "flask": ("Web & Data", "Web Development"),
    "django": ("Web & Data", "Web Development"),
    "fastapi": ("Web & Data", "Web Development"),
    "database": ("Web & Data", "Databases"),
    "postgresql": ("Web & Data", "Databases"),
    "mongodb": ("Web & Data", "Databases"),
    # Physics
    "physics": ("Physics", "Computational Modelling"),
    "astronomy": ("Physics", "Observational Astronomy"),
    "exoplanet": ("Physics", "Exoplanetary Physics"),
    "exoplanets": ("Physics", "Exoplanetary Physics"),
    "transit timing variation": ("Physics", "Transit Timing Analysis"),
    "ttv": ("Physics", "Transit Timing Analysis"),
    "gravitational wave": ("Physics", "Gravitational Wave Physics"),
    "ligo": ("Physics", "Gravitational Wave Physics"),
    "space": ("Physics", "Space & Spacecraft"),
    "rocket": ("Physics", "Space & Spacecraft"),
    "ksp": ("Physics", "Space & Spacecraft"),
    "kerbal": ("Physics", "Space & Spacecraft"),
    "cosmology": ("Physics", "Cosmology"),
    "signal processing": ("Physics", "Signal Processing"),
    "statistics": ("Physics", "Statistical Analysis"),
    "statistical analysis": ("Physics", "Statistical Analysis"),
    "modelling": ("Physics", "Computational Modelling"),
    "simulation": ("Physics", "Computational Modelling"),
}


def parse_skills(text: str) -> list[dict]:
    """Extract all \\skill{category}{name}{level} entries via brace balancing."""
    skills = []
    idx = 0
    while True:
        idx = text.find("\\skill{", idx)
        if idx == -1:
            break
        line_start = text.rfind("\n", 0, idx) + 1
        if text[line_start:idx].strip().startswith("%"):
            idx += 1
            continue
        args, end = _collect_addproject_args(text.replace("\\skill{", "\\addproject{", 1), idx)
        # _collect_addproject_args expects \addproject prefix; adapt
        idx2 = idx + len("\\skill{")
        args = []
        for arg_i in range(3):
            while idx2 < len(text) and text[idx2] in " \n\r\t":
                idx2 += 1
            if arg_i > 0:
                if idx2 >= len(text) or text[idx2] != "{":
                    break
                idx2 += 1
            depth = 0
            start = idx2
            while idx2 < len(text):
                if text[idx2] == "{":
                    depth += 1
                elif text[idx2] == "}":
                    if depth == 0:
                        args.append(text[start:idx2])
                        idx2 += 1
                        break
                    depth -= 1
                idx2 += 1
        if len(args) >= 3:
            full = text[idx:idx2]
            skills.append({"full": full, "category": args[0], "name": args[1], "level": args[2]})
        idx = idx2
    return skills


def extract_repo_skills(repo: dict) -> list[tuple[str, str]]:
    """Map a repo's language and topics to CV skill (category, name) pairs."""
    matched = []
    language = (repo.get("language") or "").lower()
    if language and language in GITHUB_SKILL_MAP:
        matched.append(GITHUB_SKILL_MAP[language])
    for topic in (t.lower() for t in repo.get("topics", [])):
        if topic in GITHUB_SKILL_MAP:
            matched.append(GITHUB_SKILL_MAP[topic])
    return matched


def evaluate_skills(new_repos_info: list[dict], current_skills: list[dict], llm_key: str, model: str, endpoint: str):
    """Ask the LLM to suggest skill adjustments AND new skills based on new repos.

    Returns (adjustments, new_skills):
      - adjustments: dict mapping skill name (lowercase) to new level (str)
      - new_skills: list of (category, name, level) tuples for entirely new skills
    """
    if not llm_key or not new_repos_info:
        return {}, []

    repos_text = "\n".join(
        f"- {r['name']}: {r.get('language') or 'N/A'} — {(', '.join(r.get('topics') or []))}\n  {(r.get('description') or 'No description')[:200]}"
        for r in new_repos_info
    )
    current_text = "\n".join(
        f"  {s['name']:<30} {s['category']:<18} Level {s['level']}"
        for s in current_skills
    )

    prompt = f"""You are evaluating skill levels for a LaTeX CV. Skill levels are 1 (Beginner) to 5 (Master).

New repositories have been added to the CV. Based on their languages, topics, and descriptions, do two things:

1. Suggest level ADJUSTMENTS for existing skills that are reflected in the new work.
2. Suggest entirely NEW skills that should be added (for languages/tools/domains the
   new repos demonstrate but are not yet listed).

Current skills (all of them):
{current_text}

New repositories added:
{repos_text}

Respond in this exact format. One line per change, no extra text:

For existing skill adjustments:
skill_name|new_level

For new skills to add:
+category|skill_name|new_level

Examples:
Python|5
Docker|4
+DevOps & Cloud|Kubernetes|2
+Languages|Rust|1

Only list changes. Return nothing if no adjustments or new skills needed."""

    payload = {
        "messages": [
            {"role": "system", "content": "You are a skill evaluator for CVs. Output only the requested format."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 400,
        "temperature": 0.3,
    }

    models = [model] + [m for m in FALLBACK_MODELS if m.lower() != model.lower()]
    text = _api_request(payload, llm_key, models, endpoint, title="CV-Skill-Eval")
    if text is None:
        return {}, []

    adjustments = {}
    new_skills = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|")
        if line.startswith("+"):
            # New skill: +category|name|level
            if len(parts) == 4:
                _, cat, name, level = parts
            elif len(parts) == 3:
                _, name, level = parts
                cat = "Languages"
            else:
                continue
            if level.isdigit() and 1 <= int(level) <= 5:
                new_skills.append((cat.strip(), name.strip(), level.strip()))
        else:
            # Adjustment: name|level
            if len(parts) >= 2:
                name, level = parts[0].strip(), parts[1].strip()
                if level.isdigit() and 1 <= int(level) <= 5:
                    adjustments[name.lower()] = level

    if adjustments or new_skills:
        log(f"Skill adjustments: {adjustments}  new skills: {(s[1] for s in new_skills)}")
    return adjustments, new_skills


def update_skills(text: str, adjustments: dict, new_skills: list) -> str:
    """Apply skill level adjustments and add new skills in the text."""
    # Apply adjustments to existing skills
    if adjustments:
        skills = parse_skills(text)
        for s in skills:
            key = s["name"].strip().lower()
            if key in adjustments and adjustments[key] != s["level"]:
                old = s["full"]
                new = old.replace("{" + s["level"] + "}", "{" + adjustments[key] + "}", 1)
                text = text.replace(old, new, 1)
                log(f"  Skill: {s['name']} level {s['level']} → {adjustments[key]}")

    # Insert new skills before "% Hobbies and Interests"
    if new_skills:
        new_lines = []
        for cat, name, level in new_skills:
            esc_name = _LATEX_ARG_PAT.sub(lambda m: _LATEX_ESC[m.group(0)], name)
            esc_cat = _LATEX_ARG_PAT.sub(lambda m: _LATEX_ESC[m.group(0)], cat)
            new_lines.append(f"\\skill{{{esc_cat}}}{{{esc_name}}}{{{level}}}")
            log(f"  New skill: {cat} / {name} (level {level})")
        insert = "\n" + "\n".join(new_lines) + "\n"
        hobby_marker = "% hobbies and interests"
        pos = text.find(hobby_marker)
        if pos != -1:
            text = text[:pos] + insert + text[pos:]

    return text


_LATEX_ARG_PAT = re.compile(r'[#$&%_^~]')
_LATEX_ESC_PAT = re.compile(r'[\\{}#$&%_^~\n\r]')
_LATEX_ESC = {
    "\\": "\\textbackslash{}", "{": "\\{", "}": "\\}",
    "$": "\\$", "&": "\\&", "%": "\\%",
    "_": "\\_", "#": "\\#",
    "^": "\\textasciicircum{}", "~": "\\textasciitilde{}",
    "\n": " ", "\r": " ",
}


def _escape_latex(text: str) -> str:
    """Escape LaTeX special chars and strip newlines."""
    text = _LATEX_ESC_PAT.sub(lambda m: _LATEX_ESC[m.group(0)], text)
    text = " ".join(text.split())
    return text


def generate_addproject(repo: dict, gh_token: str = "", llm_key: str = "", model: str = "", endpoint: str = "") -> str:
    """Generate a full \addproject entry for a repo."""
    name = repo.get("name", "")
    url = repo.get("html_url", "")
    icon = determine_icon(repo)
    affiliation = determine_affiliation(repo)

    # Get dates
    repo_full = repo.get("full_name", "")
    first_date, last_date = fetch_commit_dates(repo_full, gh_token)
    date_range = format_date_range(first_date, last_date)

    # Get description
    if llm_key:
        desc = generate_description_llm(repo, llm_key, model, endpoint)
    else:
        desc = generate_description_template(repo)

    # Escape LaTeX special characters and strip newlines from description
    desc = _escape_latex(desc)

    icon_str = "{" + icon + "}" if icon else "{}"
    affiliation_str = "{" + affiliation + "}"

    entry = (
        f"\\addproject{{{name}}}{icon_str}\n"
        f"{affiliation_str}{{{date_range}}}\n"
        f"{{{desc}}}{{{url}}}"
    )
    return entry


def scan_website() -> list[dict]:
    """Parse sk1y101.github.io/projects/ for projects not linked to GitHub repos.

    Returns a list of project dicts with keys: name, details, url, category.
    """
    class ProjectParser(html.parser.HTMLParser):
        def __init__(self):
            super().__init__()
            self.projects = []
            self.current_category = ""
            self.in_category = False
            self.in_grid_item = False
            self.in_card_title = False
            self.in_card_text = False
            self.in_link = False
            self.current_url = ""
            self.current_title = ""
            self.current_text = ""

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "h2" and "category" in attrs.get("class", ""):
                self.in_category = True
            elif tag == "div" and "grid-item" in attrs.get("class", ""):
                self.in_grid_item = True
                self.current_url = ""
                self.current_title = ""
                self.current_text = ""
            elif tag == "h2" and "card-title" in attrs.get("class", ""):
                self.in_card_title = True
            elif tag == "p" and "card-text" in attrs.get("class", ""):
                self.in_card_text = True
            elif tag == "a" and self.in_grid_item:
                self.in_link = True
                self.current_url = attrs.get("href", "")

        def handle_endtag(self, tag):
            if tag == "h2" and self.in_category:
                self.in_category = False
            elif tag == "div" and self.in_grid_item:
                self.in_grid_item = False
                if self.current_url and self.current_title:
                    self.projects.append({
                        "name": self.current_title.strip(),
                        "details": self.current_text.strip(),
                        "url": self.current_url.strip(),
                        "category": self.current_category,
                    })
            elif tag == "h2":
                self.in_card_title = False
            elif tag == "p":
                self.in_card_text = False
            elif tag == "a":
                self.in_link = False

        def handle_data(self, data):
            if self.in_category:
                self.current_category = data.strip()
            elif self.in_card_title:
                self.current_title += data
            elif self.in_card_text:
                self.current_text += data

    try:
        req = urllib.request.Request(
            WEBSITE_URL,
            headers={"User-Agent": "cv-sync/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_html = resp.read().decode("utf-8")

        parser = ProjectParser()
        parser.feed(raw_html)

        # Filter to only non-GitHub URLs (GitHub repos handled by repo scanner)
        results = []
        for p in parser.projects:
            url = p["url"]
            # Skip GitHub repos, absolute PDFs, and section-anchors
            if "github.com" in url or url.endswith(".pdf") or url.startswith("#"):
                continue
            # Resolve relative URLs
            if url.startswith("/"):
                url = "https://sk1y101.github.io" + url
            p["url"] = url
            results.append(p)

        return results
    except Exception as e:
        log(f"Website scan failed: {e}")
        return []


def check_staleness(text: str, token: str) -> str:
    """Update existing 'Present' entries that haven't been committed to in
    STALENESS_DAYS to use the last commit date as their end date."""
    projects = parse_existing_projects(text)
    changed = False

    for proj in projects:
        if proj.get("end") != "Present":
            continue
        url = proj.get("url", "")
        if not url:
            continue
        # Extract owner/repo from GitHub URL
        if "github.com" not in url:
            continue
        parts = url.rstrip("/").split("/")
        if len(parts) < 2:
            continue
        # Get last 2 parts: owner/repo
        repo_full = "/".join(parts[-2:])
        # Remove .git suffix if present
        if repo_full.endswith(".git"):
            repo_full = repo_full[:-4]

        _, last_date = fetch_commit_dates(repo_full, token, only_user=False)
        if not last_date:
            continue

        try:
            last_dt = date.fromisoformat(last_date[:10])
            days_since = (date.today() - last_dt).days
        except (ValueError, TypeError):
            continue

        if days_since >= STALENESS_DAYS:
            date_start = proj["start"] if proj["start"] else proj["date"].split("--")[0]
            new_date = f"{date_start}--{last_date[:10]}"
            entry_start = text.find(proj["full"])
            date_pos = text.find("{" + proj["date"] + "}", entry_start)
            if date_pos != -1:
                old = text[date_pos : date_pos + len(proj["date"]) + 2]
                new = "{" + new_date + "}"
                text = text.replace(old, new, 1)
                changed = True
                log(f"  Stale: {proj['name']}- set end to {last_date[:10]}")

    if changed:
        log("Updated stale project dates")

    return text


def parse_existing_projects(text: str) -> list[dict]:
    """Parse all existing \addproject entries from details.tex text."""
    projects = []

    idx = 0
    while True:
        idx = text.find("\\addproject{", idx)
        if idx == -1:
            break

        # Skip if this is a commented line
        line_start = text.rfind("\n", 0, idx) + 1
        line_prefix = text[line_start:idx].strip()
        if line_prefix.startswith("%"):
            idx += 1
            continue

        entry_start = idx
        args, end = _collect_addproject_args(text, idx)
        if len(args) >= 6:
            project = {
                "full": text[entry_start:end],
                "name": args[0],
                "icon": args[1],
                "affiliation": args[2],
                "date": args[3],
                "details": args[4],
                "url": args[5],
                "start": "",
                "end": "",
            }
            date_str = args[3]
            if "--" in date_str:
                start_d, end_d = date_str.split("--", 1)
                project["start"] = start_d
                project["end"] = end_d
            else:
                project["start"] = date_str
                project["end"] = date_str
            projects.append(project)
        idx += 1

    return projects


def find_insert_position(projects: list[dict], new_entry: dict) -> int:
    """Find where to insert a new project entry to maintain sort order.

    Order: ongoing (Present end) by start desc, then completed by end desc.
    """
    # Ongoing sort by start DESC, completed by end DESC
    ongoing = sorted(
        [p for p in projects + [new_entry] if p["end"] == "Present" or p["end"] == ""],
        key=lambda p: p["start"] or "0000-00",
        reverse=True,
    )
    completed = sorted(
        [p for p in projects + [new_entry] if p["end"] and p["end"] != "Present"],
        key=lambda p: p["end"] or "0000-00",
        reverse=True,
    )
    sorted_projects = ongoing + completed

    # Find position of new entry in sorted list
    idx = sorted_projects.index(new_entry)
    return idx, sorted_projects


def parse_single_addproject(entry_str: str) -> dict | None:
    """Parse a single \addproject entry string into a dict using brace balancing."""
    idx = entry_str.find("\\addproject{")
    if idx == -1:
        return None
    args, _ = _collect_addproject_args(entry_str, idx)
    if len(args) < 6:
        return None
    project = {
        "full": entry_str,
        "name": args[0],
        "icon": args[1],
        "affiliation": args[2],
        "date": args[3],
        "details": args[4],
        "url": args[5],
        "start": "",
        "end": "",
    }
    date_str = args[3]
    if "--" in date_str:
        project["start"], project["end"] = date_str.split("--", 1)
    else:
        project["start"] = date_str
        project["end"] = date_str
    return project


def update_details_tex(new_entries: list[str]) -> bool:
    """Insert new \addproject entries into details.tex in correct positions."""
    text = DETAILS_TEX.read_text()
    existing = parse_existing_projects(text)
    existing_urls = set(p["url"] for p in existing)
    changed = False

    for entry_str in new_entries:
        new_project = parse_single_addproject(entry_str)
        if not new_project:
            continue
        url = new_project["url"]
        if url in existing_urls:
            continue

        existing.append(new_project)
        existing_urls.add(url)

        # Find the right position
        idx, sorted_projects = find_insert_position(existing, new_project)

        # Build the new projects section
        ongoing = [p for p in sorted_projects if p.get("end") == "Present" or p.get("end") == ""]
        completed = [p for p in sorted_projects if p.get("end") and p.get("end") != "Present"]

        new_section = "% Projects and Publications\n\n"
        new_section += "% \\addproject{name}{icon}{affiliation}{date}{details}{link}\n"
        new_section += "% Ongoing entries, sorted by start date descending\n"
        for p in ongoing:
            new_section += p.get("full", "") + "\n\n"
        new_section += "% Completed, sorted by end date descending\n"
        for p in completed:
            new_section += p.get("full", "") + "\n\n"

        # Replace the projects section in the file
        # Find the boundaries: after "% Projects and Publications" comment
        # and before "% hobbies and interests"
        start_marker = "% Projects and Publications"
        end_marker = "% hobbies and interests"

        start_idx = text.find(start_marker)
        end_idx = text.find(end_marker)
        if start_idx != -1 and end_idx != -1:
            before = text[:start_idx]
            after = text[end_idx:]
            text = before + new_section.rstrip() + "\n\n" + after
            changed = True
            log(f"Added new project: {new_project['name']} ({url})")
        else:
            log("Could not find project section boundaries in details.tex")
            return False

    if changed:
        DETAILS_TEX.write_text(text)
        log("Updated details.tex")

    return changed


def run_tex2json():
    """Run tex2json.py to regenerate resume.json."""
    result = subprocess.run(
        [sys.executable, str(TEX2JSON)],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log(f"tex2json.py failed: {result.stderr}")
        return False
    log("Regenerated resume.json")
    return True


def main():
    dry_run = "--dry-run" in sys.argv

    gh_token = os.environ.get("GITHUB_TOKEN") or ""
    llm_key = os.environ.get("LLM_API_KEY") or gh_token
    llm_model = os.environ.get("LLM_MODEL", "deepseek/deepseek-v4-flash:free")
    llm_endpoint = os.environ.get("LLM_ENDPOINT", "https://openrouter.ai/api/v1")

    if not llm_key:
        log("No LLM_API_KEY or GITHUB_TOKEN set. Will use template descriptions.")

    # Step 1: Check existing entries for staleness
    if gh_token:
        log("Checking existing entries for staleness (6+ months)...")
        text = DETAILS_TEX.read_text()
        updated_text = check_staleness(text, gh_token)
        if updated_text != text:
            if dry_run:
                log("Would update stale project dates.")
            else:
                DETAILS_TEX.write_text(updated_text)
                log("Updated stale project dates.")
    else:
        log("No GITHUB_TOKEN- skipping staleness check.")

    # Step 2: Scan website for non-GitHub projects
    log("Scanning website for projects...")
    website_projects = scan_website()
    log(f"Found {len(website_projects)} website-only project candidates")

    # Fetch existing entries (both URLs and names for dedup)
    existing_urls = extract_existing_urls(DETAILS_TEX)
    existing_names = set()
    for p in parse_existing_projects(DETAILS_TEX.read_text()):
        existing_names.add(p["name"].strip().lower())
    log(f"Found {len(existing_urls)} existing project entries")

    # Step 3: Generate entries from website (non-GitHub projects)
    new_entries = []
    would_add = 0
    for wp in website_projects:
        if wp["url"] in existing_urls:
            continue
        # Skip if same name exists (e.g., MAAS already in CV via GitHub URL)
        if wp["name"].strip().lower() in existing_names:
            continue
        log(f"  New website project: {wp['name']} ({wp['url']})")
        would_add += 1
        if dry_run:
            print(f"    Would add: {wp['name']} ({wp['url']})")
            continue

        # Escape LaTeX special chars and strip newlines from description
        desc = _escape_latex(wp["details"])

        today = date.today().isoformat()[:10]
        icon = "{}"
        affiliation = "{" + wp["category"] + "}"

        # Floor work-category projects to the earliest organisation start date
        # (handles projects like MAAS that predate their GH migration).
        start = today
        if wp.get("category", "").lower() in ("work", "employment"):
            work_floors = [d for d in ORG_START_DATES.values() if d and d < start]
            if work_floors:
                start = min(work_floors)

        date_range = f"{start}--Present"
        entry = (
            f"\\addproject{{{wp['name']}}}{icon}\n"
            f"{affiliation}{{{date_range}}}\n"
            f"{{{desc}}}{{{wp['url']}}}"
        )
        new_entries.append(entry)
        log(f"    Generated entry for {wp['name']}")

    # Step 4: Scan GitHub repos
    new_repos_info = []  # for skill evaluation
    replacements = {}  # old_full_text → new_full_text

    # Step 4a: Scan contribution orgs first.  These are the "source of truth"
    # for any repo the user has touched — forks of these will be skipped.
    for org in CONTRIBUTION_ORGS:
        log(f"Fetching contributed repos for {org}...")
        repos = fetch_user_contributed_repos(org, GITHUB_USERNAME, gh_token)

        for repo in repos:
            url = repo.get("html_url", "")
            if url in existing_urls:
                continue

            name = repo.get("name", "").strip().lower()

            if name and name in existing_names:
                # This repo exists under a different URL (likely a fork).
                # Upgrade the existing entry to use the upstream.
                log(f"  Upgrading {repo['name']} to upstream ({url})")
                would_add += 1
                new_repos_info.append(repo)
                if dry_run:
                    print(f"    Would upgrade: {repo['name']} → {url}")
                    continue
                entry = generate_addproject(repo, gh_token=gh_token, llm_key=llm_key, model=llm_model, endpoint=llm_endpoint)
                for p in parse_existing_projects(text):
                    if p["name"].strip().lower() == name:
                        replacements[p["full"]] = entry
                        break
                continue

            # Skip archived repos
            if repo.get("archived"):
                continue

            log(f"  New repo: {repo['name']} ({org})")
            would_add += 1
            new_repos_info.append(repo)
            if dry_run:
                print(f"    Would add: {repo['name']} ({url})")
                continue

            entry = generate_addproject(repo, gh_token=gh_token, llm_key=llm_key, model=llm_model, endpoint=llm_endpoint)
            new_entries.append(entry)
            log(f"    Generated entry for {repo['name']}")

    # Step 4b: Scan personal repos.  Skip forks of repos already covered by
    # contribution orgs; keep other forks (they're from external projects).
    for owner in OWNERS:
        log(f"Fetching repos for {owner}...")
        repos = fetch_all_repos(owner, gh_token)
        log(f"  Found {len(repos)} repos")

        for repo in repos:
            url = repo.get("html_url", "")
            if url in existing_urls:
                continue

            name = repo.get("name", "").strip().lower()

            # Skip if a project with this name is already tracked (from a
            # contribution org or manually added). The upstream is the
            # source of truth; the fork/personal copy is redundant.
            if name and name in existing_names:
                log(f"  Skipped {repo['name']} (already exists in CV)")
                continue

            # Keep forks of external orgs (not covered by contribution
            # orgs) — those are unique contributions worth listing.
            if repo.get("fork"):
                log(f"  New fork: {repo['name']}")
            else:
                log(f"  New repo: {repo['name']}")

            # Skip archived repos
            if repo.get("archived"):
                continue

            would_add += 1
            new_repos_info.append(repo)
            if dry_run:
                print(f"    Would add: {repo['name']} ({url})")
                continue

            # Generate entry
            entry = generate_addproject(repo, gh_token=gh_token, llm_key=llm_key, model=llm_model, endpoint=llm_endpoint)
            new_entries.append(entry)
            log(f"    Generated entry for {repo['name']}")

    if dry_run:
        log(f"Dry run complete. Would add {would_add} new entries.")
        return

    if not new_entries and not replacements:
        log("No new repos found.")
        return

    # Apply replacements (upgrade fork entries to upstream)
    if replacements:
        text = DETAILS_TEX.read_text()
        for old_full, new_full in replacements.items():
            if old_full in text:
                text = text.replace(old_full, new_full, 1)
                log("  Replaced fork entry with upstream")
        DETAILS_TEX.write_text(text)

    # Update details.tex
    updated = False
    if new_entries:
        updated = update_details_tex(new_entries)
    if replacements:
        updated = True
    if updated:
        run_tex2json()
        log(f"Synchronisation complete. Added {len(new_entries)} new entries, "
            f"upgraded {len(replacements)} forks to upstream.")

    # Step 5: Re-evaluate skill levels based on new repos
    if new_repos_info and llm_key:
        log("Evaluating skill levels from new repos...")
        text = DETAILS_TEX.read_text()
        current_skills = parse_skills(text)
        adjustments, new_skills = evaluate_skills(new_repos_info, current_skills, llm_key, llm_model, llm_endpoint)
        if adjustments or new_skills:
            text = update_skills(text, adjustments, new_skills)
            DETAILS_TEX.write_text(text)
            run_tex2json()
    else:
        log("Skipping skill evaluation (no new repos or no LLM key).")


if __name__ == "__main__":
    main()
