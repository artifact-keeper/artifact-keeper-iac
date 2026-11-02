"""Offline Helm render tests for httpRoute.timeouts (#358)."""

import copy
import os
from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM", "helm")
ENABLED = {
    "secrets": {"existingSecret": "timeouts-render-test"},
    "ingress": {"enabled": False},
    "networkPolicy": {"enabled": False},
    "httpRoute": {
        "enabled": True,
        "parentRefs": [{"name": "shared-gateway"}],
        "hostnames": ["registry.example.com"],
    },
}


def run(timeouts=None, extra=None, *args):
    values = copy.deepcopy(ENABLED)
    if timeouts is not None:
        values["httpRoute"]["timeouts"] = timeouts
    for key, value in (extra or {}).items():
        if isinstance(value, dict):
            values.setdefault(key, {}).update(value)
        else:
            values[key] = value
    return subprocess.run(
        [HELM, "template", "ak", str(CHART), "-f", "-", *args],
        input=yaml.safe_dump(values), capture_output=True, text=True,
    )


def route(timeouts=None, extra=None):
    result = run(timeouts, extra)
    if result.returncode:
        raise AssertionError(result.stderr)
    return next(
        doc for doc in yaml.safe_load_all(result.stdout)
        if doc and doc["kind"] == "HTTPRoute"
    )


def rule_target(rule):
    return rule["backendRefs"][0]["name"].rsplit("-", 1)[-1]


class HTTPRouteTimeoutTests(unittest.TestCase):
    def assert_fails(self, timeouts, message, *args):
        result = run(timeouts, None, *args)
        self.assertNotEqual(result.returncode, 0, result.stdout[:200])
        self.assertIn(message, result.stderr)

    def test_default_and_empty_values_render_no_timeouts(self):
        for timeouts in (None, {}, {"request": "", "backendRequest": ""}):
            with self.subTest(timeouts=timeouts):
                for rule in route(timeouts)["spec"]["rules"]:
                    self.assertNotIn("timeouts", rule)

    def test_timeouts_apply_only_to_backend_rules(self):
        cases = (
            ({"request": "0s"}, {"request": "0s"}),
            ({"backendRequest": "300s"}, {"backendRequest": "300s"}),
            (
                {"request": "1h", "backendRequest": "30m"},
                {"request": "1h", "backendRequest": "30m"},
            ),
            ({"request": "0s", "backendRequest": "2h"}, {"request": "0s", "backendRequest": "2h"}),
        )
        extra = {
            "dependencyTrack": {"enabled": True},
            "httpRoute": {"dtrack": {"enabled": True}},
        }
        for timeouts, expected in cases:
            with self.subTest(timeouts=timeouts):
                rules = route(timeouts, extra)["spec"]["rules"]
                targets = [rule_target(rule) for rule in rules]
                self.assertEqual(targets.count("web"), 1)
                self.assertEqual(targets.count("dtrack"), 1)
                for rule in rules:
                    if rule_target(rule) == "backend":
                        self.assertEqual(rule["timeouts"], expected)
                    else:
                        self.assertNotIn("timeouts", rule)

    def test_compound_durations_are_accepted(self):
        for value in ("1h30m", "500ms", "99999s", "1h2m3s4ms", "0s"):
            with self.subTest(value=value):
                rules = route({"request": value})["spec"]["rules"]
                self.assertEqual(rules[0]["timeouts"], {"request": value})

    def test_invalid_durations_fail(self):
        bad = ("300", "5x", "1.5s", "-1s", "100000s", "1h1m1s1ms1h", " 30s", "30S", "1d")
        for field in ("request", "backendRequest"):
            for value in bad:
                with self.subTest(field=field, value=value):
                    # The schema rejects these first; the template check covers
                    # installs that skip schema validation.
                    self.assert_fails({field: value}, "timeouts")
                    self.assert_fails(
                        {field: value}, f"httpRoute.timeouts.{field} must be a Gateway API duration",
                        "--skip-schema-validation",
                    )
            with self.subTest(field=field, value=300):
                self.assert_fails(
                    {field: 300}, f"httpRoute.timeouts.{field} must be a Gateway API duration string",
                    "--skip-schema-validation",
                )
        self.assert_fails({"idle": "10s"}, "idle")

    def test_backend_request_cannot_exceed_request(self):
        for request, backend in (("5m", "10m"), ("1h", "61m"), ("1s", "1001ms")):
            with self.subTest(request=request, backend=backend):
                self.assert_fails(
                    {"request": request, "backendRequest": backend},
                    "cannot be longer than httpRoute.timeouts.request",
                )
        rules = route({"request": "1h30m", "backendRequest": "90m"})["spec"]["rules"]
        self.assertEqual(rules[0]["timeouts"], {"request": "1h30m", "backendRequest": "90m"})

    def test_timeouts_ignored_when_httproute_disabled(self):
        result = subprocess.run(
            [HELM, "template", "ak", str(CHART), "-f", "-"],
            input=yaml.safe_dump({
                "secrets": {"existingSecret": "timeouts-render-test"},
                "httpRoute": {"timeouts": {"request": "5m", "backendRequest": "10m"}},
            }),
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("kind: HTTPRoute", result.stdout)


if __name__ == "__main__":
    unittest.main()
