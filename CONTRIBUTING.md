# Contributing

Read AGENTS.md fully. Work on one milestone per session, keep functions small,
and run `pytest` and `ruff check .` before proposing a change. Do not import
vLLM or install unapproved dependencies. This project uses the MIT license.

## Git workflow

`main` contains reviewed work. Start milestone changes on `feature/mN-description`,
fixes on `bug/short-description`, documentation on `docs/short-description`, and
maintenance on `chore/short-description`. Use conventional commit subjects such
as `feat(planner): add deterministic OFAT schedules` or `fix(config): reject invalid budgets`.
Use a pull request with test results and explicit limitations; squash merge after
required CI passes. Never force push `main`, commit credentials, or commit data/.

Milestone work uses dedicated branches. Historical reserved branches are
reserved references to the setup commit, not implementations or completed work.
Before using an unused milestone branch, merge the latest origin/main into it.
Do not merge future branches into main merely because they exist.

| Milestone | Branch |
| --- | --- |
| M0 | feature/m0-offline-foundation (historical M0 snapshot) |
| M1 | feature/m1-config-planner |
| M2 | feature/m2-statistics |
| M3 | feature/m3-server-manager |
| M4 | feature/m4-loadgen-metrics |
| M5 | feature/m5-quality |
| M6 | feature/m6-store-runner |
| M7 | feature/m7-regression-validation |
| M8 | feature/m8-recommender-report |
| M9 | feature/m9-live-campaign |
| M10 | feature/m10-gpt-oss-validation (optional) |
| M11 | chore/m11-release-v0.1.0 |

No empty bug branches are needed: create them when a concrete defect is assigned.
For a solo maintainer, the main protection requires CI and a PR, with zero required
external approvals so it does not make self-maintenance impossible.

## Dependent milestones

If the previous milestone PR is still open, fast-forward the new milestone
branch to that previous branch and open a stacked PR against it. This keeps the
new PR diff limited to its own milestone. CI runs for PRs targeting any branch.
After the earlier PR is squash-merged, retarget the next PR to main and preserve
a readable history; do not bypass protections to unblock a dependency.

## Releases

Use a reviewed `chore/` release branch, consistent package/CLI metadata, clean-clone
pytest/Ruff/selftest, and separately installed artifact checks. All required CI
checks must pass before merging and creating an annotated version tag. Publish
tested wheel/source archives with SHA-256 checksums and release notes. Keep schema
v1 frozen as documented in docs/SCHEMA.md; do not silently migrate stored studies.
Optional unrun experiments remain labelled, not inferred complete from a tag.
