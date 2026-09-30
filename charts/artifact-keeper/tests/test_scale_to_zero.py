"""Offline render tests for scaleToZero (KEDA HTTP add-on). Needs helm and PyYAML."""

import os
from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
BASE = {
    "secrets": {"existingSecret": "render-test"},
    "backend": {"persistence": {"enabled": False}},
    "fleet": {
        "enabled": True,
        "instanceId": "demo",
        "host": "demo.example.com",
        "preset": "medium",
        "guardrails": {"networkPolicy": True},
    },
    "networkPolicy": {"enabled": False},
}


def merged(base, overrides):
    result = yaml.safe_load(yaml.safe_dump(base))
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merged(result[key], value)
        else:
            result[key] = value
    return result


def render(values):
    return subprocess.run(
        [
            os.environ.get("HELM", "helm"), "template", "s2z", str(CHART),
            "--namespace", "demo", "-f", "-",
        ],
        input=yaml.safe_dump(values),
        capture_output=True,
        text=True,
        check=False,
    )


def docs(values):
    result = render(values)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def kind(resources, name):
    return [doc for doc in resources if doc["kind"] == name]


def ingress_backends(resources):
    (ingress,) = kind(resources, "Ingress")
    return {
        path["path"]: (path["backend"]["service"]["name"], path["backend"]["service"]["port"]["number"])
        for path in ingress["spec"]["rules"][0]["http"]["paths"]
    }


class ScaleToZeroTests(unittest.TestCase):
    def test_disabled_renders_nothing_new(self):
        resources = docs(BASE)
        self.assertFalse(kind(resources, "HTTPScaledObject"))
        self.assertFalse([d for d in kind(resources, "Service") if d["spec"].get("type") == "ExternalName"
                          and d["metadata"]["name"].endswith("-keda-interceptor")])
        backends = ingress_backends(resources)
        self.assertEqual(backends["/"], ("s2z-artifact-keeper-web", 3000))
        self.assertEqual(backends["/api"], ("s2z-artifact-keeper-backend", 8080))
        for deploy in kind(resources, "Deployment"):
            if deploy["metadata"]["name"].endswith(("-backend", "-web")):
                self.assertEqual(deploy["spec"]["replicas"], 2)

    def test_enabled_routes_through_interceptor(self):
        resources = docs(merged(BASE, {"scaleToZero": {"enabled": True}}))
        alias = [d for d in kind(resources, "Service") if d["metadata"]["name"] == "s2z-artifact-keeper-keda-interceptor"]
        self.assertEqual(len(alias), 1)
        self.assertEqual(alias[0]["spec"]["type"], "ExternalName")
        self.assertEqual(alias[0]["spec"]["externalName"],
                         "keda-add-ons-http-interceptor-proxy.keda.svc.cluster.local")
        for path, backend in ingress_backends(resources).items():
            self.assertEqual(backend, ("s2z-artifact-keeper-keda-interceptor", 8080), path)

        objects = {d["metadata"]["name"]: d for d in kind(resources, "HTTPScaledObject")}
        self.assertEqual(set(objects), {"s2z-artifact-keeper-backend", "s2z-artifact-keeper-web"})
        for d in objects.values():
            self.assertEqual(d["apiVersion"], "http.keda.sh/v1alpha1")
            self.assertEqual(d["spec"]["hosts"], ["demo.example.com"])
            self.assertEqual(d["spec"]["replicas"], {"min": 0, "max": 2})
            self.assertEqual(d["spec"]["scaledownPeriod"], 900)
            self.assertEqual(d["spec"]["scalingMetric"]["concurrency"]["targetValue"], 100)
        backend = objects["s2z-artifact-keeper-backend"]["spec"]
        self.assertEqual(backend["scaleTargetRef"]["service"], "s2z-artifact-keeper-backend")
        self.assertEqual(backend["scaleTargetRef"]["port"], 8080)
        self.assertIn("/api", backend["pathPrefixes"])
        self.assertIn("/v2", backend["pathPrefixes"])
        self.assertNotIn("/", backend["pathPrefixes"])
        web = objects["s2z-artifact-keeper-web"]["spec"]
        self.assertEqual(web["pathPrefixes"], ["/"])
        self.assertEqual(web["scaleTargetRef"]["port"], 3000)

        for deploy in kind(resources, "Deployment"):
            if deploy["metadata"]["name"].endswith(("-backend", "-web")):
                self.assertNotIn("replicas", deploy["spec"])

        policies = [d for d in kind(resources, "NetworkPolicy")
                    if d["metadata"]["labels"].get("app.kubernetes.io/component") == "keda-interceptor"]
        self.assertEqual(len(policies), 2)
        peer = policies[0]["spec"]["ingress"][0]["from"][0]
        self.assertEqual(peer["namespaceSelector"]["matchLabels"], {"kubernetes.io/metadata.name": "keda"})
        self.assertEqual(peer["podSelector"]["matchLabels"]["app.kubernetes.io/component"], "interceptor")

    def test_single_component_and_overrides(self):
        resources = docs(merged(BASE, {"scaleToZero": {
            "enabled": True, "components": ["web"], "maxReplicas": 4,
            "hosts": ["a.example.com"], "coldStartTimeout": "120s",
        }}))
        (obj,) = kind(resources, "HTTPScaledObject")
        self.assertEqual(obj["spec"]["hosts"], ["a.example.com"])
        self.assertEqual(obj["spec"]["replicas"]["max"], 4)
        self.assertEqual(obj["spec"]["timeouts"], {"conditionWait": "120s"})
        backends = ingress_backends(resources)
        self.assertEqual(backends["/"][0], "s2z-artifact-keeper-keda-interceptor")
        self.assertEqual(backends["/api"][0], "s2z-artifact-keeper-backend")

    def test_guardrails(self):
        cases = {
            "fleet.hibernate": {"fleet": {"hibernate": True}},
            "backend.persistence.enabled": {"backend": {"persistence": {"enabled": True}}},
            "backend.autoscaling.enabled": {"backend": {"autoscaling": {"enabled": True}}},
            "requires ingress.enabled": {"ingress": {"enabled": False}},
            "is not valid": {"scaleToZero": {"components": ["search"]}},
        }
        for message, overrides in cases.items():
            with self.subTest(message):
                values = merged(merged(BASE, {"scaleToZero": {"enabled": True}}), overrides)
                result = render(values)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)


if __name__ == "__main__":
    unittest.main()
