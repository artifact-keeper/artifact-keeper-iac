"""Render tests for the scanner-adapter Service session affinity (#429)."""

from pathlib import Path
import os
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]


def render(values):
    result = subprocess.run(
        [os.environ.get("HELM", "helm"), "template", "ak", str(CHART), "--namespace", "test",
         "--set", "secrets.existingSecret=render-test", "-f", "-"],
        input=yaml.safe_dump(values), capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return [d for d in yaml.safe_load_all(result.stdout) if d]


def adapter_services(docs):
    return [d for d in docs if d["kind"] == "Service"
            and d["metadata"]["name"] == "ak-artifact-keeper-scanner-adapter"]


class ScannerAdapterServiceTests(unittest.TestCase):
    def test_status_polls_stick_to_the_replica_that_took_the_scan(self):
        (service,) = adapter_services(render({}))
        self.assertEqual(service["spec"]["sessionAffinity"], "ClientIP")

    def test_no_service_when_the_adapter_is_off(self):
        self.assertEqual(adapter_services(render({"scannerAdapter": {"enabled": False}})), [])


if __name__ == "__main__":
    unittest.main()
