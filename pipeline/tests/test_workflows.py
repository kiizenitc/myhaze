import re

from myhaze.config import REPO_ROOT


def test_every_github_action_is_pinned_to_a_commit_sha():
    # The repo is public and its workflows hold the database and aqicn secrets, so a moved tag must not change code.
    uses = []
    for path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")):
        uses += re.findall(r"uses:\s*([^\s#]+)", path.read_text(encoding="utf-8"))
    assert uses, "no workflows found"
    assert [u for u in uses if not re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u)] == []

def test_the_forecast_workflow_builds_the_site_then_deploys_only_with_cloudflare_secrets():
    text = (REPO_ROOT / ".github" / "workflows" / "forecast.yml").read_text(encoding="utf-8")
    assert text.index("npm --prefix web run build") < text.index("myhaze.jobs.forecast")
    assert '--out "$GITHUB_WORKSPACE/web/out/data"' in text
    assert "if: env.HAS_CLOUDFLARE == 'true'" in text and "npx wrangler deploy" in text


def test_ci_runs_the_web_tests_typecheck_and_build():
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for command in ("npm --prefix web ci", "npm --prefix web test", "npm --prefix web run typecheck",
                    "npm --prefix web run build"):
        assert command in text

def test_ci_runs_the_scheduler_tests():
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "npm --prefix scheduler test" in text and "npm --prefix scheduler run typecheck" in text
