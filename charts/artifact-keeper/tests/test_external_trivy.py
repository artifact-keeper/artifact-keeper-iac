"""Offline render tests for trivy.externalUrl; requires Helm and the CI-pinned PyYAML."""

import os
from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
EXTERNAL = "http://trivy.scanners.svc.cluster.local:8090"
FLEET = {
    "fleet": {
        "enabled": True,
        "instanceId": "registry-test",
        "guardrails": {"resourceQuota": True},
        "externalDatabaseBootstrap": {
            "host": "postgres.example.com",
            "adminSecret": "db-admin",
            "existingSecret": "db-instance",
        },
    },
    "postgres": {"enabled": False},
}


def render(values=None):
    result = subprocess.run(
        [
            os.environ.get("HELM", "helm"), "template", "trivy-test", str(CHART),
            "--namespace", "artifacts",
            "--set", "secrets.existingSecret=render-test",
            "-f", "-",
        ],
        input=yaml.safe_dump(values or {}),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def merged(*parts):
    out = {}
    for part in parts:
        for key, value in part.items():
            if isinstance(value, dict) and isinstance(out.get(key), dict):
                out[key] = merged(out[key], value)
            else:
                out[key] = value
    return out


def trivy_resources(docs):
    return [
        (doc["kind"], doc["metadata"]["name"]) for doc in docs
        if doc["kind"] in ("Deployment", "Service", "PersistentVolumeClaim")
        and doc["metadata"].get("labels", {}).get("app.kubernetes.io/component") == "trivy"
    ]


def backend(docs):
    return next(
        doc for doc in docs
        if doc["kind"] == "Deployment" and doc["metadata"]["name"].endswith("-backend")
    )


def backend_env(docs):
    container = backend(docs)["spec"]["template"]["spec"]["containers"][0]
    return {entry["name"]: entry.get("value") for entry in container["env"]}


def backend_volumes(docs):
    return {v["name"] for v in backend(docs)["spec"]["template"]["spec"]["volumes"]}


def backend_policy(docs):
    return next(
        doc for doc in docs
        if doc["kind"] == "NetworkPolicy" and doc["metadata"]["name"].endswith("-backend")
    )


class ExternalTrivyTests(unittest.TestCase):
    def test_default_keeps_bundled_server(self):
        docs = render()
        self.assertEqual(
            sorted(kind for kind, _ in trivy_resources(docs)),
            ["Deployment", "PersistentVolumeClaim", "Service"],
        )
        env = backend_env(docs)
        self.assertEqual(env["TRIVY_URL"], "http://trivy-test-artifact-keeper-trivy:8090")
        self.assertEqual(env["SCAN_WORKSPACE_PATH"], "/scan-workspace")

    def test_external_url_wins_over_enabled(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                docs = render({
                    "trivy": {"enabled": enabled, "externalUrl": EXTERNAL, "db": {"preseed": {"enabled": True}}},
                    "backend": {"scanWorkspace": {"enabled": False}},
                })
                self.assertEqual(trivy_resources(docs), [])
                self.assertFalse(any("trivy-db-init" in str(doc) for doc in docs))
                env = backend_env(docs)
                self.assertEqual(env["TRIVY_URL"], EXTERNAL)
                self.assertEqual(env["SCAN_WORKSPACE_PATH"], "/scan-workspace")
                self.assertIn("scan-workspace", backend_volumes(docs))

    def test_disabled_without_external_url_sets_no_trivy_url(self):
        docs = render({"trivy": {"enabled": False}, "backend": {"scanWorkspace": {"enabled": False}}})
        self.assertEqual(trivy_resources(docs), [])
        self.assertNotIn("TRIVY_URL", backend_env(docs))
        self.assertNotIn("scan-workspace", backend_volumes(docs))

    def test_trailing_slash_trimmed_and_scheme_required(self):
        env = backend_env(render({"trivy": {"externalUrl": EXTERNAL + "/"}}))
        self.assertEqual(env["TRIVY_URL"], EXTERNAL)
        with self.assertRaisesRegex(AssertionError, "must be an http"):
            render({"trivy": {"externalUrl": "trivy.scanners:8090"}})

    def test_egress_rule_only_when_selector_given(self):
        def external_rules(docs):
            return [
                rule for rule in backend_policy(docs)["spec"]["egress"]
                if any("namespaceSelector" in peer for peer in rule.get("to", []))
            ]

        self.assertEqual(external_rules(render({"trivy": {"externalUrl": EXTERNAL}})), [])
        selector = {"matchLabels": {"kubernetes.io/metadata.name": "scanners"}}
        pods = {"matchLabels": {"app.kubernetes.io/name": "trivy"}}
        rules = external_rules(render({"trivy": {
            "externalUrl": EXTERNAL,
            "externalNetworkPolicy": {"namespaceSelector": selector, "podSelector": pods, "port": 9000},
        }}))
        self.assertEqual(rules, [{
            "to": [{"namespaceSelector": selector, "podSelector": pods}],
            "ports": [{"port": 9000, "protocol": "TCP"}],
        }])
        # Selector without externalUrl: no rule (there is no external server).
        self.assertEqual(external_rules(render({"trivy": {
            "externalNetworkPolicy": {"namespaceSelector": selector},
        }})), [])

    def test_fleet_quota_drops_trivy_footprint(self):
        def quota(values):
            docs = render(merged(FLEET, values))
            return next(doc for doc in docs if doc["kind"] == "ResourceQuota")["spec"]["hard"]

        bundled = quota({})
        external = quota({"trivy": {"externalUrl": EXTERNAL}})
        disabled = quota({"trivy": {"enabled": False}})
        self.assertEqual(external, disabled)
        self.assertNotEqual(external, bundled)


if __name__ == "__main__":
    unittest.main()
