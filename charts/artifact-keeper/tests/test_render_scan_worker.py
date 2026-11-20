"""Offline Helm render tests for the opt-in scan-worker Deployment."""

import collections
import os
from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM", "helm")


def helm(values):
    values = {"secrets": {"existingSecret": "scan-worker-render-test"}, **values}
    return subprocess.run(
        [HELM, "template", "ak", str(CHART), "-f", "-"],
        input=yaml.safe_dump(values), capture_output=True, text=True,
    )


def render(values):
    result = helm(values)
    if result.returncode:
        raise AssertionError(result.stderr)
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    return {
        doc["metadata"]["labels"].get("app.kubernetes.io/component"): doc
        for doc in docs if doc["kind"] == "Deployment"
    }


def container(deployment):
    return deployment["spec"]["template"]["spec"]["containers"][0]


def env(deployment):
    return {e["name"]: e.get("value") for e in container(deployment)["env"]}


def env_names(deployment):
    return [e["name"] for e in container(deployment)["env"]]


ON_S3 = {
    "scanWorker": {"enabled": True},
    "backend": {"env": {"STORAGE_BACKEND": "s3"}},
}


class ScanWorkerTests(unittest.TestCase):
    def test_disabled_by_default_and_backend_has_no_scan_env(self):
        deployments = render({})
        self.assertNotIn("scan-worker", deployments)
        names = env_names(deployments["backend"])
        self.assertNotIn("SCAN_QUEUE_ENABLED", names)
        self.assertNotIn("SCAN_WORKER_ENABLED", names)

    def test_enabled_splits_api_pods_from_the_worker(self):
        deployments = render(ON_S3)
        backend, worker = env(deployments["backend"]), env(deployments["scan-worker"])
        self.assertEqual(backend["SCAN_QUEUE_ENABLED"], "true")
        self.assertEqual(backend["SCAN_WORKER_ENABLED"], "false")
        self.assertEqual(worker["SCAN_QUEUE_ENABLED"], "true")
        self.assertEqual(worker["SCAN_WORKER_ENABLED"], "true")
        self.assertEqual(worker["SCAN_WORKER_CONCURRENCY"], "8")

    def test_worker_shares_the_backend_env(self):
        deployments = render(ON_S3)
        backend, worker = env(deployments["backend"]), env(deployments["scan-worker"])
        for name in ("STORAGE_BACKEND", "DATABASE_URL"):
            self.assertIn(name, worker)
        self.assertEqual(worker["STORAGE_BACKEND"], backend["STORAGE_BACKEND"])

    def test_refuses_storage_the_worker_cannot_read(self):
        result = helm({"scanWorker": {"enabled": True}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("scanWorker.enabled needs the worker pods", result.stderr)

    def test_worker_env_overrides_backend_env_without_duplicates(self):
        deployments = render({
            "scanWorker": {"enabled": True, "env": {
                "MAX_CONCURRENT_SCAN_EXTRACTIONS": "16",
                "DATABASE_MAX_CONNECTIONS": "40",
            }},
            "backend": {"env": {
                "STORAGE_BACKEND": "s3",
                "MAX_CONCURRENT_SCAN_EXTRACTIONS": "4",
                "DATABASE_MAX_CONNECTIONS": "300",
                "SCAN_QUEUE_ENABLED": "true",
            }},
        })
        for component in ("backend", "scan-worker"):
            with self.subTest(component=component):
                counts = collections.Counter(env_names(deployments[component]))
                self.assertEqual([n for n, c in counts.items() if c > 1], [])
        backend, worker = env(deployments["backend"]), env(deployments["scan-worker"])
        self.assertEqual(backend["MAX_CONCURRENT_SCAN_EXTRACTIONS"], "4")
        self.assertEqual(backend["DATABASE_MAX_CONNECTIONS"], "300")
        self.assertEqual(worker["MAX_CONCURRENT_SCAN_EXTRACTIONS"], "16")
        self.assertEqual(worker["DATABASE_MAX_CONNECTIONS"], "40")

    def test_liveness_tolerates_a_busy_worker(self):
        probe = container(render(ON_S3)["scan-worker"])["livenessProbe"]
        self.assertGreaterEqual(probe["timeoutSeconds"], 5)


if __name__ == "__main__":
    unittest.main()
