"""Offline render tests for credentials in backend.env (#375), the OpenSearch
NetworkPolicy (#376) and Prometheus access to the metrics listener (#307)."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM", "helm")
BASE = ["--set", "secrets.existingSecret=render-test"]


def run(values, notes=False):
    """Render the chart. With notes=True, NOTES.txt is rendered too.

    `helm template` does not render NOTES.txt, so the notes variant renders a
    copy of the chart whose NOTES.txt is wrapped in a ConfigMap named notes.
    """
    with tempfile.TemporaryDirectory() as directory:
        chart = CHART
        if notes:
            chart = Path(directory) / "chart"
            shutil.copytree(CHART, chart, ignore=shutil.ignore_patterns("tests"))
            body = (chart / "templates/NOTES.txt").read_text()
            (chart / "templates/NOTES.txt").unlink()
            (chart / "templates/_notes.tpl").write_text(
                '{{- define "test.notes" -}}\n' + body + "\n{{- end -}}\n"
            )
            (chart / "templates/zz-notes.yaml").write_text(
                "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: notes\n"
                'data:\n  notes: {{ include "test.notes" . | quote }}\n'
            )
        return subprocess.run(
            [HELM, "template", "ak", str(chart), *BASE, "-f", "-"],
            input=yaml.safe_dump(values), capture_output=True, text=True, check=False,
        )


def render(values=None):
    result = run(values or {})
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def notes(values=None):
    result = run(values or {}, notes=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    return next(d for d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "notes")["data"]["notes"]


def named(docs, kind, suffix):
    found = [d for d in docs if d["kind"] == kind and d["metadata"]["name"].endswith(suffix)]
    return found[0] if found else None


def backend_env(docs):
    container = named(docs, "Deployment", "-backend")["spec"]["template"]["spec"]["containers"][0]
    names = [entry["name"] for entry in container["env"]]
    assert len(names) == len(set(names)), f"duplicate env names: {names}"
    return {entry["name"]: entry for entry in container["env"]}


class BackendEnvCredentialTests(unittest.TestCase):
    CREDENTIALS = (
        "ADMIN_PASSWORD", "INITIAL_ADMIN_PASSWORD", "JWT_SECRET", "S3_SECRET_KEY",
        "S3_SECRET_ACCESS_KEY", "DEPENDENCY_TRACK_API_KEY", "OPENSEARCH_PASSWORD",
        "OIDC_CLIENT_SECRET", "LDAP_BIND_PASSWORD", "PEER_API_KEY",
    )

    def test_credentials_fail_the_render(self):
        for key in self.CREDENTIALS:
            with self.subTest(key=key):
                result = run({"backend": {"env": {key: "s3cr3t-value"}}})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"backend.env sets {key}.", result.stderr)
                self.assertIn("backend.environmentSecrets", result.stderr)

    def test_database_url_only_with_a_password(self):
        result = run({"backend": {"env": {"DATABASE_URL": "postgres://ak:pw@db:5432/ak"}}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("backend.env sets DATABASE_URL.", result.stderr)
        for url in ("postgres://ak@db:5432/ak", "postgres://db:5432/ak?sslmode=require"):
            with self.subTest(url=url):
                render({"backend": {"env": {"DATABASE_URL": url}}})

    def test_empty_placeholders_and_other_keys_pass(self):
        env = backend_env(render())
        self.assertEqual(env["ADMIN_PASSWORD"]["value"], "")
        render({"backend": {"env": {"ADMIN_PASSWORD": "", "RUST_LOG": "info", "S3_BUCKET": "b"}}})

    def test_environment_secrets_win_over_backend_env(self):
        docs = render({"backend": {
            "env": {"ADMIN_PASSWORD": "left-over-plaintext"},
            "environmentSecrets": [{
                "name": "ADMIN_PASSWORD",
                "secretKeyRef": {"name": "ak-admin", "key": "password"},
            }],
        }})
        entry = backend_env(docs)["ADMIN_PASSWORD"]
        self.assertNotIn("value", entry)
        self.assertEqual(entry["valueFrom"]["secretKeyRef"], {"name": "ak-admin", "key": "password"})
        self.assertNotIn("left-over-plaintext", yaml.safe_dump_all(docs))

    def test_acknowledged_credentials_render_with_a_warning(self):
        values = {"backend": {"allowCredentialsInEnv": True, "env": {"ADMIN_PASSWORD": "test-only", "PEER_API_KEY": "k"}}}
        env = backend_env(render(values))
        self.assertEqual(env["ADMIN_PASSWORD"]["value"], "test-only")
        text = notes(values)
        self.assertIn("WARNING: backend.env sets ADMIN_PASSWORD, PEER_API_KEY", text)
        self.assertNotIn("WARNING: backend.env sets", notes())

    def test_flag_must_be_boolean(self):
        result = run({"backend": {"allowCredentialsInEnv": "true"}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("backend.allowCredentialsInEnv must be a boolean", result.stderr)

    def test_test_profiles_acknowledge_their_credentials(self):
        for profile in ("values-smoke.yaml", "ci/test-values.yaml", "values-mesh-main.yaml", "values-mesh-peer.yaml"):
            with self.subTest(profile=profile):
                values = yaml.safe_load((CHART / profile).read_text())
                self.assertIs(values["backend"]["allowCredentialsInEnv"], True)
        for profile in ("values.yaml", "values-production.yaml", "values-staging.yaml", "values-openshift.yaml"):
            with self.subTest(profile=profile):
                values = yaml.safe_load((CHART / profile).read_text())
                self.assertFalse(values.get("backend", {}).get("allowCredentialsInEnv", False))


class OpenSearchPolicyTests(unittest.TestCase):
    def policy(self, values=None):
        return named(render(values), "NetworkPolicy", "-opensearch")

    def assert_backend_only(self, policy):
        rules = policy["spec"]["ingress"]
        self.assertEqual(policy["spec"]["policyTypes"], ["Ingress"])
        self.assertEqual(policy["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/component"], "opensearch")
        http = next(r for r in rules if r["ports"] == [{"port": 9200, "protocol": "TCP"}])
        self.assertEqual([p["podSelector"]["matchLabels"]["app.kubernetes.io/component"] for p in http["from"]], ["backend"])
        transport = next(r for r in rules if r["ports"] == [{"port": 9300, "protocol": "TCP"}])
        self.assertEqual([p["podSelector"]["matchLabels"]["app.kubernetes.io/component"] for p in transport["from"]], ["opensearch"])

    def test_rendered_by_default(self):
        self.assert_backend_only(self.policy())

    def test_rendered_when_chart_policies_are_off(self):
        values = {"networkPolicy": {"enabled": False}}
        self.assert_backend_only(self.policy(values))
        self.assertEqual([d["metadata"]["name"] for d in render(values) if d["kind"] == "NetworkPolicy"], ["ak-artifact-keeper-opensearch"])
        self.assertIn("admits :9200 from the backend pods", notes(values))

    def test_opt_out_and_disabled_opensearch(self):
        values = {"networkPolicy": {"enabled": False}, "opensearch": {"networkPolicy": {"enabled": False}}}
        self.assertIsNone(self.policy(values))
        self.assertIn("ANY pod in the cluster", notes(values))
        self.assertIsNone(self.policy({"opensearch": {"enabled": False}}))

    def test_extra_from(self):
        peer = {"podSelector": {"matchLabels": {"app": "opensearch-dashboards"}}}
        policy = self.policy({"opensearch": {"networkPolicy": {"extraFrom": [peer]}}})
        http = next(r for r in policy["spec"]["ingress"] if r["ports"][0]["port"] == 9200)
        self.assertEqual(http["from"][1], peer)

    def test_no_auth_warning_only_without_security_plugin(self):
        self.assertIn("Security plugin disabled", notes())
        text = notes({"opensearch": {"disableSecurityPlugin": False, "auth": {"password": "x"}}})
        self.assertNotIn("Security plugin disabled", text)


class MetricsPolicyTests(unittest.TestCase):
    def scrape_rule(self, docs, suffix="-backend"):
        policy = named(docs, "NetworkPolicy", suffix)
        rules = [
            r for r in policy["spec"]["ingress"]
            if any("namespaceSelector" in p and "podSelector" not in p for p in r["from"])
            or r["from"] == [{"podSelector": {"matchLabels": {"app.kubernetes.io/name": "prometheus"}}}]
        ]
        self.assertEqual(len(rules), 1)
        return rules[0]

    def test_default_unchanged(self):
        rule = self.scrape_rule(render())
        self.assertEqual(rule["from"], [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "monitoring"}}}])
        self.assertEqual(rule["ports"], [{"port": 8080, "protocol": "TCP"}])

    def test_metrics_listener_port_is_admitted_and_matches_service_monitor(self):
        docs = render({
            "backend": {"metricsListener": {"enabled": True, "port": 9100}},
            "serviceMonitor": {"enabled": True},
        })
        rule = self.scrape_rule(docs)
        self.assertIn({"port": 9100, "protocol": "TCP"}, rule["ports"])
        monitor = named(docs, "ServiceMonitor", "-backend")
        port_name = monitor["spec"]["endpoints"][0]["port"]
        service = named(docs, "Service", "-backend")
        container_port = next(p for p in service["spec"]["ports"] if p["name"] == port_name)["port"]
        self.assertIn({"port": container_port, "protocol": "TCP"}, rule["ports"])

    def test_monitoring_namespace_and_peers(self):
        docs = render({"networkPolicy": {"monitoringNamespace": "observability"}})
        for suffix in ("-backend", "-web"):
            self.assertEqual(
                self.scrape_rule(docs, suffix)["from"],
                [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "observability"}}}],
            )
        peers = [{"podSelector": {"matchLabels": {"app.kubernetes.io/name": "prometheus"}}}]
        docs = render({"networkPolicy": {"monitoringPeers": peers}})
        self.assertEqual(self.scrape_rule(docs)["from"], peers)
        result = run({"networkPolicy": {"monitoringNamespace": ""}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("networkPolicy.monitoringNamespace", result.stderr)

    def test_service_monitor_labels(self):
        docs = render({"serviceMonitor": {"enabled": True, "labels": {"release": "kube-prom-stack"}}})
        self.assertEqual(named(docs, "ServiceMonitor", "-backend")["metadata"]["labels"]["release"], "kube-prom-stack")


class ReuseValuesTests(unittest.TestCase):
    """`helm upgrade --reuse-values` keeps the previous chart's default values,
    so keys added in this chart are absent. Null removes them here."""

    MISSING = {
        "backend": {"allowCredentialsInEnv": None},
        "opensearch": {"networkPolicy": None},
        "networkPolicy": {"monitoringNamespace": None, "monitoringPeers": None},
        "serviceMonitor": {"labels": None, "enabled": True},
    }

    def test_new_keys_missing_keep_secure_defaults(self):
        docs = render(self.MISSING)
        self.assertIsNotNone(named(docs, "NetworkPolicy", "-opensearch"))
        rule = MetricsPolicyTests.scrape_rule(self, docs)
        self.assertEqual(rule["from"], [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "monitoring"}}}])
        self.assertIn("namespace monitoring", notes(self.MISSING))
        values = {**self.MISSING, "backend": {"allowCredentialsInEnv": None, "env": {"ADMIN_PASSWORD": "x"}}}
        result = run(values)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("backend.env sets ADMIN_PASSWORD.", result.stderr)


if __name__ == "__main__":
    unittest.main()
