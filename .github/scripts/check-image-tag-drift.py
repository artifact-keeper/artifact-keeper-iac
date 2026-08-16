#!/usr/bin/env python3
"""Fail when a chart image pin has drifted behind its component's latest release.

The chart pins `backend.image.tag` and `web.image.tag` to "that component's
latest published release" (see the IMAGE TAGS note at the top of
`charts/artifact-keeper/values.yaml`), and `appVersion` to the backend's.
Nothing enforced that, so the pins silently fell two to three minors behind
across several chart releases (issue #301).

This is deliberately a *different* check from `verify-image-references` in
helm-ci.yml. That gate answers "does the pinned tag exist on the registry?" --
it catches a pin pointing at an unbuilt image, which breaks at pull time. This
gate answers "is the pinned tag the current release?" -- it catches a pin that
resolves perfectly but deploys old software.

Failure-mode note: drift is a hard failure, but an unreachable GitHub API is
only a warning. The dangerous direction (pinning a tag that does not exist)
stays hard-gated by verify-image-references; a staleness check that goes red on
a transient API hiccup would just train people to bypass it.

Usage:
    python3 .github/scripts/check-image-tag-drift.py [--chart-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

# Component -> the GitHub repo whose latest release the pin must track.
COMPONENT_REPOS = {
    "backend": "artifact-keeper/artifact-keeper",
    "web": "artifact-keeper/artifact-keeper-web",
}

# Value files that pin real release tags. Files that intentionally pin a
# floating tag (values-staging.yaml, values-mesh-*.yaml) or leave the tag to the
# caller (values-smoke.yaml) are not listed; any non-release tag is skipped
# anyway by is_release_tag() below, so adding one here is harmless.
PINNED_VALUE_FILES = ("values.yaml", "values-production.yaml")

RELEASE_TAG_RE = re.compile(r"^\d+\.\d+\.\d+$")


def is_release_tag(tag: str) -> bool:
    """True for a plain X.Y.Z pin; False for "dev", "", or a prerelease."""
    return bool(RELEASE_TAG_RE.match(tag))


def http_get_json(url: str, retries: int = 3):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "artifact-keeper-iac-drift-check",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
            last_err = err
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed after {retries} attempts: {last_err}")


def latest_release_tag(repo: str) -> str:
    """Latest non-prerelease, non-draft release of `repo`, without the leading v.

    The image tag scheme drops the `v` that the git tag carries (`1.7.1`, not
    `v1.7.1`), so strip it here.
    """
    data = http_get_json(f"https://api.github.com/repos/{repo}/releases/latest")
    tag = (data.get("tag_name") or "").strip()
    if not tag:
        raise RuntimeError(f"{repo}: latest release has no tag_name")
    return tag[1:] if tag.startswith("v") else tag


def read_yaml(path: str):
    try:
        import yaml
    except ImportError:
        sys.exit("PyYAML is required: pip install pyyaml")
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chart-dir", default="charts/artifact-keeper")
    args = parser.parse_args()

    # Resolve every expected tag up front so an API outage degrades to a single
    # warning rather than a per-component mess.
    latest: dict[str, str] = {}
    try:
        for component, repo in COMPONENT_REPOS.items():
            latest[component] = latest_release_tag(repo)
    except RuntimeError as err:
        print(f"::warning::could not determine latest releases, skipping drift check: {err}")
        return 0

    for component, tag in sorted(latest.items()):
        print(f"latest published {component} release: {tag}")
    print()

    drift: list[str] = []

    # 1. Image tag pins in the values files.
    for filename in PINNED_VALUE_FILES:
        path = os.path.join(args.chart_dir, filename)
        if not os.path.exists(path):
            continue
        values = read_yaml(path)
        for component, expected in latest.items():
            pinned = ((values.get(component) or {}).get("image") or {}).get("tag")
            pinned = "" if pinned is None else str(pinned)
            if not is_release_tag(pinned):
                print(f"  - {filename}: {component}.image.tag = {pinned!r} (not a release pin, skipped)")
                continue
            if pinned == expected:
                print(f"  ✓ {filename}: {component}.image.tag = {pinned}")
            else:
                print(f"  ✗ {filename}: {component}.image.tag = {pinned} (latest is {expected})")
                drift.append(f"{filename}: {component}.image.tag is {pinned}, latest published is {expected}")

    # 2. appVersion tracks the backend.
    chart_path = os.path.join(args.chart_dir, "Chart.yaml")
    chart = read_yaml(chart_path)
    app_version = str(chart.get("appVersion", "")).strip()
    expected_app = latest["backend"]
    if not is_release_tag(app_version):
        print(f"  - Chart.yaml: appVersion = {app_version!r} (not a release pin, skipped)")
    elif app_version == expected_app:
        print(f"  ✓ Chart.yaml: appVersion = {app_version}")
    else:
        print(f"  ✗ Chart.yaml: appVersion = {app_version} (backend latest is {expected_app})")
        drift.append(f"Chart.yaml: appVersion is {app_version}, latest published backend is {expected_app}")

    if drift:
        print()
        print("::error::chart image pins have drifted behind the latest published releases")
        for item in drift:
            print(f"  - {item}")
        print()
        print("Repoint the pins above, or add the 'image-drift-ack' label to this PR")
        print("if the chart is intentionally held back this cycle.")
        return 1

    print()
    print("All chart image pins track their component's latest published release.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
