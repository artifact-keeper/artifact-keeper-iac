"""Render tests for existingClaim and PVC annotations on chart-managed volumes."""

from pathlib import Path
import os
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
CHART = ROOT / "charts/artifact-keeper"
PREFIX = "claims-test-artifact-keeper"


def render(values=None):
    return subprocess.run(
        [
            os.environ.get("HELM", "helm"),
            "template",
            "claims-test",
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


def documents(values=None):
    result = render(values)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def pvcs(docs):
    return {
        document["metadata"]["name"]: document
        for document in docs
        if document["kind"] == "PersistentVolumeClaim"
    }


def workload(docs, kind, suffix):
    return next(
        document
        for document in docs
        if document["kind"] == kind and document["metadata"]["name"].endswith(suffix)
    )


def claim_for(document, volume_name):
    volumes = document["spec"]["template"]["spec"].get("volumes", [])
    volume = next(volume for volume in volumes if volume["name"] == volume_name)
    return volume["persistentVolumeClaim"]["claimName"]


def mounting_claim(docs, claim_name):
    """(kind, name) of every workload with a volume on claim_name."""
    found = set()
    for document in docs:
        spec = document.get("spec", {})
        if document["kind"] == "CronJob":
            spec = spec["jobTemplate"]["spec"]
        volumes = spec.get("template", {}).get("spec", {}).get("volumes") or []
        for volume in volumes:
            if volume.get("persistentVolumeClaim", {}).get("claimName") == claim_name:
                found.add((document["kind"], document["metadata"]["name"]))
    return found


# component -> (values with existingClaim set, chart PVC name, workload kind,
# workload name suffix, volume name)
CASES = {
    "backend storage": (
        {"backend": {"persistence": {"existingClaim": "my-claim"}}},
        f"{PREFIX}-storage",
        "Deployment",
        "-backend",
        "storage",
    ),
    "backend scan workspace": (
        {"backend": {"scanWorkspace": {"existingClaim": "my-claim"}}},
        f"{PREFIX}-scan-workspace",
        "Deployment",
        "-backend",
        "scan-workspace",
    ),
    "opensearch": (
        {"opensearch": {"persistence": {"existingClaim": "my-claim"}}},
        f"{PREFIX}-opensearch",
        "Deployment",
        "-opensearch",
        "opensearch-data",
    ),
    "trivy": (
        {"trivy": {"persistence": {"existingClaim": "my-claim"}}},
        f"{PREFIX}-trivy-cache",
        "Deployment",
        "-trivy",
        "trivy-cache",
    ),
    "dependency-track": (
        {"dependencyTrack": {"persistence": {"existingClaim": "my-claim"}}},
        f"{PREFIX}-dtrack",
        "Deployment",
        "-dtrack",
        "dtrack-data",
    ),
    "image builder": (
        {
            "imageBuilder": {
                "enabled": True,
                "persistence": {"existingClaim": "my-claim"},
            }
        },
        f"{PREFIX}-buildkitd-cache",
        "Deployment",
        "-buildkitd",
        "cache",
    ),
}


def merge(base, extra):
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


class DefaultRenderTests(unittest.TestCase):
    def test_default_render_keeps_chart_pvcs(self):
        docs = documents({"imageBuilder": {"enabled": True}})
        names = set(pvcs(docs))
        for _, pvc, kind, suffix, volume in CASES.values():
            self.assertIn(pvc, names)
            self.assertEqual(claim_for(workload(docs, kind, suffix), volume), pvc)
        self.assertIn(f"{PREFIX}-shared-config", names)
        postgres = workload(docs, "StatefulSet", "-postgres")
        templates = postgres["spec"]["volumeClaimTemplates"]
        self.assertEqual([t["metadata"]["name"] for t in templates], ["postgres-data"])
        self.assertNotIn("annotations", templates[0]["metadata"])
        for pvc in pvcs(docs).values():
            self.assertNotIn("annotations", pvc["metadata"])


class ExistingClaimTests(unittest.TestCase):
    def test_existing_claim_replaces_chart_pvc(self):
        for component, (values, pvc, kind, suffix, volume) in CASES.items():
            with self.subTest(component=component):
                docs = documents(values)
                self.assertNotIn(pvc, pvcs(docs))
                self.assertEqual(
                    claim_for(workload(docs, kind, suffix), volume), "my-claim"
                )
                # Only the targeted PVC goes away.
                self.assertTrue(pvcs(docs))

    def test_shared_config_existing_claim(self):
        docs = documents({"backend": {"sharedConfig": {"existingClaim": "my-claim"}}})
        self.assertNotIn(f"{PREFIX}-shared-config", pvcs(docs))
        self.assertEqual(
            claim_for(workload(docs, "Deployment", "-backend"), "shared-config"),
            "my-claim",
        )
        mounts = mounting_claim(docs, "my-claim")
        # The backend and the Dependency-Track bootstrap both mount it.
        self.assertGreaterEqual(len(mounts), 2, mounts)
        self.assertEqual(mounting_claim(docs, f"{PREFIX}-shared-config"), set())

    def test_postgres_existing_claim_uses_volume(self):
        docs = documents({"postgres": {"persistence": {"existingClaim": "my-claim"}}})
        postgres = workload(docs, "StatefulSet", "-postgres")
        self.assertNotIn("volumeClaimTemplates", postgres["spec"])
        self.assertEqual(claim_for(postgres, "postgres-data"), "my-claim")
        # The init-db ConfigMap volume is kept alongside the claim.
        names = [v["name"] for v in postgres["spec"]["template"]["spec"]["volumes"]]
        self.assertEqual(names, ["init-db", "postgres-data"])

    def test_postgres_existing_claim_without_init_db(self):
        docs = documents(
            {
                "postgres": {
                    "initDb": {"enabled": False},
                    "persistence": {"existingClaim": "my-claim"},
                }
            }
        )
        postgres = workload(docs, "StatefulSet", "-postgres")
        volumes = postgres["spec"]["template"]["spec"]["volumes"]
        self.assertEqual([v["name"] for v in volumes], ["postgres-data"])

    def test_backend_existing_claim_requires_persistence(self):
        result = render(
            {"backend": {"persistence": {"enabled": False, "existingClaim": "my-claim"}}}
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "backend.persistence.existingClaim requires backend.persistence.enabled=true",
            result.stderr,
        )

    def test_backend_existing_claim_rejects_ephemeral(self):
        for enabled in (True, False):
            with self.subTest(persistence_enabled=enabled):
                result = render(
                    {
                        "backend": {
                            "persistence": {
                                "enabled": enabled,
                                "existingClaim": "my-claim",
                                "ephemeral": {"enabled": True},
                            }
                        }
                    }
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "backend.persistence.existingClaim cannot be combined with "
                    "backend.persistence.ephemeral.enabled",
                    result.stderr,
                )

    def test_existing_claim_requires_component_persistence(self):
        cases = {
            "backend.scanWorkspace.existingClaim requires "
            "backend.scanWorkspace.enabled=true": {
                "backend": {"scanWorkspace": {"enabled": False, "existingClaim": "c"}}
            },
            "opensearch.persistence.existingClaim requires "
            "opensearch.persistence.enabled=true": {
                "opensearch": {"persistence": {"enabled": False, "existingClaim": "c"}}
            },
            "imageBuilder.persistence.existingClaim requires "
            "imageBuilder.persistence.enabled=true": {
                "imageBuilder": {
                    "enabled": True,
                    "persistence": {"enabled": False, "existingClaim": "c"},
                }
            },
        }
        for message, values in cases.items():
            with self.subTest(message=message):
                result = render(values)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_opensearch_existing_claim_rejects_multi_node(self):
        result = render(
            {
                "opensearch": {
                    "replicaCount": 3,
                    "persistence": {"existingClaim": "my-claim"},
                }
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "opensearch.persistence.existingClaim is only supported with "
            "opensearch.replicaCount=1",
            result.stderr,
        )


ANNOTATIONS = {
    "helm.sh/resource-policy": "keep",
    "argocd.argoproj.io/sync-options": "Prune=false",
}


class PvcAnnotationTests(unittest.TestCase):
    def test_annotations_on_chart_pvcs(self):
        values = {
            "backend": {
                "persistence": {"annotations": ANNOTATIONS},
                "scanWorkspace": {"annotations": ANNOTATIONS},
                "sharedConfig": {"annotations": ANNOTATIONS},
            },
            "opensearch": {"persistence": {"annotations": ANNOTATIONS}},
            "trivy": {"persistence": {"annotations": ANNOTATIONS}},
            "dependencyTrack": {"persistence": {"annotations": ANNOTATIONS}},
            "imageBuilder": {
                "enabled": True,
                "persistence": {"annotations": ANNOTATIONS},
            },
            "postgres": {"persistence": {"annotations": ANNOTATIONS}},
        }
        docs = documents(values)
        claims = pvcs(docs)
        expected = [case[1] for case in CASES.values()] + [f"{PREFIX}-shared-config"]
        for name in expected:
            with self.subTest(pvc=name):
                self.assertEqual(claims[name]["metadata"]["annotations"], ANNOTATIONS)
        postgres = workload(docs, "StatefulSet", "-postgres")
        template = postgres["spec"]["volumeClaimTemplates"][0]["metadata"]
        self.assertEqual(template["annotations"], ANNOTATIONS)

    def test_annotations_on_multi_node_opensearch_template(self):
        docs = documents(
            {
                "opensearch": {
                    "replicaCount": 3,
                    "persistence": {"annotations": ANNOTATIONS},
                }
            }
        )
        opensearch = workload(docs, "StatefulSet", "-opensearch")
        template = opensearch["spec"]["volumeClaimTemplates"][0]["metadata"]
        self.assertEqual(template["annotations"], ANNOTATIONS)

    def test_annotations_ignored_with_existing_claim(self):
        values = merge(
            CASES["trivy"][0],
            {"trivy": {"persistence": {"annotations": ANNOTATIONS}}},
        )
        docs = documents(values)
        self.assertNotIn(f"{PREFIX}-trivy-cache", pvcs(docs))


if __name__ == "__main__":
    unittest.main()
