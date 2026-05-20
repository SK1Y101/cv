#!/usr/bin/env python3
"""
Daily sync script: fetches public repos from configured GitHub owners and
parses sk1y101.github.io/projects/ for new entries, detects ones not yet in
details.tex, generates descriptions via LLM, and inserts new \addproject
entries. Also marks stale projects (6+ months without commits) as completed.

Usage:
    python3 scripts/sync_repos.py [--dry-run]

Environment:
    GITHUB_TOKEN       — GitHub API token (required for API calls)
    LLM_API_KEY        — LLM API key (defaults to GITHUB_TOKEN for GitHub Models)
    LLM_MODEL          — Model name (default: deepseek/deepseek-v4)
    LLM_ENDPOINT       — API endpoint (default: https://openrouter.ai/api/v1)
"""

import os
import sys
import json
import subprocess
import urllib.request
import urllib.parse
import html.parser
from datetime import date
from pathlib import Path
from typing import Optional

REPO_DIR = Path(__file__).resolve().parent.parent
DETAILS_TEX = REPO_DIR / "details.tex"
TEX2JSON = REPO_DIR / "tex2json.py"

STALENESS_DAYS = 180  # 6 months
WEBSITE_URL = "https://sk1y101.github.io/projects/"

# GitHub owners to scan for new repos
OWNERS = [
    "SK1Y101",
    "SkiylianSoftware",
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


def gh_api(path: str, token: str) -> dict | list:
    url = f"https://api.github.com{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "cv-sync/1.0")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        log(f"GitHub API error {e.code} for {path}: {e.read().decode()[:200]}")
        return []


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


def fetch_first_commit(repo_full: str, token: str) -> Optional[str]:
    """Get the date of the very first commit in a repo."""
    # First try: get the first commit via the list API
    data = gh_api(f"/repos/{repo_full}/commits?per_page=1&sha=", token)
    if data and isinstance(data, list) and len(data) > 0:
        # GitHub API returns commits from the default branch
        # Get first commit by walking to the root - use the SHA ordering
        # Actually, the first commit is the LAST one in the full list
        data = gh_api(f"/repos/{repo_full}/commits?per_page=1&page=1", token)
        if data and isinstance(data, list) and len(data) > 0:
            # Get the last page by checking Link header
            pass

    # Simple approach: get commits sorted by date, take the oldest
    # But this doesn't work well. Let's get the repo creation date instead.
    repo_data = gh_api(f"/repos/{repo_full}", token)
    if repo_data and isinstance(repo_data, dict):
        created = repo_data.get("created_at", "")
        if created:
            return created[:10]  # YYYY-MM-DD

    return None


def fetch_commit_dates(repo_full: str, token: str) -> tuple[Optional[str], Optional[str]]:
    """Get first and latest commit dates for a repo (by SK1Y101 if canonical org)."""
    first_date = None
    last_date = None

    # Get repo creation date as fallback for first commit
    repo_data = gh_api(f"/repos/{repo_full}", token)
    if repo_data and isinstance(repo_data, dict):
        created = repo_data.get("created_at", "")
        if created:
            first_date = created[:10]

    # Get latest commit on default branch
    commits = gh_api(f"/repos/{repo_full}/commits?per_page=1", token)
    if commits and isinstance(commits, list) and len(commits) > 0:
        commit_date = commits[0].get("commit", {}).get("committer", {}).get("date", "")
        if commit_date:
            last_date = commit_date[:10]

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
    if owner.lower() == "canonical":
        return "Canonical"
    if owner == "SkiylianSoftware":
        return "SkiylianSoftware"
    return "Personal"


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
- Do not wrap in quotes"""

    # Try LLM API via OpenRouter-compatible endpoint
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "cv-sync/1.0",
        }
        # OpenRouter-specific headers
        if "openrouter" in endpoint:
            headers["HTTP-Referer"] = "https://github.com/SK1Y101/cv"
            headers["X-Title"] = "CV-Sync"
        req = urllib.request.Request(
            f"{endpoint}/chat/completions",
            data=json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a technical writer for CVs. Write concise, informative project descriptions."},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 200,
                "temperature": 0.7,
            }).encode(),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            text = result["choices"][0]["message"]["content"].strip()
            # Remove quotes if LLM wrapped it
            text = text.strip('"').strip("'")
            return text
    except Exception as e:
        log(f"LLM call failed: {e}")
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

    # Escape LaTeX special characters in description
    desc = desc.replace("&", "\\&")
    desc = desc.replace("%", "\\%")
    desc = desc.replace("_", "\\_")
    desc = desc.replace("#", "\\#")

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
        repo_full = repo_full.rstrip(".git")

        _, last_date = fetch_commit_dates(repo_full, token)
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
                log(f"  Stale: {proj['name']} — set end to {last_date[:10]}")

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

    def sort_key(p):
        is_ongoing = p["end"] == "Present" or p["end"] == ""
        # For sorting: ongoing first (0 < 1), then by end desc, then start desc
        return (
            0 if is_ongoing else 1,
            # For 'Present', use a very large date
            "9999-99" if is_ongoing else (p["end"] or "0000-00"),
            p["start"] or "0000-00",
        )

    # Add the new entry to the list, sort, find its position
    all_projects = projects + [new_entry]
    all_projects.sort(key=sort_key, reverse=True)
    # Ongoing sort by start DESC, completed by end DESC
    ongoing = [p for p in all_projects if p["end"] == "Present" or p["end"] == ""]
    completed = [p for p in all_projects if p["end"] and p["end"] != "Present"]
    ongoing.sort(key=lambda p: p["start"] or "0000-00", reverse=True)
    completed.sort(key=lambda p: p["end"] or "0000-00", reverse=True)
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
    llm_model = os.environ.get("LLM_MODEL", "deepseek/deepseek-v4")
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
        log("No GITHUB_TOKEN — skipping staleness check.")

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
    for wp in website_projects:
        if wp["url"] in existing_urls:
            continue
        # Skip if same name exists (e.g., MAAS already in CV via GitHub URL)
        if wp["name"].strip().lower() in existing_names:
            continue
        log(f"  New website project: {wp['name']} ({wp['url']})")
        if dry_run:
            print(f"    Would add: {wp['name']} ({wp['url']})")
            continue

        # Escape LaTeX special chars in description
        desc = wp["details"]
        desc = desc.replace("&", "\\&")
        desc = desc.replace("%", "\\%")
        desc = desc.replace("_", "\\_")
        desc = desc.replace("#", "\\#")

        today = date.today().isoformat()[:10]
        icon = "{}"
        affiliation = "{" + wp["category"] + "}"
        date_range = f"{today}--Present"
        entry = (
            f"\\addproject{{{wp['name']}}}{icon}\n"
            f"{affiliation}{{{date_range}}}\n"
            f"{{{desc}}}{{{wp['url']}}}"
        )
        new_entries.append(entry)
        log(f"    Generated entry for {wp['name']}")

    # Step 4: Scan GitHub repos
    for owner in OWNERS:
        log(f"Fetching repos for {owner}...")
        repos = fetch_all_repos(owner, gh_token)
        log(f"  Found {len(repos)} repos")

        for repo in repos:
            url = repo.get("html_url", "")
            if url in existing_urls:
                continue

            # Skip forks unless they have significant changes
            if repo.get("fork"):
                continue

            # Skip archived repos
            if repo.get("archived"):
                continue

            log(f"  New repo: {repo['name']}")
            if dry_run:
                print(f"    Would add: {repo['name']} ({url})")
                continue

            # Generate entry
            entry = generate_addproject(repo, gh_token=gh_token, llm_key=llm_key, model=llm_model, endpoint=llm_endpoint)
            new_entries.append(entry)
            log(f"    Generated entry for {repo['name']}")

    if dry_run:
        log(f"Dry run complete. Would add {len(new_entries)} new entries.")
        return

    if not new_entries:
        log("No new repos found.")
        return

    # Update details.tex
    updated = update_details_tex(new_entries)
    if updated:
        run_tex2json()
        log(f"Sync complete. Added {len(new_entries)} new projects.")
    else:
        log("No changes made.")


if __name__ == "__main__":
    main()
