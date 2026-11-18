"""Offline Helm render tests for backend probe configuration (#448)."""

import os
from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM", "helm")
PROBES = ("startupProbe", "livenessProbe", "readinessProbe")


def run(values, *args):
    values = {"secrets": {"existingSecret": "probe-render-test"}, **values}
    return subprocess.run(
        [HELM, "template", "ak", str(CHART), "-f", "-", *args],
        input=yaml.safe_dump(values), capture_output=True, text=True,
    )


def backend_container(values, *args):
    result = run(values, *args)
    if result.returncode:
        raise AssertionError(result.stderr)
    deployment = next(
        doc for doc in yaml.safe_load_all(result.stdout)
        if doc and doc["kind"] == "Deployment"
        and doc["metadata"]["labels"].get("app.kubernetes.io/component") == "backend"
    )
    return next(
        c for c in deployment["spec"]["template"]["spec"]["containers"]
        if c["name"] == "backend"
    )


class BackendProbeRenderTests(unittest.TestCase):
    def assert_fails(self, values, message, *args):
        result = run(values, *args)
        self.assertNotEqual(result.returncode, 0, result.stdout[:200])
        self.assertIn(message, result.stderr)

    def test_defaults_preserve_existing_probes_without_enabled_key(self):
        c = backend_container({})
        self.assertEqual(c["startupProbe"], {
            "httpGet": {"path": "/readyz", "port": "http"},
            "periodSeconds": 5,
            "timeoutSeconds": 5,
            "failureThreshold": 30,
        })
        self.assertEqual(c["livenessProbe"], {
            "httpGet": {"path": "/livez", "port": "http"},
            "periodSeconds": 15,
            "timeoutSeconds": 5,
            "failureThreshold": 5,
        })
        self.assertEqual(c["readinessProbe"], {
            "httpGet": {"path": "/readyz", "port": "http"},
            "periodSeconds": 10,
            "timeoutSeconds": 5,
            "failureThreshold": 5,
        })
        for name in PROBES:
            self.assertNotIn("enabled", c[name])

    def test_partial_startup_probe_override_merges_with_defaults(self):
        c = backend_container({"backend": {"startupProbe": {"failureThreshold": 360}}})
        self.assertEqual(c["startupProbe"], {
            "httpGet": {"path": "/readyz", "port": "http"},
            "periodSeconds": 5,
            "timeoutSeconds": 5,
            "failureThreshold": 360,
        })

    def test_reuse_values_missing_probe_keys_keep_defaults(self):
        c = backend_container({"backend": {
            "startupProbe": None,
            "livenessProbe": None,
            "readinessProbe": None,
        }})
        self.assertEqual(c["startupProbe"]["failureThreshold"], 30)
        self.assertEqual(c["livenessProbe"]["httpGet"]["path"], "/livez")
        self.assertEqual(c["readinessProbe"]["httpGet"]["path"], "/readyz")

    def test_disabled_probe_is_omitted(self):
        c = backend_container({"backend": {"startupProbe": {"enabled": False}}})
        self.assertNotIn("startupProbe", c)
        self.assertIn("livenessProbe", c)
        self.assertIn("readinessProbe", c)

    def test_handler_replacement_clears_default_http_get(self):
        c = backend_container({"backend": {
            "livenessProbe": {"httpGet": None, "tcpSocket": {"port": "http"}},
        }})
        self.assertNotIn("httpGet", c["livenessProbe"])
        self.assertEqual(c["livenessProbe"]["tcpSocket"], {"port": "http"})
        self.assertEqual(c["livenessProbe"]["periodSeconds"], 15)

    def test_invalid_probe_values_fail(self):
        for name in PROBES:
            with self.subTest(probe=name):
                self.assert_fails(
                    {"backend": {name: "bad"}},
                    f"backend.{name} must be a map",
                )
                self.assert_fails(
                    {"backend": {name: {"enabled": "false"}}},
                    f"backend.{name}.enabled must be a boolean",
                )


if __name__ == "__main__":
    unittest.main()
