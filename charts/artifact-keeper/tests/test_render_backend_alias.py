"""Render tests for the bare "backend" ExternalName alias (#327)."""

from pathlib import Path
import os
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
PROXY = {"global": {"proxy": {"enabled": True, "httpProxy": "http://proxy:3128"}},
         "backend": {"proxy": {"enabled": True}}}


def run_helm(values):
    return subprocess.run(
        [os.environ.get("HELM", "helm"), "template", "ak", str(CHART), "--namespace", "test",
         "--set", "secrets.existingSecret=render-test", "-f", "-"],
        input=yaml.safe_dump(values), capture_output=True, text=True, check=False,
    )


def render(values):
    result = run_helm(values)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [d for d in yaml.safe_load_all(result.stdout) if d]


def alias(docs):
    return [d for d in docs if d["kind"] == "Service" and d["metadata"]["name"] == "backend"]


def backend_no_proxy(docs):
    deploy = next(d for d in docs if d["kind"] == "Deployment"
                  and d["metadata"]["name"].endswith("-backend"))
    container = next(c for c in deploy["spec"]["template"]["spec"]["containers"]
                     if c["name"] == "backend")
    env = {e["name"]: e.get("value") for e in container["env"]}
    return env["NO_PROXY"].split(",")


class BackendAliasTests(unittest.TestCase):
    def test_alias_renders_by_default(self):
        docs = render(PROXY)
        services = alias(docs)
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0]["spec"], {
            "type": "ExternalName",
            "externalName": "ak-artifact-keeper-backend.test.svc.cluster.local"})
        self.assertIn("backend", backend_no_proxy(docs))

    def test_alias_can_be_disabled(self):
        docs = render({**PROXY, "web": {"backendAlias": {"enabled": False}}})
        self.assertEqual(alias(docs), [])
        self.assertNotIn("backend", backend_no_proxy(docs))
        # The web pod still reaches the backend through its release-qualified name.
        web = next(d for d in docs if d["kind"] == "Deployment"
                   and d["metadata"]["name"].endswith("-web"))
        env = {e["name"]: e.get("value") for e in web["spec"]["template"]["spec"]["containers"][0]["env"]}
        self.assertEqual(env["BACKEND_URL"], "http://ak-artifact-keeper-backend:8080")

    def test_alias_requires_web(self):
        self.assertEqual(alias(render({"web": {"enabled": False}})), [])

    def test_non_boolean_fails(self):
        result = run_helm({"web": {"backendAlias": {"enabled": "false"}}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("web.backendAlias.enabled must be a boolean", result.stderr)


if __name__ == "__main__":
    unittest.main()
