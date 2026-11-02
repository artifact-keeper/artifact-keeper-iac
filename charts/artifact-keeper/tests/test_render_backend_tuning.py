"""Offline Helm render tests for backend.logging (#387) and backend.stuckScan (#101)."""

import os
from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM", "helm")
NAMES = (
    "LOG_FORMAT", "LOG_ANSI",
    "STUCK_SCAN_THRESHOLD_SECS", "STUCK_SCAN_CHECK_INTERVAL_SECS",
)


def run(values, *args):
    values = {"secrets": {"existingSecret": "tuning-render-test"}, **values}
    return subprocess.run(
        [HELM, "template", "ak", str(CHART), "-f", "-", *args],
        input=yaml.safe_dump(values), capture_output=True, text=True,
    )


def backend_env(values, *args):
    """Return ({name: value}, [names]) for the backend container."""
    result = run(values, *args)
    if result.returncode:
        raise AssertionError(result.stderr)
    deployment = next(
        doc for doc in yaml.safe_load_all(result.stdout)
        if doc and doc["kind"] == "Deployment"
        and doc["metadata"]["labels"].get("app.kubernetes.io/component") == "backend"
    )
    container = next(
        c for c in deployment["spec"]["template"]["spec"]["containers"]
        if c["name"] == "backend"
    )
    env = container["env"]
    return {e["name"]: e.get("value", e.get("valueFrom")) for e in env}, [e["name"] for e in env]


class BackendTuningRenderTests(unittest.TestCase):
    def assert_fails(self, values, message, *args):
        result = run(values, *args)
        self.assertNotEqual(result.returncode, 0, result.stdout[:200])
        self.assertIn(message, result.stderr)

    def test_defaults_render_nothing(self):
        explicit = {"backend": {
            "logging": {"format": "text", "ansi": "auto"},
            "stuckScan": {"thresholdSecs": None, "checkIntervalSecs": None},
        }}
        for values in ({}, explicit):
            with self.subTest(values=values):
                env, _ = backend_env(values)
                for name in NAMES:
                    self.assertNotIn(name, env)

    def test_non_default_values_render_once(self):
        env, names = backend_env({"backend": {
            "logging": {"format": "json", "ansi": "false"},
            "stuckScan": {"thresholdSecs": 900, "checkIntervalSecs": "120"},
        }})
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(env["LOG_FORMAT"], "json")
        self.assertEqual(env["LOG_ANSI"], "false")
        self.assertEqual(env["STUCK_SCAN_THRESHOLD_SECS"], "900")
        self.assertEqual(env["STUCK_SCAN_CHECK_INTERVAL_SECS"], "120")

    def test_ansi_accepts_yaml_and_set_booleans(self):
        for value in (True, False):
            with self.subTest(value=value):
                env, _ = backend_env({"backend": {"logging": {"ansi": value}}})
                self.assertEqual(env["LOG_ANSI"], str(value).lower())
        env, _ = backend_env({}, "--set", "backend.logging.ansi=true")
        self.assertEqual(env["LOG_ANSI"], "true")

    def test_large_and_set_integers_render_as_plain_digits(self):
        env, _ = backend_env({"backend": {"stuckScan": {"thresholdSecs": 1000000}}})
        self.assertEqual(env["STUCK_SCAN_THRESHOLD_SECS"], "1000000")
        env, _ = backend_env({}, "--set", "backend.stuckScan.checkIntervalSecs=45")
        self.assertEqual(env["STUCK_SCAN_CHECK_INTERVAL_SECS"], "45")

    def test_invalid_values_fail(self):
        cases = [
            ({"logging": {"format": "pretty"}}, "backend.logging.format must be"),
            ({"logging": {"format": "JSON"}}, "backend.logging.format must be"),
            ({"logging": {"format": ""}}, "backend.logging.format must be"),
            ({"logging": {"format": True}}, "backend.logging.format must be"),
            ({"logging": {"ansi": "yes"}}, "backend.logging.ansi must be"),
            ({"logging": {"ansi": 1}}, "backend.logging.ansi must be"),
            ({"logging": "json"}, "backend.logging must be a map"),
            ({"stuckScan": []}, "backend.stuckScan must be a map"),
        ]
        for key in ("thresholdSecs", "checkIntervalSecs"):
            for bad in (0, -5, 1.5, "0", "10m", "", "012", True):
                cases.append((
                    {"stuckScan": {key: bad}},
                    f"backend.stuckScan.{key} must be a positive integer",
                ))
        for backend, message in cases:
            with self.subTest(backend=backend):
                self.assert_fails({"backend": backend}, message)

    def test_backend_env_entry_wins_over_default_and_must_match_otherwise(self):
        manual = {"LOG_FORMAT": "json", "LOG_ANSI": "true",
                  "STUCK_SCAN_THRESHOLD_SECS": "300", "STUCK_SCAN_CHECK_INTERVAL_SECS": "60"}
        env, names = backend_env({"backend": {"env": manual}})
        self.assertEqual(len(names), len(set(names)))
        for name, value in manual.items():
            self.assertEqual(env[name], value)
        env, names = backend_env({"backend": {
            "env": manual,
            "logging": {"format": "json", "ansi": True},
            "stuckScan": {"thresholdSecs": 300, "checkIntervalSecs": 60},
        }})
        self.assertEqual(len(names), len(set(names)))
        for name, value in manual.items():
            self.assertEqual(env[name], value)
        conflicts = [
            ({"logging": {"format": "json"}}, "LOG_FORMAT", "text"),
            ({"logging": {"ansi": "false"}}, "LOG_ANSI", "true"),
            ({"stuckScan": {"thresholdSecs": 900}}, "STUCK_SCAN_THRESHOLD_SECS", "1800"),
            ({"stuckScan": {"checkIntervalSecs": 900}}, "STUCK_SCAN_CHECK_INTERVAL_SECS", "600"),
        ]
        for backend, name, value in conflicts:
            with self.subTest(name=name):
                self.assert_fails(
                    {"backend": {**backend, "env": {name: value}}},
                    f"backend.env.{name} ({value}) conflicts with",
                )

    def test_environment_secrets_conflict_with_chart_value(self):
        self.assert_fails({"backend": {
            "logging": {"format": "json"},
            "environmentSecrets": [{
                "name": "LOG_FORMAT",
                "secretKeyRef": {"name": "logging", "key": "format"},
            }],
        }}, "LOG_FORMAT is set by backend.logging.format and also by backend.environmentSecrets")


if __name__ == "__main__":
    unittest.main()
