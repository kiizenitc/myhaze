import re

from myhaze.config import REPO_ROOT


def test_every_github_action_is_pinned_to_a_commit_sha():
    # The repo is public and its workflows hold the database and aqicn secrets, so a moved tag must not change code.
    uses = []
    for path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")):
        uses += re.findall(r"uses:\s*([^\s#]+)", path.read_text(encoding="utf-8"))
    assert uses, "no workflows found"
    assert [u for u in uses if not re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u)] == []
