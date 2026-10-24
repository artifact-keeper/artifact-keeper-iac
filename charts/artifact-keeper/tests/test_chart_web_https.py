"""Render regressions for web HTTPS headers (#392)."""
import os
from pathlib import Path
import subprocess
import unittest

import yaml

CHART = Path(__file__).resolve().parents[1]


def render(values):
    return subprocess.run(
        [os.environ.get("HELM", "helm"), "template", "ak", str(CHART),
         "--set", "secrets.existingSecret=render-test", "-f", "-"],
        input=yaml.safe_dump(values), text=True, capture_output=True,
    )


class WebHttpsTests(unittest.TestCase):
    def test_explicit_opt_in_is_web_only(self):
        result = render({"web": {"enforceHttps": True}})
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = []
        for doc in yaml.safe_load_all(result.stdout):
            if doc and doc["kind"] == "Deployment":
                for container in doc["spec"]["template"]["spec"]["containers"]:
                    for env in container.get("env", []):
                        if env["name"] == "AK_ENFORCE_HTTPS":
                            seen.append((container["name"], env["value"]))
        self.assertEqual(seen, [("web", "true")])

    def test_defaults_and_false_preserve_plain_http(self):
        for values in ({}, {"web": {"enforceHttps": False}},
                       {"ingress": {"enabled": True}}):
            with self.subTest(values=values):
                result = render(values)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("name: AK_ENFORCE_HTTPS", result.stdout)

    def test_string_false_is_rejected(self):
        result = render({"web": {"enforceHttps": "false"}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("web.enforceHttps must be a boolean", result.stderr)

    def test_disabled_web_does_not_render_headers(self):
        result = render({"web": {"enabled": False, "enforceHttps": True}})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("name: AK_ENFORCE_HTTPS", result.stdout)
