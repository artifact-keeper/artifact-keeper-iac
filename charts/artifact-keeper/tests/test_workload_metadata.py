"""Offline Helm render tests for workload annotations (#334, #344) and
backend env uniqueness (#381)."""

import collections
import os
from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM", "helm")

WORKLOADS = {
    # values key -> (kind, component label)
    "backend": ("Deployment", "backend"),
    "web": ("Deployment", "web"),
    "dependencyTrack": ("Deployment", "dependency-track"),
    "postgres": ("StatefulSet", "postgres"),
}


def render(**overrides):
    values = {"secrets": {"existingSecret": "metadata-render-test"}, **overrides}
    result = subprocess.run(
        [HELM, "template", "ak", str(CHART), "-f", "-"],
        input=yaml.safe_dump(values), capture_output=True, text=True,
    )
    return result, [d for d in yaml.safe_load_all(result.stdout) if d] if not result.returncode else []


def workload(docs, kind, component):
    return next(
        d for d in docs
        if d["kind"] == kind
        and d["metadata"]["labels"].get("app.kubernetes.io/component") == component
    )


def backend_env(docs):
    pod = workload(docs, "Deployment", "backend")["spec"]["template"]["spec"]
    container = next(c for c in pod["containers"] if c["name"] == "backend")
    return container.get("env", [])


class WorkloadAnnotationsTests(unittest.TestCase):
    def test_defaults_render_no_annotations(self):
        result, docs = render()
        self.assertEqual(result.returncode, 0, result.stderr)
        for key, (kind, component) in WORKLOADS.items():
            with self.subTest(workload=key):
                doc = workload(docs, kind, component)
                self.assertNotIn("annotations", doc["metadata"])
                self.assertNotIn("annotations", doc["spec"]["template"]["metadata"])

    def test_annotations_land_on_metadata_and_pod_template(self):
        overrides = {
            key: {
                "annotations": {"reloader.stakater.com/auto": "true"},
                "podAnnotations": {
                    "cluster-autoscaler.kubernetes.io/safe-to-evict": "false",
                    "example.com/note": "x",
                },
            }
            for key in WORKLOADS
        }
        result, docs = render(**overrides)
        self.assertEqual(result.returncode, 0, result.stderr)
        for key, (kind, component) in WORKLOADS.items():
            with self.subTest(workload=key):
                doc = workload(docs, kind, component)
                self.assertEqual(doc["metadata"]["annotations"],
                                 {"reloader.stakater.com/auto": "true"})
                self.assertEqual(
                    doc["spec"]["template"]["metadata"]["annotations"],
                    {"cluster-autoscaler.kubernetes.io/safe-to-evict": "false",
                     "example.com/note": "x"})
                # Selector labels are untouched by the new blocks.
                self.assertEqual(doc["spec"]["selector"]["matchLabels"]["app.kubernetes.io/component"],
                                 component)


class BackendEnvUniquenessTests(unittest.TestCase):
    def assert_unique_env(self, docs):
        names = [e["name"] for e in backend_env(docs)]
        dupes = [n for n, c in collections.Counter(names).items() if c > 1]
        self.assertEqual(dupes, [], f"duplicate backend env names: {dupes}")

    def test_default_and_metrics_listener_render_unique_env(self):
        for overrides in (
            {},
            {"backend": {"metricsListener": {"enabled": True}}},
            {"backend": {"metricsListener": {"enabled": True, "bindIP": "0.0.0.0"},
                         "env": {"METRICS_BIND_IP": "127.0.0.1"}}},
            {"backend": {"clientIp": {"trustedProxyCidrs": "10.0.0.0/8"},
                         "env": {"RATE_LIMIT_TRUSTED_PROXY_CIDRS": "10.1.0.0/16"}}},
        ):
            with self.subTest(overrides=overrides):
                result, docs = render(**overrides)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_unique_env(docs)

    def test_matching_env_metrics_port_renders_once(self):
        result, docs = render(backend={
            "metricsListener": {"enabled": True, "port": 9100},
            "env": {"METRICS_PORT": 9100},
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_unique_env(docs)
        ports = [e["value"] for e in backend_env(docs) if e["name"] == "METRICS_PORT"]
        self.assertEqual(ports, ["9100"])

    def test_conflicting_env_metrics_port_fails_render(self):
        result, _ = render(backend={
            "metricsListener": {"enabled": True, "port": 9091},
            "env": {"METRICS_PORT": "9100"},
        })
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("backend.env.METRICS_PORT (9100) conflicts with backend.metricsListener.port (9091)",
                      result.stderr)


if __name__ == "__main__":
    unittest.main()
