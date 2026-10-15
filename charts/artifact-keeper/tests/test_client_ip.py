"""Offline render tests for backend.clientIp (trusted proxies, XFF for authz)."""

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


def render(values, notes=False):
    """Render the chart; with notes=True, return NOTES.txt as text instead.

    `helm template` does not render NOTES.txt, so the notes variant renders a
    copy of the chart whose NOTES.txt is wrapped in a ConfigMap.
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
        result = subprocess.run(
            [HELM, "template", "ak", str(chart), *BASE, "-f", "-"],
            input=yaml.safe_dump(values), capture_output=True, text=True, check=False,
        )
    if result.returncode:
        raise AssertionError(result.stderr)
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    if notes:
        return next(doc for doc in docs if doc["kind"] == "ConfigMap" and doc["metadata"]["name"] == "notes")["data"]["notes"]
    return docs


def backend_env(docs):
    deployment = next(
        doc for doc in docs
        if doc["kind"] == "Deployment" and doc["metadata"]["name"].endswith("-backend")
    )
    entries = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    names = [entry["name"] for entry in entries]
    assert len(names) == len(set(names)), f"duplicate env names: {names}"
    return {entry["name"]: entry.get("value") for entry in entries}


class ClientIpTests(unittest.TestCase):
    def test_defaults_trust_no_proxy(self):
        env = backend_env(render({}))
        self.assertNotIn("RATE_LIMIT_TRUSTED_PROXY_CIDRS", env)
        self.assertEqual(env["XFF_TRUSTED_FOR_AUTHZ"], "false")
        self.assertNotIn("trusted proxies are set", render({}, notes=True))

    def test_structured_values_render(self):
        values = {"backend": {"clientIp": {"trustedProxyCidrs": "10.1.42.0/24", "xffTrustedForAuthz": True}}}
        env = backend_env(render(values))
        self.assertEqual(env["RATE_LIMIT_TRUSTED_PROXY_CIDRS"], "10.1.42.0/24")
        self.assertEqual(env["XFF_TRUSTED_FOR_AUTHZ"], "true")
        self.assertNotIn("trusted proxies are set", render(values, notes=True))

    def test_backend_env_wins(self):
        values = {"backend": {
            "clientIp": {"trustedProxyCidrs": "10.1.42.0/24", "xffTrustedForAuthz": True},
            "env": {"RATE_LIMIT_TRUSTED_PROXY_CIDRS": "10.9.0.0/16", "XFF_TRUSTED_FOR_AUTHZ": "false"},
        }}
        env = backend_env(render(values))
        self.assertEqual(env["RATE_LIMIT_TRUSTED_PROXY_CIDRS"], "10.9.0.0/16")
        self.assertEqual(env["XFF_TRUSTED_FOR_AUTHZ"], "false")
        notes = render(values, notes=True)
        self.assertIn("RATE_LIMIT_TRUSTED_PROXY_CIDRS=10.9.0.0/16", notes)

    def test_notes_warn_when_proxies_trusted_without_xff_authz(self):
        notes = render({"backend": {"clientIp": {"trustedProxyCidrs": "10.1.42.0/24"}}}, notes=True)
        self.assertIn("trusted proxies are set (RATE_LIMIT_TRUSTED_PROXY_CIDRS=10.1.42.0/24)", notes)
        self.assertIn("xffTrustedForAuthz", notes)

    def test_non_boolean_fails(self):
        with self.assertRaisesRegex(AssertionError, "xffTrustedForAuthz must be a boolean"):
            render({"backend": {"clientIp": {"xffTrustedForAuthz": "yes"}}})


if __name__ == "__main__":
    unittest.main()
