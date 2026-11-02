"""Render tests for the fleet-mode sizing presets."""

from pathlib import Path
import os
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
FLEET = {"fleet": {"enabled": True, "instanceId": "preset-test",
                   "externalDatabaseBootstrap": {"enabled": False}}}


def render(values):
    result = subprocess.run(
        [os.environ.get("HELM", "helm"), "template", "ak", str(CHART),
         "--set", "secrets.existingSecret=render-test", "-f", "-"],
        input=yaml.safe_dump(values), capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return [d for d in yaml.safe_load_all(result.stdout) if d]


def resources(docs, component):
    deploy = next(d for d in docs if d["kind"] == "Deployment"
                  and d["metadata"]["name"].endswith("-" + component))
    container = next(c for c in deploy["spec"]["template"]["spec"]["containers"]
                     if c["name"] == component)
    return container["resources"]


class FleetPresetTests(unittest.TestCase):
    """#350: fleet backends get the same ephemeral-storage headroom as #116."""

    EXPECTED = {
        # preset: (backend request, web limit) -- unchanged by #350
        "small": ("256Mi", "1Gi"),
        "medium": ("512Mi", "2Gi"),
        "large": ("1Gi", "2Gi"),
    }

    def test_backend_ephemeral_limit_matches_non_fleet_default(self):
        default_limit = resources(render({}), "backend")["limits"]["ephemeral-storage"]
        self.assertEqual(default_limit, "16Gi")
        for preset, (backend_request, web_limit) in self.EXPECTED.items():
            with self.subTest(preset=preset):
                docs = render({"fleet": {**FLEET["fleet"], "preset": preset}})
                backend = resources(docs, "backend")
                self.assertEqual(backend["limits"]["ephemeral-storage"], default_limit)
                self.assertEqual(backend["requests"]["ephemeral-storage"], backend_request)
                self.assertEqual(resources(docs, "web")["limits"]["ephemeral-storage"], web_limit)

    def test_empty_preset_is_small(self):
        self.assertEqual(resources(render(FLEET), "backend"),
                         resources(render({"fleet": {**FLEET["fleet"], "preset": "small"}}), "backend"))


if __name__ == "__main__":
    unittest.main()
