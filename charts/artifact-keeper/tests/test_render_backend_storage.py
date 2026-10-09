"""Render tests for backend storage volume modes."""

from pathlib import Path
import os
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
CHART = ROOT / "charts/artifact-keeper"


def render(values=None):
    return subprocess.run(
        [
            os.environ.get("HELM", "helm"),
            "template",
            "storage-test",
            str(CHART),
            "--set",
            "secrets.existingSecret=render-test",
            "-f",
            "-",
        ],
        input=yaml.safe_dump(values or {}),
        capture_output=True,
        text=True,
        check=False,
    )


def deployment(result):
    if result.returncode:
        raise AssertionError(result.stderr)
    documents = [document for document in yaml.safe_load_all(result.stdout) if document]
    return next(
        document
        for document in documents
        if document["kind"] == "Deployment"
        and document["metadata"]["name"].endswith("-backend")
    )


def storage_volume(result):
    volumes = deployment(result)["spec"]["template"]["spec"]["volumes"]
    return next(volume for volume in volumes if volume["name"] == "storage")


class BackendStorageTests(unittest.TestCase):
    def test_persistent_volume_is_default(self):
        volume = storage_volume(render())
        self.assertEqual(
            volume["persistentVolumeClaim"]["claimName"],
            "storage-test-artifact-keeper-storage",
        )

    def test_empty_dir_size_limit_is_configurable(self):
        volume = storage_volume(
            render(
                {
                    "backend": {
                        "persistence": {
                            "enabled": False,
                            "emptyDir": {"sizeLimit": "24Gi"},
                        }
                    }
                }
            )
        )
        self.assertEqual(volume["emptyDir"]["sizeLimit"], "24Gi")

    def test_generic_ephemeral_volume_claim_template(self):
        volume = storage_volume(
            render(
                {
                    "backend": {
                        "persistence": {
                            "enabled": False,
                            "ephemeral": {
                                "enabled": True,
                                "size": "20Gi",
                                "storageClass": "managed-csi",
                                "accessModes": ["ReadWriteOnce"],
                            },
                        }
                    }
                }
            )
        )
        claim = volume["ephemeral"]["volumeClaimTemplate"]["spec"]
        self.assertEqual(claim["accessModes"], ["ReadWriteOnce"])
        self.assertEqual(claim["resources"]["requests"]["storage"], "20Gi")
        self.assertEqual(claim["storageClassName"], "managed-csi")

    def test_persistent_and_ephemeral_modes_are_mutually_exclusive(self):
        result = render(
            {
                "backend": {
                    "persistence": {
                        "enabled": True,
                        "ephemeral": {"enabled": True},
                    }
                }
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "backend.persistence.enabled and "
            "backend.persistence.ephemeral.enabled cannot both be true",
            result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
