import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import review_package


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    })
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env)
    assert proc.returncode == 0, f"git {args}: {proc.stderr}"
    return proc


def make_repo(root: Path) -> str:
    git(root, "init", "-q")
    (root / "a.txt").write_text("alpha\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "b.txt").write_text("beta\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "baseline")
    return git(root, "rev-parse", "HEAD").stdout.strip()


def run_create(repo: Path, baseline: str, out: Path, *extra: str) -> dict:
    argv = ["create", "--repo", str(repo), "--baseline", baseline, "--out", str(out), *extra]
    rc = review_package.main_with(argv)
    assert rc == 0
    return json.loads((out / "snapshot.json").read_text(encoding="utf-8"))


class ReviewPackageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.baseline = make_repo(self.repo)
        self.out = self.root / "evidence"

    def test_create_covers_modified_and_untracked_then_verify_current(self) -> None:
        (self.repo / "a.txt").write_text("alpha v2\n", encoding="utf-8")
        (self.repo / "c.txt").write_text("untracked\n", encoding="utf-8")
        snapshot = run_create(self.repo, self.baseline, self.out)
        by_path = {e["path"]: e for e in snapshot["files"]}
        self.assertEqual(by_path["a.txt"]["status"], "modified-or-new")
        self.assertEqual(by_path["c.txt"]["status"], "untracked")
        self.assertEqual(snapshot["baseline"], self.baseline)
        self.assertEqual(snapshot["head"], git(self.repo, "rev-parse", "HEAD").stdout.strip())
        diff = (self.out / "review.diff").read_text(encoding="utf-8")
        self.assertIn("alpha v2", diff)
        self.assertIn("untracked", diff)
        self.assertTrue((self.out / "dispatch-scaffold.md").is_file())
        scaffold = (self.out / "dispatch-scaffold.md").read_text(encoding="utf-8")
        self.assertIn(snapshot["scopeSha256"], scaffold)
        self.assertIn("[REQUIRED:", scaffold)
        self.assertEqual(review_package.main_with(["verify", "--snapshot", str(self.out / "snapshot.json")]), 0)

    def test_verify_reports_drift(self) -> None:
        (self.repo / "a.txt").write_text("alpha v2\n", encoding="utf-8")
        run_create(self.repo, self.baseline, self.out)
        (self.repo / "a.txt").write_text("alpha v3\n", encoding="utf-8")
        self.assertEqual(review_package.main_with(["verify", "--snapshot", str(self.out / "snapshot.json")]), 1)

    def test_scoped_paths_limit_package(self) -> None:
        (self.repo / "a.txt").write_text("alpha v2\n", encoding="utf-8")
        (self.repo / "sub" / "b.txt").write_text("beta v2\n", encoding="utf-8")
        snapshot = run_create(self.repo, self.baseline, self.out, "--path", "sub")
        self.assertEqual([e["path"] for e in snapshot["files"]], ["sub/b.txt"])

    def test_deleted_file_recorded(self) -> None:
        (self.repo / "a.txt").unlink()
        snapshot = run_create(self.repo, self.baseline, self.out)
        entry = {e["path"]: e for e in snapshot["files"]}["a.txt"]
        self.assertEqual(entry["status"], "deleted")
        self.assertIsNone(entry["sha256"])
        self.assertEqual(review_package.main_with(["verify", "--snapshot", str(self.out / "snapshot.json")]), 0)

    def test_non_ascii_path_in_scope(self) -> None:
        (self.repo / "中文-日志.md").write_text("记录\n", encoding="utf-8")
        snapshot = run_create(self.repo, self.baseline, self.out, "--path", "中文-日志.md")
        self.assertEqual([e["path"] for e in snapshot["files"]], ["中文-日志.md"])
        diff = (self.out / "review.diff").read_text(encoding="utf-8")
        self.assertIn("记录", diff)
        self.assertEqual(review_package.main_with(["verify", "--snapshot", str(self.out / "snapshot.json")]), 0)

    def test_staged_new_file_in_diff(self) -> None:
        # regression: staged-but-uncommitted new file must appear in review.diff
        (self.repo / "staged_new.py").write_text("print('staged')\n", encoding="utf-8")
        git(self.repo, "add", "staged_new.py")
        run_create(self.repo, self.baseline, self.out)
        diff = (self.out / "review.diff").read_text(encoding="utf-8")
        self.assertIn("staged_new.py", diff)
        self.assertIn("print('staged')", diff)

    def test_verify_catches_post_dispatch_addition(self) -> None:
        # regression: a file added after dispatch must flip verify to stale
        (self.repo / "a.txt").write_text("alpha v2\n", encoding="utf-8")
        run_create(self.repo, self.baseline, self.out)
        (self.repo / "late.txt").write_text("late\n", encoding="utf-8")
        self.assertEqual(review_package.main_with(["verify", "--snapshot", str(self.out / "snapshot.json")]), 1)


if __name__ == "__main__":
    unittest.main()
