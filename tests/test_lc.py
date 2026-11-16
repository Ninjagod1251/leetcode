import datetime as dt
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["LC_OFFLINE"] = "1"  # tests never call LeetCode
import lc  # noqa: E402

# What LeetSync writes as solutions/<id>-<slug>/README.md (statement shortened).
LEETSYNC_README = (
    '<h2><a href="https://leetcode.com/problems/add-two-numbers">Add Two Numbers</a></h2> '
    "<img src='https://img.shields.io/badge/Difficulty-Medium-orange' alt='Difficulty: Medium' />"
    "<hr><p>You are given two non-empty linked lists...</p>")


class Repo:
    """A throwaway copy of the repo's data files."""

    def __init__(self, test: unittest.TestCase):
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ("roadmap.csv", "log.csv", "lc.config.json", "README.md"):
            shutil.copy(ROOT / name, self.root / name)
        shutil.copytree(ROOT / "templates", self.root / "templates")
        (self.root / "solutions").mkdir()

    def run(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lc.main(list(argv), root=self.root)
        return code, out.getvalue() + err.getvalue()

    def log(self, *argv):
        return self.run("log", *argv, "--no-commit", "--no-pull")

    def rows(self):
        return lc.load_log(self.root)

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")


class ScheduleTest(unittest.TestCase):
    def test_first_solve(self):
        self.assertEqual(lc.next_box(None, hints=0, assisted=False, confidence=4), 3)
        self.assertEqual(lc.next_box(None, hints=0, assisted=False, confidence=3), 2)
        self.assertEqual(lc.next_box(None, hints=1, assisted=False, confidence=5), 1)
        self.assertEqual(lc.next_box(None, hints=0, assisted=False, confidence=2), 1)
        self.assertEqual(lc.next_box(None, hints=3, assisted=True, confidence=4), 0)

    def test_review(self):
        self.assertEqual(lc.next_box(3, hints=0, assisted=False, confidence=5), 4)
        self.assertEqual(lc.next_box(3, hints=0, assisted=False, confidence=3), 3)
        self.assertEqual(lc.next_box(3, hints=1, assisted=False, confidence=4), 2)
        self.assertEqual(lc.next_box(0, hints=1, assisted=False, confidence=4), 0)
        self.assertEqual(lc.next_box(5, hints=0, assisted=True, confidence=5), 0)
        self.assertEqual(lc.next_box(6, hints=0, assisted=False, confidence=5), 6)


class StreakTest(unittest.TestCase):
    def test_runs(self):
        d = dt.date(2026, 11, 1)
        days = {d, d + dt.timedelta(1), d + dt.timedelta(2), d + dt.timedelta(4)}
        self.assertEqual(lc.run_ending_at(days, d + dt.timedelta(2)), 3)
        self.assertEqual(lc.run_ending_at(days, d + dt.timedelta(4)), 1)
        self.assertEqual(lc.run_ending_at(days, d + dt.timedelta(3)), 0)
        self.assertEqual(lc.longest_run(days), 3)
        self.assertEqual(lc.longest_run(set()), 0)


class ParseSlugTest(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(lc.parse_slug("https://leetcode.com/problems/two-sum/description/"), "two-sum")
        self.assertEqual(lc.parse_slug("1-two-sum"), "two-sum")
        self.assertEqual(lc.parse_slug("Two Sum"), "two-sum")
        self.assertEqual(lc.parse_slug("3sum"), "3sum")


class LogAlgoTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)

    def test_first_solve_then_review(self):
        code, out = self.repo.log("two-sum", "-m", "18", "-H", "0", "-c", "4",
                                  "-n", "store complement -> index", "--date", "2026-11-16")
        self.assertEqual(code, 0, out)
        row = self.repo.rows()[-1]
        self.assertEqual((row["id"], row["kind"], row["box"], row["next_review"]),
                         ("1", "new", "3", "2026-11-30"))
        self.assertEqual(row["pattern"], "hashing")
        notes = self.repo.read("solutions/1-two-sum/approach.md")
        self.assertIn("# 1. Two Sum", notes)
        self.assertIn("store complement -> index", notes)
        self.assertIn("| 2026-11-16 | new | 18 | 0 | 4/5 | 2026-11-30 |", notes)
        readme = self.repo.read("README.md")
        self.assertIn("**Streak:** 1 day as of 2026-11-16", readme)
        self.assertIn("**Problems:** 1 (1 Easy", readme)

        code, out = self.repo.log("two-sum", "-m", "9", "-H", "1", "-c", "3", "--date", "2026-11-30")
        self.assertEqual(code, 0, out)
        row = self.repo.rows()[-1]
        self.assertEqual((row["kind"], row["box"], row["next_review"]), ("review", "2", "2026-12-07"))
        notes = self.repo.read("solutions/1-two-sum/approach.md")
        first = notes.index("| 2026-11-16 |")
        second = notes.index("| 2026-11-30 | review | 9 | 1 | 3/5 | 2026-12-07 |")
        self.assertLess(first, second)
        self.assertEqual(lc.check_errors(self.repo.root, lc.load_config(self.repo.root)), [])

    def test_assisted_is_visible(self):
        self.repo.log("valid-anagram", "-m", "30", "-H", "3", "-c", "2", "-a", "--date", "2026-11-16")
        row = self.repo.rows()[-1]
        self.assertEqual((row["assisted"], row["box"], row["next_review"]), ("1", "0", "2026-11-17"))
        readme = self.repo.read("README.md")
        self.assertIn("3 + saw solution", readme)
        self.assertIn("**Solved first try without hints:** 0%", readme)

    def test_hints_required_for_algo(self):
        code, out = self.repo.log("two-sum", "-m", "10", "-c", "4")
        self.assertEqual(code, 1)
        self.assertIn("--hints is required", out)

    def test_leetsync_folder_supplies_metadata(self):
        folder = self.repo.root / "solutions" / "2-add-two-numbers"
        folder.mkdir()
        (folder / "README.md").write_text(LEETSYNC_README, encoding="utf-8")
        lc.local_today, saved = (lambda cfg: dt.date(2026, 11, 16)), lc.local_today
        try:
            _, out = self.repo.run("today")
        finally:
            lc.local_today = saved
        self.assertIn("2-add-two-numbers", out)  # synced but not logged yet
        folder2 = self.repo.root / "solutions" / "217-contains-duplicate"
        folder2.mkdir()
        _, out = self.repo.run("next", "-n", "1")
        self.assertNotIn("Contains Duplicate", out)  # synced counts as solved
        code, out = self.repo.log("add-two-numbers", "-m", "30", "-H", "2", "-c", "2",
                                  "-p", "linked-list", "--date", "2026-11-16")
        self.assertEqual(code, 0, out)
        row = self.repo.rows()[-1]
        self.assertEqual((row["id"], row["title"], row["difficulty"], row["box"]),
                         ("2", "Add Two Numbers", "Medium", "1"))
        self.assertTrue((folder / "approach.md").exists())
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["README.md", "approach.md"])

    def test_unknown_problem_needs_id(self):
        code, out = self.repo.log("some-new-problem", "-m", "20", "-H", "0", "-c", "3")
        self.assertEqual(code, 1)
        self.assertIn("--id", out)
        code, out = self.repo.log("some-new-problem", "-m", "20", "-H", "0", "-c", "3",
                                  "--id", "3999", "--difficulty", "Hard", "--date", "2026-11-16")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.repo.rows()[-1]["pattern"], "other")
        self.assertIn("| other | 1 solved (off roadmap) |", self.repo.read("README.md"))

    def test_attempt_rows_stay_in_the_table(self):
        self.repo.log("two-sum", "-m", "18", "-H", "0", "-c", "4", "--date", "2026-11-16")
        path = self.repo.root / "solutions/1-two-sum/approach.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n## Later thoughts\nhash maps\n",
                        encoding="utf-8")
        self.repo.log("two-sum", "-m", "8", "-H", "0", "-c", "5", "--date", "2026-11-30")
        lines = path.read_text(encoding="utf-8").splitlines()
        i = lines.index("| 2026-11-16 | new | 18 | 0 | 4/5 | 2026-11-30 |")
        self.assertTrue(lines[i + 1].startswith("| 2026-11-30 | review | 8 |"))
        self.assertIn("## Later thoughts", lines)


class PracticalTest(unittest.TestCase):
    def test_design_session(self):
        repo = Repo(self)
        code, out = repo.log("rate-limiter", "-t", "design", "-m", "60", "-c", "3",
                             "-n", "settle the API first", "--date", "2026-11-17")
        self.assertEqual(code, 0, out)
        debrief = repo.read("practical/2026-11-17-design-rate-limiter/debrief.md")
        self.assertIn("Code design: Rate limiter", debrief)
        self.assertIn("settle the API first", debrief)
        row = repo.rows()[-1]
        self.assertEqual((row["box"], row["next_review"]), ("", ""))
        readme = repo.read("README.md")
        self.assertIn("Code design 1", readme)
        self.assertIn("(practical/2026-11-17-design-rate-limiter/debrief.md)", readme)


class TodayTest(unittest.TestCase):
    def test_due_and_next(self):
        repo = Repo(self)
        repo.log("two-sum", "-m", "25", "-H", "2", "-c", "2", "-a", "--date", "2026-11-16")
        lc.local_today, saved = (lambda cfg: dt.date(2026, 11, 18)), lc.local_today
        try:
            code, out = repo.run("today")
        finally:
            lc.local_today = saved
        self.assertEqual(code, 0, out)
        self.assertIn("streak 0", out)
        self.assertIn("1. Two Sum (Easy, Arrays & Hashing)  due 2026-11-17", out)
        self.assertIn("217. Contains Duplicate", out)  # first unsolved roadmap problem
        self.assertIn("No practical session in the last 7 days", out)


class CheckTest(unittest.TestCase):
    def test_real_repo_is_consistent(self):
        self.assertEqual(lc.check_errors(ROOT, lc.load_config(ROOT)), [])

    def test_bad_row_fails(self):
        repo = Repo(self)
        with open(repo.root / "log.csv", "a", encoding="utf-8") as f:
            f.write("2026-11-16,algo,1,two-sum,Two Sum,Easy,hashing,new,10,0,0,9,3,2026-11-30,\n")
        errors = lc.check_errors(repo.root, lc.load_config(repo.root))
        self.assertTrue(any("confidence" in e for e in errors), errors)

    def test_stale_readme_fails(self):
        repo = Repo(self)
        repo.log("two-sum", "-m", "18", "-H", "0", "-c", "4", "--date", "2026-11-16")
        readme = repo.root / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8").replace("1 day", "9 days"),
                          encoding="utf-8")
        errors = lc.check_errors(repo.root, lc.load_config(repo.root))
        self.assertTrue(any("stale" in e for e in errors), errors)

    def test_markdown_escaping(self):
        self.assertEqual(lc.md("All O`one | x"), "All O\\`one \\| x")


@unittest.skipUnless(shutil.which("git"), "git not installed")
class CommitTest(unittest.TestCase):
    def test_commit_message_and_files(self):
        repo = Repo(self)
        root = repo.root

        def git(*args):
            return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                                  text=True).stdout

        git("init", "-q")
        git("config", "user.name", "Test")
        git("config", "user.email", "test@example.com")
        git("config", "commit.gpgsign", "false")
        git("add", ".")
        git("commit", "-qm", "init")
        (root / "scratch.txt").write_text("not mine to commit", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lc.main(["log", "two-sum", "-m", "18", "-H", "0", "-c", "4", "--no-push",
                            "--date", "2026-11-16", "--trailer", "Co-Authored-By: Someone <a@b.c>"],
                           root=root)
        self.assertEqual(code, 0, err.getvalue())
        message = git("log", "-1", "--format=%B")
        self.assertTrue(message.startswith("log: 1. Two Sum · Arrays & Hashing · 18m · 0 hints · conf 4/5"))
        self.assertIn("Next re-solve: 2026-11-30", message)
        self.assertIn("Co-Authored-By: Someone <a@b.c>", message)
        files = git("show", "--name-only", "--format=", "HEAD").split()
        self.assertEqual(sorted(files), ["README.md", "log.csv", "solutions/1-two-sum/approach.md"])
        self.assertIn("scratch.txt", git("status", "--porcelain"))  # left alone


if __name__ == "__main__":
    unittest.main()
