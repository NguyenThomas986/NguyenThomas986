import json
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone


USERNAME = os.environ.get(
    "GITHUB_USERNAME",
    "NguyenThomas986",
)

TOKEN = os.environ.get("GITHUB_TOKEN")

API_URL = "https://api.github.com"

PROFILE_REPO = f"{USERNAME}/{USERNAME}"

START_MARKER = "<!-- START_GITHUB_STATS -->"
END_MARKER = "<!-- END_GITHUB_STATS -->"


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

    request = urllib.request.Request(
        url,
        headers=headers,
    )

    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as error:
        print(
            f"GitHub API error: "
            f"{error.code} {error.reason}"
        )
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
        if (
            repo["full_name"].lower()
            != PROFILE_REPO.lower()
            and not repo.get("fork", False)
        )
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

        print(
            f"Checking commits in {repo_name}..."
        )

        commits = get_commits(repo_name)

        for commit in commits:

            commit_info = commit.get(
                "commit",
                {},
            )

            author = commit_info.get(
                "author",
                {},
            )

            timestamp = author.get("date")

            if not timestamp:
                continue

            try:
                dt = datetime.fromisoformat(
                    timestamp.replace(
                        "Z",
                        "+00:00",
                    )
                )

            except ValueError:
                continue

            hourly[dt.hour] += 1
            weekdays[dt.weekday()] += 1

            total_commits += 1

    return (
        hourly,
        weekdays,
        total_commits,
    )


def progress_bar(value, maximum, width=24):
    """
    Create a text progress bar.

    The bar is scaled relative to the maximum
    value in that particular category.
    """

    if maximum <= 0:
        filled = 0
    else:
        filled = round(
            (value / maximum) * width
        )

    return (
        "█" * filled
        + "░" * (width - filled)
    )


def percentage(value, total):
    """Calculate percentage."""

    if total == 0:
        return 0.0

    return value / total * 100


def get_languages(repositories):
    """Aggregate GitHub language byte counts across repositories."""

    language_totals = Counter()

    for repo in repositories:

        repo_name = repo["full_name"]

        print(
            f"Checking languages in {repo_name}..."
        )

        data = github_request(
            f"/repos/{repo_name}/languages"
        )

        if not data:
            continue

        for language, bytes_count in data.items():

            language_totals[language] += bytes_count

    return language_totals


def build_language_stats(languages):
    """
    Build most-used language statistics.

    Bars are scaled relative to the most-used language.
    Percentages are based on total language bytes.
    """

    if not languages:
        return "No language data available."

    total_bytes = sum(
        languages.values()
    )

    most_common = languages.most_common(8)

    # IMPORTANT:
    # Language bars use the largest language
    # as the maximum, not total bytes.
    maximum = most_common[0][1]

    lines = [
        "**Most Used Languages**",
        "",
        "<pre>",
    ]

    for language, byte_count in most_common:

        pct = percentage(
            byte_count,
            total_bytes,
        )

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

    return "\n".join(lines).rstrip()


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
            "Warning: markers not found: "
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

    # --------------------------------------------------
    # Commit statistics
    # --------------------------------------------------

    hourly, weekdays, total_commits = (
        collect_commit_stats(
            repositories
        )
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

    # --------------------------------------------------
    # Language statistics
    # --------------------------------------------------

    languages = get_languages(
        repositories
    )

    language_stats = build_language_stats(
        languages
    )

    # --------------------------------------------------
    # Timestamp
    # --------------------------------------------------

    updated = datetime.now(
        timezone.utc
    ).strftime(
        "%d/%m/%Y %H:%M:%S UTC"
    )

    timestamp = (
        '<div align="center">'
        "<sub>"
        f"Last Updated on {updated}"
        "</sub>"
        "</div>"
    )

    # --------------------------------------------------
    # Build Dev Metrics section
    # --------------------------------------------------

    github_stats = (
        time_stats
        + "\n\n"
        + weekday_stats
        + "\n\n"
        + language_stats
        + "\n\n"
        + timestamp
    )

    # --------------------------------------------------
    # Read README
    # --------------------------------------------------

    with open(
        "README.md",
        "r",
        encoding="utf-8",
    ) as file:

        readme = file.read()

    # --------------------------------------------------
    # Update Dev Metrics section
    # --------------------------------------------------

    readme = update_section(
        readme,
        START_MARKER,
        END_MARKER,
        github_stats,
    )

    # --------------------------------------------------
    # Write README
    # --------------------------------------------------

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