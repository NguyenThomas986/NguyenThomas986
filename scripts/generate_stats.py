import json
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone


USERNAME = os.environ.get("GITHUB_USERNAME", "NguyenThomas986")
TOKEN = os.environ.get("GITHUB_TOKEN")

API_URL = "https://api.github.com"
PROFILE_REPO = f"{USERNAME}/{USERNAME}"

START_MARKER = "<!-- START_GITHUB_STATS -->"
END_MARKER = "<!-- END_GITHUB_STATS -->"

LANG_START_MARKER = "<!-- START_LANGUAGE_STATS -->"
LANG_END_MARKER = "<!-- END_LANGUAGE_STATS -->"


def github_request(endpoint, params=None):
    """Make a request to the GitHub API."""

    url = f"{API_URL}{endpoint}"

    if params:
        url += "?" + urllib.parse.urlencode(params)

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-profile-stats",
    }

    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as error:
        print(f"GitHub API error: {error.code} {error.reason}")
        return None


def get_repositories():
    """Get public repositories owned by the user."""

    repositories = []
    page = 1

    while True:
        data = github_request(
            f"/users/{USERNAME}/repos",
            {
                "per_page": 100,
                "page": page,
                "type": "owner",
                "sort": "updated",
            },
        )

        if not data:
            break

        repositories.extend(data)

        if len(data) < 100:
            break

        page += 1

    # Exclude profile repository and forks.
    repositories = [
        repo
        for repo in repositories
        if repo["full_name"].lower() != PROFILE_REPO.lower()
        and not repo.get("fork", False)
    ]

    return repositories


def get_commits(repo_name):
    """Get commits authored by the user in a repository."""

    commits = []
    page = 1

    while True:
        data = github_request(
            f"/repos/{repo_name}/commits",
            {
                "author": USERNAME,
                "per_page": 100,
                "page": page,
            },
        )

        if not data:
            break

        commits.extend(data)

        if len(data) < 100:
            break

        page += 1

    return commits


def collect_commit_stats(repositories):
    """Collect commit counts by hour and weekday."""

    hourly = Counter()
    weekdays = Counter()

    total_commits = 0

    for repo in repositories:
        repo_name = repo["full_name"]

        print(f"Checking commits in {repo_name}...")

        commits = get_commits(repo_name)

        for commit in commits:
            commit_info = commit.get("commit", {})
            author = commit_info.get("author", {})
            timestamp = author.get("date")

            if not timestamp:
                continue

            try:
                dt = datetime.fromisoformat(
                    timestamp.replace("Z", "+00:00")
                )
            except ValueError:
                continue

            hourly[dt.hour] += 1
            weekdays[dt.weekday()] += 1
            total_commits += 1

    return hourly, weekdays, total_commits


def progress_bar(value, maximum, width=24):
    """Create a text progress bar."""

    if maximum <= 0:
        filled = 0
    else:
        filled = round((value / maximum) * width)

    return "█" * filled + "░" * (width - filled)


def percentage(value, total):
    """Calculate percentage."""

    if total == 0:
        return 0.0

    return value / total * 100


def build_time_stats(hourly, total):
    """Build Morning / Daytime / Evening / Night statistics."""

    periods = {
        "🌞 Morning": range(5, 12),
        "🌆 Daytime": range(12, 17),
        "🌃 Evening": range(17, 22),
        "🌙 Night": list(range(22, 24)) + list(range(0, 5)),
    }

    period_counts = {}

    for name, hours in periods.items():
        period_counts[name] = sum(hourly[h] for h in hours)

    maximum = max(period_counts.values(), default=1)

    lines = [
        "**I'm an Early 🐤**",
        "",
        "<pre>",
    ]

    for name, count in period_counts.items():
        pct = percentage(count, total)
        bar = progress_bar(count, maximum)

        lines.append(
            f"{name:<16}"
            f"{count:>5} commits   "
            f"{bar} "
            f"{pct:05.2f} %"
        )

    lines.append("</pre>")

    return "\n".join(lines)


def build_weekday_stats(weekdays, total):
    """Build Monday-Sunday statistics."""

    names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    most_productive = max(
        weekdays,
        key=weekdays.get,
        default=0,
    )

    maximum = max(weekdays.values(), default=1)

    lines = [
        "",
        f"**📅 I'm Most Productive on {names[most_productive]}**",
        "",
        "<pre>",
    ]

    for index, name in enumerate(names):
        count = weekdays[index]
        pct = percentage(count, total)
        bar = progress_bar(count, maximum)

        lines.append(
            f"{name:<12}"
            f"{count:>5} commits   "
            f"{bar} "
            f"{pct:05.2f} %"
        )

    lines.append("</pre>")

    return "\n".join(lines)


def get_languages(repositories):
    """Aggregate GitHub language byte counts across repositories."""

    language_totals = Counter()

    for repo in repositories:
        repo_name = repo["full_name"]

        print(f"Checking languages in {repo_name}...")

        data = github_request(
            f"/repos/{repo_name}/languages"
        )

        if not data:
            continue

        for language, bytes_count in data.items():
            language_totals[language] += bytes_count

    return language_totals


def build_language_stats(languages):
    """Build most-used language section."""

    if not languages:
        return "No language data available."

    total_bytes = sum(languages.values())

    most_common = languages.most_common(8)

    maximum = most_common[0][1]

    lines = ["<pre>"]

    for language, byte_count in most_common:
        pct = percentage(byte_count, total_bytes)

        bar = progress_bar(
            byte_count,
            maximum,
            width=20,
        )

        lines.append(
            f"{language:<15}"
            f"{bar} "
            f"{pct:05.2f} %"
        )

    lines.append("</pre>")

    return "\n".join(lines)


def update_section(
    readme,
    start_marker,
    end_marker,
    content,
):
    """Replace content between README markers."""

    pattern = (
        re.escape(start_marker)
        + r".*?"
        + re.escape(end_marker)
    )

    replacement = (
        f"{start_marker}\n"
        f"{content}\n"
        f"{end_marker}"
    )

    updated, count = re.subn(
        pattern,
        replacement,
        readme,
        flags=re.DOTALL,
    )

    if count == 0:
        print(
            f"Warning: markers not found: "
            f"{start_marker}"
        )
        return readme

    return updated


def main():
    print(
        f"Generating GitHub statistics "
        f"for {USERNAME}"
    )

    repositories = get_repositories()

    print(
        f"Found {len(repositories)} repositories."
    )

    if not repositories:
        print("No repositories found.")
        return

    # Commit statistics.
    hourly, weekdays, total_commits = (
        collect_commit_stats(repositories)
    )

    print(
        f"Found {total_commits} commits."
    )

    time_stats = build_time_stats(
        hourly,
        total_commits,
    )

    weekday_stats = build_weekday_stats(
        weekdays,
        total_commits,
    )

    updated = datetime.now(
        timezone.utc
    ).strftime(
        "%d/%m/%Y %H:%M:%S UTC"
    )

    commit_stats = (
        time_stats
        + "\n"
        + weekday_stats
        + "\n\n"
        + f"Last Updated on {updated}"
    )

    # Language statistics.
    languages = get_languages(repositories)

    language_stats = build_language_stats(
        languages
    )

    # Read README.
    with open(
        "README.md",
        "r",
        encoding="utf-8",
    ) as file:
        readme = file.read()

    # Update GitHub activity.
    readme = update_section(
        readme,
        START_MARKER,
        END_MARKER,
        commit_stats,
    )

    # Update language statistics.
    readme = update_section(
        readme,
        LANG_START_MARKER,
        LANG_END_MARKER,
        language_stats,
    )

    # Write README.
    with open(
        "README.md",
        "w",
        encoding="utf-8",
    ) as file:
        file.write(readme)

    print(
        "README.md updated successfully."
    )


if __name__ == "__main__":
    main()