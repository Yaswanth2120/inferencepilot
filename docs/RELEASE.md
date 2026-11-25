# v0.1.0 release verification

This document defines the v0.1.0 release gate. The published
[GitHub release](https://github.com/Yaswanth2120/inferencepilot/releases/tag/v0.1.0),
annotated tag and attached verification/checksum files identify the final artifacts.

## Required checks

1. Review and merge the release PR after all six Linux/macOS × Python 3.10–3.12
   CI jobs pass. Each job checks version consistency, builds a wheel, runs Ruff,
   pytest and the offline selftest.
2. In a new directory, clone the merged public repository and follow the README
   quickstart verbatim: Python 3.12 `venv`, `pip install -e '.[dev,report]'`, `pytest`,
   `ruff check .`, and `inferencepilot selftest`.
3. Build wheel and source archives from that clean merged checkout. Inspect their
   version, MIT license, fake executables and source contents. Build the wheel
   through the source archive so missing manifest content is caught.
4. In another new virtualenv outside the checkout, install the actual wheel with
   dev/report extras. Remove PYTHONPATH, verify imports resolve to site-packages,
   check package/CLI/metadata version agreement, run `pip check`, and run the full
   standalone offline selftest. Never substitute an editable install for this check.
5. Recheck the schema-v1 snapshot/hash and verify that v0.1.0 makes no DDL migration.
   Generate SHA256SUMS and a sanitized release-verification.json for the artifacts.
6. Create an annotated `v0.1.0` tag at the verified merged commit, push the tag, and
   publish the tested wheel, source archive and verification files on GitHub.
   Verify the public assets against their local hashes. Never move an existing tag.

## Release scope

The release includes the completed Qwen3 campaign and the narrower existing-server
GPT-OSS performance results. Source/statistical caveats are preserved in the
README, design, fixture coverage and final report. SQLite schema version 1 is
frozen independently of package version 0.1.0; see [SCHEMA.md](SCHEMA.md).

Optional GPT-OSS startup/context/OOM-boundary tests were intentionally omitted:
**not run (needs GPU)**. No GPU/SSH, additional model execution, rental lifecycle
action, or PyPI upload is needed for these release checks.

The wheel is a package/CLI distribution, not a vLLM or CUDA distribution. vLLM is
invoked externally and live dependencies are installed separately on the GPU host.
The source archive additionally includes configs, docs, scripts, tests, fixtures,
and published reports; local data and environments are excluded. The MIT license
is included in both archives.

Release-candidate local verification: **317 tests passed in 156.66 seconds**, Ruff
passed, and CLI/metadata version agreement was checked. Wheel/source contents,
MIT SPDX metadata and executable fake-tool modes were inspected. The final merged
clone and standalone-wheel results are recorded in the release attachment.
