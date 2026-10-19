"""Offline Helm render tests for additional backend volumes and mounts (#305)."""

import os
from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM", "helm")


def render(backend=None, **overrides):
    values = {"secrets": {"existingSecret": "volume-render-test"}, **overrides}
    if backend is not None:
        values["backend"] = backend
    result = subprocess.run(
        [HELM, "template", "ak", str(CHART), "-f", "-"],
        input=yaml.safe_dump(values), capture_output=True, text=True,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    deployment = next(
        doc for doc in docs
        if doc["kind"] == "Deployment"
        and doc["metadata"]["labels"].get("app.kubernetes.io/component") == "backend"
    )
    pod = deployment["spec"]["template"]["spec"]
    container = next(c for c in pod["containers"] if c["name"] == "backend")
    return pod, container


class BackendExtraVolumesTests(unittest.TestCase):
    def test_empty_and_omitted_values_preserve_builtin_volumes(self):
        pod, container = render()
        self.assertIn("storage", {v["name"] for v in pod["volumes"]})
        for value in ([], None):
            with self.subTest(value=value):
                actual_pod, actual_container = render({
                    "extraVolumes": value, "extraVolumeMounts": value,
                })
                self.assertEqual(actual_pod["volumes"], pod["volumes"])
                self.assertEqual(actual_container["volumeMounts"], container["volumeMounts"])

    def test_volume_sources_and_mount_fields_are_preserved(self):
        volumes = [
            {"name": "custom-ca", "configMap": {
                "name": "backend-custom-ca", "defaultMode": 292,
                "items": [{"key": "ca.pem", "path": "ca.pem"}],
            }},
            {"name": "credentials", "secret": {
                "secretName": "backend-credentials", "optional": True,
            }},
            {"name": "projected-config", "projected": {"sources": [
                {"configMap": {"name": "backend-config"}},
                {"secret": {"name": "backend-extra-config"}},
            ]}},
            {"name": "scratch", "emptyDir": {"medium": "Memory", "sizeLimit": "16Mi"}},
        ]
        mounts = [
            {"name": "custom-ca", "mountPath": "/etc/custom-ca", "readOnly": True},
            {"name": "credentials", "mountPath": "/etc/backend-key", "subPath": "key", "readOnly": True},
            {"name": "projected-config", "mountPath": "/etc/backend-config", "readOnly": True},
            {"name": "scratch", "mountPath": "/var/backend-scratch", "readOnly": False},
        ]
        baseline_pod, baseline_container = render()
        pod, container = render({"extraVolumes": volumes, "extraVolumeMounts": mounts})
        self.assertEqual(pod["volumes"], baseline_pod["volumes"] + volumes)
        self.assertEqual(container["volumeMounts"], baseline_container["volumeMounts"] + mounts)
        self.assertEqual(pod.get("initContainers"), baseline_pod.get("initContainers"))

    def test_lists_can_be_used_independently(self):
        baseline_pod, baseline_container = render()
        mounts = [{"name": "tmp", "mountPath": "/var/custom-tmp"}]
        pod, container = render({"extraVolumeMounts": mounts})
        self.assertEqual(pod["volumes"], baseline_pod["volumes"])
        self.assertEqual(container["volumeMounts"], baseline_container["volumeMounts"] + mounts)

        volumes = [{"name": "extra-config", "configMap": {"name": "backend-config"}}]
        pod, container = render({"extraVolumes": volumes})
        self.assertEqual(pod["volumes"], baseline_pod["volumes"] + volumes)
        self.assertEqual(container["volumeMounts"], baseline_container["volumeMounts"])

    def test_optional_builtin_volumes_remain_intact(self):
        volumes = [{"name": "extra-config", "configMap": {"name": "backend-config"}}]
        mounts = [{"name": "extra-config", "mountPath": "/etc/backend-config", "readOnly": True}]
        for enabled in (False, True):
            with self.subTest(optional_volumes=enabled):
                backend = {"scanWorkspace": {"enabled": enabled}}
                overrides = {"trivy": {"enabled": enabled}, "dependencyTrack": {"enabled": enabled}}
                baseline_pod, baseline_container = render(backend, **overrides)
                pod, container = render({
                    **backend, "extraVolumes": volumes, "extraVolumeMounts": mounts,
                }, **overrides)
                self.assertEqual(pod["volumes"], baseline_pod["volumes"] + volumes)
                self.assertEqual(container["volumeMounts"], baseline_container["volumeMounts"] + mounts)


if __name__ == "__main__":
    unittest.main()
