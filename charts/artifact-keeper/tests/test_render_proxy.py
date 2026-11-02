"""Offline Helm render tests for the egress proxy helpers (#297)."""

import os
from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM", "helm")
PROXY = "http://p:3128"
PROXY_NAMES = {"HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy"}


def render(**overrides):
    values = {"secrets": {"existingSecret": "proxy-render-test"}, **overrides}
    result = subprocess.run(
        [HELM, "template", "ak", str(CHART), "-f", "-"],
        input=yaml.safe_dump(values), capture_output=True, text=True,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def workload(docs, component, kind="Deployment"):
    return next(
        doc for doc in docs
        if doc["kind"] == kind
        and doc["metadata"]["labels"].get("app.kubernetes.io/component") == component
    )


def container(doc, name, init=False):
    pod = doc["spec"]["template"]["spec"]
    return next(c for c in pod["initContainers" if init else "containers"] if c["name"] == name)


def env_of(c):
    """Return {name: value-or-valueFrom} and the list of names (duplicates kept)."""
    env = c.get("env") or []
    return {e["name"]: e.get("value", e.get("valueFrom")) for e in env}, [e["name"] for e in env]


def proxy_env(c):
    env, _ = env_of(c)
    return {k: v for k, v in env.items() if k in PROXY_NAMES}


class ProxyRenderTests(unittest.TestCase):
    def test_default_render_emits_no_proxy_env(self):
        for doc in render():
            if doc["kind"] not in ("Deployment", "StatefulSet", "Job"):
                continue
            pod = doc["spec"]["template"]["spec"]
            for c in (pod.get("initContainers") or []) + pod["containers"]:
                with self.subTest(workload=doc["metadata"]["name"], container=c["name"]):
                    self.assertEqual(proxy_env(c), {})

    def test_global_proxy_reaches_every_egress_container_once(self):
        docs = render(
            **{"global": {"proxy": {"httpProxy": PROXY, "httpsProxy": PROXY}}},
            imageBuilder={"enabled": True},
            cosign={"enabled": True},
            backend={"env": {"HTTP_PROXY": "dup", "no_proxy": "dup"}},
        )
        backend = workload(docs, "backend")
        cases = {
            "backend": container(backend, "backend"),
            "verify-image-signature": container(backend, "verify-image-signature", init=True),
            "buildkitd": container(workload(docs, "image-builder"), "buildkitd"),
            "trivy": container(workload(docs, "trivy"), "trivy"),
            "scanner-adapter": container(workload(docs, "scanner-adapter"), "scanner-adapter"),
            "dtrack-api": container(workload(docs, "dependency-track"), "dtrack-api"),
        }
        for name, c in cases.items():
            with self.subTest(container=name):
                env, names = env_of(c)
                for key in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
                    self.assertEqual(names.count(key), 1, key)
                    self.assertEqual(env[key], PROXY)
                for key in ("NO_PROXY", "no_proxy"):
                    self.assertEqual(names.count(key), 1, key)
                no_proxy = env["NO_PROXY"].split(",")
                self.assertEqual(env["no_proxy"], env["NO_PROXY"])
                for entry in ("localhost", "127.0.0.1", ".svc", ".svc.cluster.local", ".cluster.local",
                              "backend", "ak-artifact-keeper-backend", "ak-artifact-keeper-buildkitd",
                              "ak-artifact-keeper-postgres"):
                    self.assertIn(entry, no_proxy)
                self.assertEqual(len(no_proxy), len(set(no_proxy)))

        # Components that opt out by default stay untouched.
        self.assertEqual(proxy_env(container(workload(docs, "web"), "web")), {})
        self.assertEqual(proxy_env(container(workload(docs, "opensearch"), "opensearch")), {})

    def test_backend_env_keeps_unrelated_keys_while_proxy_keys_are_owned_by_helper(self):
        docs = render(
            **{"global": {"proxy": {"httpProxy": PROXY}}},
            backend={"env": {"HTTP_PROXY": "dup", "HTTPS_PROXY": "kept", "CUSTOM_FLAG": "1"}},
        )
        env, names = env_of(container(workload(docs, "backend"), "backend"))
        self.assertEqual(names.count("HTTP_PROXY"), 1)
        self.assertEqual(env["HTTP_PROXY"], PROXY)
        self.assertEqual(env["CUSTOM_FLAG"], "1")
        # Only httpProxy resolved, so the helper does not own HTTPS_PROXY and the
        # operator's backend.env entry survives.
        self.assertEqual(env["HTTPS_PROXY"], "kept")
        self.assertNotIn("https_proxy", env)

    def test_no_proxy_alias_and_buildkitd_entries_follow_their_services(self):
        docs = render(**{"global": {"proxy": {"httpProxy": PROXY}}}, web={"enabled": False})
        self.assertFalse([d for d in docs if d["kind"] == "Service" and d["metadata"]["name"] == "backend"])
        no_proxy = proxy_env(container(workload(docs, "backend"), "backend"))["NO_PROXY"].split(",")
        self.assertNotIn("backend", no_proxy)
        self.assertNotIn("ak-artifact-keeper-buildkitd", no_proxy)

    def test_component_no_proxy_extends_global_and_fields_override_individually(self):
        docs = render(
            **{"global": {"proxy": {"httpProxy": PROXY, "httpsProxy": PROXY, "noProxy": ".corp.example"}}},
            trivy={"db": {"preseed": {"enabled": True}},
                   "proxy": {"httpsProxy": "http://scan:3128", "noProxy": "mirror.corp.example"}},
        )
        trivy = workload(docs, "trivy")
        for c in (container(trivy, "trivy"), container(trivy, "trivy-db-init", init=True)):
            with self.subTest(container=c["name"]):
                env = proxy_env(c)
                self.assertEqual(env["HTTP_PROXY"], PROXY)
                self.assertEqual(env["HTTPS_PROXY"], "http://scan:3128")
                self.assertTrue(env["NO_PROXY"].endswith(",.corp.example,mirror.corp.example"))
        backend_env = proxy_env(container(workload(docs, "backend"), "backend"))
        self.assertTrue(backend_env["NO_PROXY"].endswith(",.corp.example"))

    def test_component_can_opt_out_of_global_proxy(self):
        docs = render(
            **{"global": {"proxy": {"httpProxy": PROXY, "httpsProxy": PROXY}}},
            dependencyTrack={"proxy": {"enabled": False}},
        )
        self.assertEqual(proxy_env(container(workload(docs, "dependency-track"), "dtrack-api")), {})
        self.assertNotEqual(proxy_env(container(workload(docs, "backend"), "backend")), {})

    def test_existing_secret_renders_secret_key_refs(self):
        docs = render(**{"global": {"proxy": {"existingSecret": "egress-proxy", "httpProxy": PROXY}}})
        env = proxy_env(container(workload(docs, "backend"), "backend"))
        self.assertEqual(env["HTTP_PROXY"], PROXY)
        self.assertEqual(env["http_proxy"], PROXY)
        ref = {"secretKeyRef": {"name": "egress-proxy", "key": "HTTPS_PROXY"}}
        self.assertEqual(env["HTTPS_PROXY"], ref)
        self.assertEqual(env["https_proxy"], ref)
        self.assertIn("ak-artifact-keeper-backend", env["NO_PROXY"])

        docs = render(backend={"proxy": {"existingSecret": "backend-proxy"}})
        env = proxy_env(container(workload(docs, "backend"), "backend"))
        self.assertEqual(env["HTTP_PROXY"], {"secretKeyRef": {"name": "backend-proxy", "key": "HTTP_PROXY"}})
        self.assertEqual(env["HTTPS_PROXY"], {"secretKeyRef": {"name": "backend-proxy", "key": "HTTPS_PROXY"}})
        self.assertEqual(proxy_env(container(workload(docs, "trivy"), "trivy")), {})


if __name__ == "__main__":
    unittest.main()
