#!/usr/bin/env python3
"""lc: a small CLI for a daily interview-practice log.

  python lc.py today                  re-solves due, unlogged solutions, next problems
  python lc.py next [-n 5] [-p graphs]
  python lc.py log two-sum -m 18 -H 0 -c 4 --note "store complement -> index while scanning"
  python lc.py log rate-limiter --track design -m 60 -c 3 --note "..."
  python lc.py stats                  rebuild the README stats block
  python lc.py check                  validate the data files (CI runs this)
  python lc.py doctor [--online]      check setup; --online verifies roadmap.csv against LeetCode

Standard library only (Python 3.9+). LeetSync pushes accepted solutions into solutions/;
this tool never writes code there, only approach.md notes next to it.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Days until the next from-scratch re-solve, indexed by "box". A clean, confident solve moves a
# problem up a box, a hint or low confidence moves it down, and seeing the solution resets it.
LADDER = [1, 3, 7, 14, 30, 60, 120]

# Tracks other than "algo" are practice sessions run from a prompt in prompts/.
TRACKS = {
    "algo": "",
    "design": "prompts/code-design.md",
    "debug": "prompts/bug-squash.md",
    "integration": "prompts/integration.md",
    "ai": "prompts/ai-assisted.md",
    "mock": "prompts/mock-interview.md",
}
TRACK_NAMES = {
    "design": "Code design",
    "debug": "Bug squash",
    "integration": "Integration",
    "ai": "AI-assisted",
    "mock": "Mock interview",
}
PATTERNS = {
    "hashing": "Arrays & Hashing",
    "two-pointers": "Two Pointers",
    "sliding-window": "Sliding Window",
    "prefix-sum": "Prefix Sum",
    "stack": "Stack",
    "binary-search": "Binary Search",
    "linked-list": "Linked List",
    "trees": "Trees",
    "tries": "Tries",
    "heap": "Heap / Priority Queue",
    "intervals": "Intervals",
    "backtracking": "Backtracking",
    "graphs": "Graphs",
    "graphs-advanced": "Union-Find, Dijkstra, MST",
    "dp-1d": "1-D Dynamic Programming",
    "dp-2d": "2-D Dynamic Programming",
    "greedy": "Greedy",
    "design": "Data Structure Design",
}
DIFFICULTIES = ("Easy", "Medium", "Hard")
LOG_FIELDS = ["date", "track", "id", "slug", "title", "difficulty", "pattern", "kind",
              "minutes", "hints", "assisted", "confidence", "box", "next_review", "note"]
ROADMAP_FIELDS = ["order", "pattern", "id", "slug", "title", "difficulty"]
STATS_START = "<!-- lc:stats:start -->"
STATS_END = "<!-- lc:stats:end -->"
DEFAULT_CONFIG = {
    "leetcode_username": "",
    "timezone": "America/Los_Angeles",
    "solutions_dir": "solutions",
    "auto_push": True,
}


class LcError(Exception):
    """A problem the user can fix. Printed without a traceback."""


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


# ---------------------------------------------------------------- data files

def load_config(root: Path) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    path = root / "lc.config.json"
    if path.exists():
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    return cfg


def local_today(cfg: dict) -> dt.date:
    """Today's date in the configured time zone (falls back to the machine's clock)."""
    tz = cfg.get("timezone")
    if tz:
        try:
            from zoneinfo import ZoneInfo  # Windows needs the tzdata package for this
            return dt.datetime.now(ZoneInfo(tz)).date()
        except Exception:
            pass
    return dt.date.today()


def load_roadmap(root: Path) -> list[dict]:
    path = root / "roadmap.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_log(root: Path) -> list[dict]:
    path = root / "log.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_log(root: Path, row: dict) -> None:
    path = root / "log.csv"
    fresh = not path.exists() or path.stat().st_size == 0
    if not fresh and not path.read_bytes().endswith(b"\n"):
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n")
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS, lineterminator="\n")
        if fresh:
            writer.writeheader()
        writer.writerow(row)


# ---------------------------------------------------------------- problem metadata

def parse_slug(text: str) -> str:
    """Accept a slug, a LeetCode URL, or a LeetSync folder name like '1-two-sum'."""
    text = text.strip()
    m = re.search(r"leetcode\.(?:com|cn)/problems/([a-z0-9-]+)", text)
    if m:
        return m.group(1)
    m = re.fullmatch(r"\d+-([a-z0-9-]+)/?", text)
    if m:
        return m.group(1)
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def leetsync_dirs(root: Path, cfg: dict) -> dict[str, tuple[str, Path]]:
    """Map slug -> (problem number, folder) for folders LeetSync created."""
    base = root / cfg["solutions_dir"]
    found = {}
    if base.is_dir():
        for child in sorted(base.iterdir()):
            m = re.fullmatch(r"(\d+)-([a-z0-9-]+)", child.name)
            if child.is_dir() and m:
                found[m.group(2)] = (m.group(1), child)
    return found


def parse_leetsync_readme(folder: Path) -> tuple[str, str] | None:
    """LeetSync's README.md starts with the title link and a difficulty badge."""
    path = folder / "README.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    title = re.search(r'<h2><a href="https://leetcode\.com/problems/[^"]*">(.*?)</a></h2>', text)
    difficulty = re.search(r"alt='Difficulty: (Easy|Medium|Hard)'", text)
    if not title:
        return None
    return html.unescape(title.group(1)).strip(), difficulty.group(1) if difficulty else ""


def fetch_leetcode(slug: str, timeout: float = 8) -> dict | None:
    """Public problem metadata from LeetCode's GraphQL endpoint (no login needed)."""
    if os.environ.get("LC_OFFLINE"):
        return None
    query = ("query q($titleSlug: String!) { question(titleSlug: $titleSlug) "
             "{ questionFrontendId title difficulty topicTags { slug } } }")
    body = json.dumps({"query": query, "variables": {"titleSlug": slug}}).encode()
    request = urllib.request.Request(
        "https://leetcode.com/graphql", data=body,
        headers={"Content-Type": "application/json",
                 "Referer": f"https://leetcode.com/problems/{slug}/",
                 "User-Agent": "Mozilla/5.0 (lc.py practice log)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            question = json.load(response)["data"]["question"]
    except Exception:
        return None
    if not question:
        return None
    return {"id": question["questionFrontendId"], "title": question["title"],
            "difficulty": question["difficulty"],
            "tags": [t["slug"] for t in question.get("topicTags") or []]}


def resolve_problem(root: Path, cfg: dict, slug: str, args) -> dict:
    """Problem number, title and difficulty: LeetSync folder > roadmap > LeetCode > flags."""
    info = {"id": "", "title": "", "difficulty": "", "pattern": ""}
    for p in load_roadmap(root):
        if p["slug"] == slug:
            info.update(id=p["id"], title=p["title"], difficulty=p["difficulty"],
                        pattern=p["pattern"])
    synced = leetsync_dirs(root, cfg).get(slug)
    if synced:
        info["id"] = synced[0]  # came from LeetCode itself, so it wins over the roadmap
        meta = parse_leetsync_readme(synced[1])
        if meta:
            info["title"] = meta[0] or info["title"]
            info["difficulty"] = meta[1] or info["difficulty"]
    if not (info["id"] and info["title"] and info["difficulty"]):
        remote = fetch_leetcode(slug)
        if remote:
            for key in ("id", "title", "difficulty"):
                info[key] = info[key] or remote[key]
    for key in ("id", "title", "difficulty", "pattern"):
        value = getattr(args, key, None)
        if value:
            info[key] = value
    if not info["title"]:
        info["title"] = slug.replace("-", " ").title()
    return info


# ---------------------------------------------------------------- scheduling and streaks

def next_box(prev_box: int | None, hints: int, assisted: bool, confidence: int) -> int:
    """Leitner-style box for the next re-solve. prev_box is None on a first solve."""
    if assisted:
        return 0
    shaky = hints > 0 or confidence <= 2
    if prev_box is None:
        if shaky:
            return 1
        return 3 if confidence >= 4 else 2
    if shaky:
        return max(prev_box - 1, 0)
    if confidence >= 4:
        return min(prev_box + 1, len(LADDER) - 1)
    return prev_box


def run_ending_at(days: set[dt.date], day: dt.date) -> int:
    count = 0
    while day in days:
        count += 1
        day -= dt.timedelta(days=1)
    return count


def longest_run(days: set[dt.date]) -> int:
    best = 0
    for day in days:
        if day - dt.timedelta(days=1) not in days:  # first day of a run
            length = 0
            while day + dt.timedelta(days=length) in days:
                length += 1
            best = max(best, length)
    return best


def practice_days(rows: list[dict]) -> set[dt.date]:
    return {dt.date.fromisoformat(r["date"]) for r in rows}


def latest_algo(rows: list[dict]) -> dict[str, dict]:
    latest = {}
    for row in rows:
        if row["track"] == "algo":
            latest[row["slug"]] = row
    return latest


def due_reviews(rows: list[dict], today: dt.date) -> list[dict]:
    due = [r for r in latest_algo(rows).values()
           if r["next_review"] and dt.date.fromisoformat(r["next_review"]) <= today]
    return sorted(due, key=lambda r: (r["next_review"], int(r["box"] or 0)))


def next_problems(roadmap: list[dict], rows: list[dict], n: int = 3,
                  pattern: str | None = None, synced: set[str] = frozenset()) -> list[dict]:
    done = set(latest_algo(rows)) | set(synced)  # synced = solved, even if not logged yet
    todo = [p for p in sorted(roadmap, key=lambda p: int(p["order"]))
            if p["slug"] not in done and (not pattern or p["pattern"] == pattern)]
    return todo[:n]


# ---------------------------------------------------------------- README stats

def md(text: str) -> str:
    return text.replace("|", "\\|").replace("`", "\\`")


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def bar(done: int, total: int, width: int = 10) -> str:
    filled = min(width, round(width * done / total)) if total else 0
    return "█" * filled + "░" * (width - filled)


def problem_link(row: dict, cfg: dict) -> str:
    if row["track"] == "algo":
        return (f"[{row['id']}. {md(row['title'])}]"
                f"(https://leetcode.com/problems/{row['slug']}/)")
    folder = f"practical/{row['date']}-{row['track']}-{row['slug']}/debrief.md"
    return f"[{md(row['title'])}]({folder})"


def render_stats(root: Path, cfg: dict) -> str:
    """Deterministic for a given log, so CI can check the README is current."""
    rows = load_log(root)
    roadmap = load_roadmap(root)
    algo = [r for r in rows if r["track"] == "algo"]
    days = practice_days(rows)
    last = max(days) if days else None

    first_try = {}
    for r in algo:
        first_try.setdefault(r["slug"], r)
    solved = latest_algo(rows)
    by_difficulty = Counter(r["difficulty"] for r in solved.values())
    clean_first = sum(1 for r in first_try.values() if r["hints"] == "0" and r["assisted"] == "0")
    resolves = [r for r in algo if r["kind"] == "review"]
    retained = {r["slug"] for r in resolves if r["hints"] == "0" and r["assisted"] == "0"}
    sessions = Counter(r["track"] for r in rows if r["track"] != "algo")

    out = []
    user = cfg.get("leetcode_username")
    if user:
        out += [f"[![LeetCode stats](https://leetcard.jacoblin.cool/{user}?ext=heatmap)]"
                f"(https://leetcode.com/u/{user}/)", ""]
    if last:
        out.append(f"- **Streak:** {plural(run_ending_at(days, last), 'day')} as of {last} "
                   f"(longest {longest_run(days)}) · **Practice days:** {len(days)}")
    else:
        out.append("- **Streak:** not started yet · **Practice days:** 0")
    no_hint = f"{round(100 * clean_first / len(first_try))}%" if first_try else "n/a"
    out.append(f"- **Problems logged:** {len(solved)} ({by_difficulty['Easy']} Easy · "
               f"{by_difficulty['Medium']} Medium · {by_difficulty['Hard']} Hard) · "
               f"**Solved first try without hints:** {no_hint}")
    out.append(f"- **Re-solves:** {len(resolves)} · "
               f"**Retained** (solved again cleanly): {len(retained)}")
    out.append("- **Practical sessions:** " + " · ".join(
        f"{name} {sessions[key]}" for key, name in TRACK_NAMES.items()))
    out += ["", "| Pattern | Roadmap progress |", "|---|---|"]

    pattern_of = {p["slug"]: p["pattern"] for p in roadmap}
    total = Counter(p["pattern"] for p in roadmap)
    done = Counter(pattern_of.get(slug) or r["pattern"] for slug, r in solved.items())
    for key in list(PATTERNS) + sorted(set(done) - set(PATTERNS)):
        if total[key]:
            out.append(f"| {PATTERNS.get(key, key)} | {bar(done[key], total[key])} "
                       f"{done[key]}/{total[key]} |")
        elif done[key]:
            out.append(f"| {md(PATTERNS.get(key, key))} | {done[key]} solved (off roadmap) |")

    out += ["", "**Recent**", "",
            "| Date | Problem | Level / track | Pattern | Minutes | Hints |",
            "|---|---|---|---|---|---|"]
    recent = rows[-10:][::-1]
    if not recent:
        out.append("| | Nothing logged yet | | | | |")
    for r in recent:
        level = r["difficulty"] if r["track"] == "algo" else TRACK_NAMES[r["track"]]
        if r["kind"] == "review":
            level += " · re-solve"
        hints = r["hints"] + (" + saw solution" if r["assisted"] == "1" else "")
        pattern = PATTERNS.get(r["pattern"], r["pattern"]) if r["track"] == "algo" else ""
        out.append(f"| {r['date']} | {problem_link(r, cfg)} | {level} | {md(pattern)} | "
                   f"{r['minutes']} | {hints if r['track'] == 'algo' else ''} |")
    return "\n".join(out)


def stats_block(root: Path, cfg: dict) -> str:
    return f"{STATS_START}\n{render_stats(root, cfg)}\n{STATS_END}"


def write_readme_stats(root: Path, cfg: dict) -> bool:
    path = root / "README.md"
    text = read_text(path)
    if STATS_START not in text or STATS_END not in text:
        raise LcError(f"README.md needs the markers {STATS_START} and {STATS_END}")
    pattern = re.escape(STATS_START) + r".*?" + re.escape(STATS_END)
    updated = re.sub(pattern, lambda _: stats_block(root, cfg), text, count=1, flags=re.S)
    if updated != text:
        write_text(path, updated)
        return True
    return False


# ---------------------------------------------------------------- notes files

def render_template(root: Path, name: str, values: dict) -> str:
    text = read_text(root / "templates" / name)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def attempt_row(row: dict) -> str:
    hints = row["hints"] + (" + saw solution" if row["assisted"] == "1" else "")
    return (f"| {row['date']} | {row['kind']} | {row['minutes']} | {hints} | "
            f"{row['confidence']}/5 | {row['next_review']} |")


def update_approach(root: Path, cfg: dict, row: dict) -> Path:
    folder = root / cfg["solutions_dir"] / f"{row['id']}-{row['slug']}"
    path = folder / "approach.md"
    insight = row["note"] or ("<!-- One or two sentences, in my own words: "
                              "the observation that makes it work. -->")
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        text = render_template(root, "approach.md", {
            "id": row["id"], "title": row["title"], "slug": row["slug"],
            "difficulty": row["difficulty"],
            "pattern": PATTERNS.get(row["pattern"], row["pattern"]), "insight": insight})
    else:
        text = read_text(path)
    lines = text.rstrip("\n").split("\n")
    header = next((i for i, line in enumerate(lines) if line.startswith("| Date | Kind")), None)
    if header is None:
        lines += ["", "## Attempts", "| Date | Kind | Minutes | Hints | Confidence | Next re-solve |",
                  "|---|---|---|---|---|---|"]
        header = len(lines) - 2
    end = header + 2
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    lines.insert(end, attempt_row(row))
    write_text(path, "\n".join(lines) + "\n")
    return path


def create_debrief(root: Path, row: dict) -> Path:
    folder = root / "practical" / f"{row['date']}-{row['track']}-{row['slug']}"
    path = folder / "debrief.md"
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        write_text(path, render_template(root, "debrief.md", {
            "date": row["date"], "track": TRACK_NAMES[row["track"]], "title": row["title"],
            "prompt": TRACKS[row["track"]], "minutes": row["minutes"],
            "note": row["note"] or "<!-- What I'd do differently next time. -->"}))
    return path


# ---------------------------------------------------------------- git

def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=root, check=check, capture_output=True,
                              text=True)
    except FileNotFoundError:
        raise LcError("git isn't installed or isn't on PATH") from None


def git_pull(root: Path) -> None:
    if git(root, "rev-parse", "--abbrev-ref", "@{u}", check=False).returncode != 0:
        return  # not a clone, or no upstream yet
    result = git(root, "pull", "--rebase", "--autostash", "--quiet", check=False)
    if result.returncode != 0:
        print("warning: git pull failed, continuing with local files:", result.stderr.strip())


def open_editor(root: Path, path: Path) -> None:
    """Open the notes file in the editor git uses, and wait for it to close."""
    editor = git(root, "var", "GIT_EDITOR", check=False).stdout.strip()
    editor = editor or os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        print(f"no editor configured; edit {path.relative_to(root)} by hand")
        return
    print(f"opening {path.relative_to(root)} (close the editor to commit)")
    subprocess.run(f'{editor} "{path}"', shell=True, cwd=root)


def git_commit(root: Path, paths: list[Path], message: str, push: bool) -> None:
    git(root, "add", "--", *[str(p.relative_to(root)) for p in paths])
    result = git(root, "commit", "-m", message, check=False)
    if result.returncode != 0:
        raise LcError("git commit failed:\n" + (result.stderr or result.stdout).strip())
    print("committed:", message.splitlines()[0])
    if push:
        result = git(root, "push", check=False)
        if result.returncode != 0:
            print("warning: push failed (commit is saved locally):", result.stderr.strip())
        else:
            print("pushed")


# ---------------------------------------------------------------- commands

def cmd_log(args, root: Path, cfg: dict) -> None:
    track = args.track
    slug = parse_slug(args.problem)
    if not slug:
        raise LcError("give a problem slug, URL, or session name")
    day = dt.date.fromisoformat(args.date) if args.date else local_today(cfg)
    if not 1 <= args.confidence <= 5:
        raise LcError("--confidence is 1 (lost) to 5 (could teach it)")
    if args.minutes < 0:
        raise LcError("--minutes can't be negative")
    if track == "algo" and args.hints is None:
        raise LcError("--hints is required: count every hint rung, 0 if none")
    hints = args.hints or 0
    if hints < 0:
        raise LcError("--hints can't be negative")
    if not args.no_pull:
        git_pull(root)  # pick up whatever LeetSync pushed since the last pull

    rows = load_log(root)
    touched = []
    if track == "algo":
        info = resolve_problem(root, cfg, slug, args)
        if not info["id"]:
            raise LcError(f"couldn't find the LeetCode number for '{slug}'. "
                          "Pass --id N (the number before the title on LeetCode).")
        if info["difficulty"] and info["difficulty"] not in DIFFICULTIES:
            raise LcError(f"--difficulty must be one of {', '.join(DIFFICULTIES)}")
        previous = [r for r in rows if r["track"] == "algo" and r["slug"] == slug]
        prev_box = int(previous[-1]["box"]) if previous else None
        box = next_box(prev_box, hints, args.assisted, args.confidence)
        row = {"date": day.isoformat(), "track": track, "id": info["id"], "slug": slug,
               "title": info["title"], "difficulty": info["difficulty"],
               "pattern": info["pattern"] or "other", "kind": "review" if previous else "new",
               "minutes": str(args.minutes), "hints": str(hints),
               "assisted": "1" if args.assisted else "0", "confidence": str(args.confidence),
               "box": str(box), "next_review": (day + dt.timedelta(days=LADDER[box])).isoformat(),
               "note": args.note or ""}
        touched.append(update_approach(root, cfg, row))
    else:
        row = {"date": day.isoformat(), "track": track, "id": "", "slug": slug,
               "title": args.title or slug.replace("-", " ").capitalize(), "difficulty": "",
               "pattern": args.pattern or "", "kind": track, "minutes": str(args.minutes),
               "hints": str(hints), "assisted": "1" if args.assisted else "0",
               "confidence": str(args.confidence), "box": "", "next_review": "",
               "note": args.note or ""}
        touched.append(create_debrief(root, row))

    append_log(root, row)
    write_readme_stats(root, cfg)
    touched += [root / "log.csv", root / "README.md"]
    if args.edit:
        open_editor(root, touched[0])

    if track == "algo":
        print(f"logged {row['id']}. {row['title']} ({row['kind']}); "
              f"next re-solve {row['next_review']} (box {row['box']})")
        if row["pattern"] == "other":
            print("tip: pass -p PATTERN so it counts toward a pattern; keys:", ", ".join(PATTERNS))
        subject = (f"log: {row['id']}. {row['title']} · {PATTERNS.get(row['pattern'], row['pattern'])}"
                   f" · {row['minutes']}m · {plural(hints, 'hint')}"
                   f"{' + saw solution' if args.assisted else ''} · conf {row['confidence']}/5")
        body = f"Next re-solve: {row['next_review']}"
    else:
        print(f"logged {TRACK_NAMES[track]} session '{row['title']}' -> {touched[0].relative_to(root)}")
        subject = f"log: {TRACK_NAMES[track].lower()} session · {row['title']} · {row['minutes']}m"
        body = f"Debrief: {touched[0].relative_to(root).as_posix()}"
    if args.no_commit:
        return
    message = subject + "\n\n" + body
    if args.trailer:
        message += "\n\n" + "\n".join(args.trailer)
    push = cfg.get("auto_push", True) and not args.no_push
    git_commit(root, touched, message, push)


def cmd_today(args, root: Path, cfg: dict) -> None:
    today = local_today(cfg)
    rows = load_log(root)
    days = practice_days(rows)
    last = max(days) if days else None
    alive = last is not None and (today - last).days <= 1
    streak = run_ending_at(days, last) if alive else 0
    if today in days:
        status = "done for today"
    elif streak:
        status = "practice today to keep it going"
    else:
        status = "start one today"
    print(f"{today} · streak {streak} · {status}\n")

    due = due_reviews(rows, today)
    print("Re-solve from scratch (no peeking at your old code):")
    for r in due[:5]:
        print(f"  {r['id']}. {r['title']} ({r['difficulty']}, {PATTERNS.get(r['pattern'], r['pattern'])})"
              f"  due {r['next_review']}")
    if not due:
        print("  nothing due")
    if len(due) > 5:
        print(f"  ...and {len(due) - 5} more")

    logged = set(latest_algo(rows))
    unlogged = [(pid, slug) for slug, (pid, _) in leetsync_dirs(root, cfg).items()
                if slug not in logged]
    if unlogged:
        print("\nSynced by LeetSync but not logged yet:")
        for pid, slug in unlogged:
            print(f"  {pid}-{slug}  ->  python lc.py log {slug} -m MIN -H HINTS -c CONF")

    print("\nNext on the roadmap:")
    for p in next_problems(load_roadmap(root), rows, n=3, synced=set(leetsync_dirs(root, cfg))):
        print(f"  {p['id']}. {p['title']} ({p['difficulty']}, {PATTERNS.get(p['pattern'], p['pattern'])})"
              f"  https://leetcode.com/problems/{p['slug']}/")

    week = [r for r in rows if (today - dt.date.fromisoformat(r["date"])).days < 7]
    if not any(r["track"] != "algo" for r in week):
        recent_track = {}
        for r in rows:
            if r["track"] != "algo":
                recent_track[r["track"]] = r["date"]
        pick = min(TRACK_NAMES, key=lambda t: recent_track.get(t, ""))
        print(f"\nNo practical session in the last 7 days. Next up: {TRACK_NAMES[pick].lower()}"
              f" ({TRACKS[pick]}).")


def cmd_next(args, root: Path, cfg: dict) -> None:
    if args.pattern and args.pattern not in PATTERNS:
        raise LcError("unknown pattern; keys: " + ", ".join(PATTERNS))
    todo = next_problems(load_roadmap(root), load_log(root), n=args.n, pattern=args.pattern,
                         synced=set(leetsync_dirs(root, cfg)))
    for p in todo:
        print(f"{p['id']}. {p['title']} ({p['difficulty']}, {PATTERNS[p['pattern']]})  "
              f"https://leetcode.com/problems/{p['slug']}/")
    if not todo:
        print("roadmap done for this selection")


def cmd_stats(args, root: Path, cfg: dict) -> None:
    changed = write_readme_stats(root, cfg)
    print(render_stats(root, cfg))
    print("\nREADME.md updated" if changed else "\nREADME.md already current")


def check_errors(root: Path, cfg: dict) -> list[str]:
    errors = []
    roadmap = load_roadmap(root)
    seen = set()
    for i, p in enumerate(roadmap, start=2):
        where = f"roadmap.csv line {i}"
        if list(p) != ROADMAP_FIELDS:
            errors.append(f"{where}: columns must be {ROADMAP_FIELDS}")
            break
        if p["slug"] in seen:
            errors.append(f"{where}: duplicate slug {p['slug']}")
        seen.add(p["slug"])
        if p["pattern"] not in PATTERNS:
            errors.append(f"{where}: unknown pattern {p['pattern']}")
        if p["difficulty"] not in DIFFICULTIES:
            errors.append(f"{where}: bad difficulty {p['difficulty']}")
        if not p["id"].isdigit() or not p["order"].isdigit():
            errors.append(f"{where}: id and order must be numbers")
    path = root / "log.csv"
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), [])
        if header != LOG_FIELDS:
            errors.append(f"log.csv: header must be {','.join(LOG_FIELDS)}")
            return errors
    for i, r in enumerate(load_log(root), start=2):
        where = f"log.csv line {i}"
        try:
            dt.date.fromisoformat(r["date"])
            if r["track"] not in TRACKS:
                raise ValueError(f"unknown track {r['track']}")
            if not 1 <= int(r["confidence"]) <= 5 or int(r["minutes"]) < 0 or int(r["hints"]) < 0:
                raise ValueError("confidence 1-5, minutes and hints >= 0")
            if r["assisted"] not in ("0", "1"):
                raise ValueError("assisted must be 0 or 1")
            if r["track"] == "algo":
                if not r["id"].isdigit():
                    raise ValueError("algo rows need a problem number")
                if not 0 <= int(r["box"]) < len(LADDER):
                    raise ValueError("box out of range")
                dt.date.fromisoformat(r["next_review"])
        except (ValueError, TypeError, KeyError) as exc:
            errors.append(f"{where}: {exc}")
    readme = root / "README.md"
    if readme.exists() and not errors:
        if stats_block(root, cfg) not in read_text(readme):
            errors.append("README.md stats are stale: run python lc.py stats")
    return errors


def cmd_check(args, root: Path, cfg: dict) -> None:
    errors = check_errors(root, cfg)
    for e in errors:
        print("error:", e)
    if errors:
        raise SystemExit(1)
    print(f"ok: {len(load_roadmap(root))} roadmap problems, {len(load_log(root))} log entries")


def cmd_doctor(args, root: Path, cfg: dict) -> None:
    print(f"python {sys.version.split()[0]}")
    name = git(root, "config", "user.name", check=False).stdout.strip()
    email = git(root, "config", "user.email", check=False).stdout.strip()
    print(f"git identity: {name or '(none)'} <{email or 'none'}>")
    if not email:
        print("  set one: git config user.email YOUR_ID+USERNAME@users.noreply.github.com")
    elif not email.endswith("users.noreply.github.com"):
        print("  this email must be added to your GitHub account, or commits won't count "
              "on your contribution graph")
    remote = git(root, "remote", "get-url", "origin", check=False).stdout.strip()
    print(f"remote: {remote or '(none)'}")
    print(f"today: {local_today(cfg)} ({cfg.get('timezone') or 'machine clock'})")
    print(f"leetcode_username: {cfg.get('leetcode_username') or '(not set: stats card hidden)'}")
    print(f"LeetSync folders in {cfg['solutions_dir']}/: {len(leetsync_dirs(root, cfg))}")
    errors = check_errors(root, cfg)
    print("data files: " + ("ok" if not errors else f"{len(errors)} problem(s), run python lc.py check"))
    if not args.online:
        return
    roadmap = load_roadmap(root)
    print(f"checking {len(roadmap)} roadmap problems against LeetCode...")
    bad = 0
    for p in roadmap:
        remote = fetch_leetcode(p["slug"])
        if remote is None:
            print(f"  {p['slug']}: not found (or LeetCode unreachable)")
            bad += 1
            continue
        diffs = [f"{k} {p[k]!r} -> {remote[k]!r}" for k in ("id", "title", "difficulty")
                 if p[k] != remote[k]]
        if diffs:
            print(f"  {p['slug']}: " + "; ".join(diffs))
            bad += 1
    print("roadmap matches LeetCode" if not bad else f"{bad} roadmap row(s) need fixing")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lc", description="Daily interview-practice log.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("today", help="what to do today")

    p = sub.add_parser("next", help="next unsolved roadmap problems")
    p.add_argument("-n", type=int, default=5)
    p.add_argument("-p", "--pattern", help="only this pattern key")

    p = sub.add_parser("log", help="record an attempt or practice session")
    p.add_argument("problem", help="LeetCode slug or URL; for other tracks, a short session name")
    p.add_argument("-m", "--minutes", type=int, required=True, help="time spent")
    p.add_argument("-H", "--hints", type=int, help="hint rungs used (required for algo)")
    p.add_argument("-c", "--confidence", type=int, required=True,
                   help="1 = lost, 3 = got there, 5 = could teach it")
    p.add_argument("-p", "--pattern", help="pattern key (roadmap problems fill this in)")
    p.add_argument("-n", "--note", help="the key insight, one line, in your own words")
    p.add_argument("-a", "--assisted", action="store_true",
                   help="you saw a solution (resets the review schedule)")
    p.add_argument("-t", "--track", choices=list(TRACKS), default="algo")
    p.add_argument("--title", help="override the title")
    p.add_argument("--id", help="LeetCode problem number, if it can't be found")
    p.add_argument("--difficulty", choices=DIFFICULTIES)
    p.add_argument("--date", help="YYYY-MM-DD, if logging an earlier day's practice")
    p.add_argument("-e", "--edit", action="store_true",
                   help="open the notes file in your editor before committing")
    p.add_argument("--trailer", action="append", help="extra line for the commit message")
    p.add_argument("--no-commit", action="store_true")
    p.add_argument("--no-push", action="store_true")
    p.add_argument("--no-pull", action="store_true")

    sub.add_parser("stats", help="rebuild the README stats block")
    sub.add_parser("check", help="validate data files and README (CI)")
    p = sub.add_parser("doctor", help="check setup")
    p.add_argument("--online", action="store_true", help="verify roadmap.csv against LeetCode")
    return parser


COMMANDS = {"today": cmd_today, "next": cmd_next, "log": cmd_log, "stats": cmd_stats,
            "check": cmd_check, "doctor": cmd_doctor}


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    args = build_parser().parse_args(argv)
    try:
        COMMANDS[args.command](args, root, load_config(root))
    except LcError as exc:
        print("error:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
