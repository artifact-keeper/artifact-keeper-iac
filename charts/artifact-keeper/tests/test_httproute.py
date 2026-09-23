"""Offline render tests. See the chart README for tools and schema download."""

import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
CHART = ROOT / "charts/artifact-keeper"
TMP = ROOT / "tmp"
ENABLED = {
    "ingress": {"enabled": False},
    "httpRoute": {
        "enabled": True,
        "parentRefs": [{"name": "shared-gateway"}],
        "hostnames": ["registry.example.com"],
        "networkPolicy": {
            "namespace": "gateway-system",
            "podSelector": {"app.kubernetes.io/name": "envoy"},
        },
    },
}


def merged(base, overrides):
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merged(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def render(values=None):
    return subprocess.run(
        [
            os.environ.get("HELM", "helm"), "template", "route-test", str(CHART),
            "--namespace", "artifacts",
            "--set", "secrets.existingSecret=render-test",
            "-f", "-",
        ],
        input=yaml.safe_dump(values or {}),
        capture_output=True,
        text=True,
        check=False,
    )


def resources(result):
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def only(docs, kind):
    found = [doc for doc in docs if doc["kind"] == kind]
    if len(found) != 1:
        raise AssertionError(f"Expected one {kind}, found {len(found)}")
    return found[0]


def route_paths(route):
    return [
        (match["path"]["value"], match["path"]["type"], rule["backendRefs"][0])
        for rule in route["spec"]["rules"]
        for match in rule["matches"]
    ]


def gateway_policies(docs):
    return [
        doc for doc in docs
        if doc["kind"] == "NetworkPolicy"
        and doc["metadata"]["labels"].get("app.kubernetes.io/component") == "httproute"
    ]


class HTTPRouteTests(unittest.TestCase):
    def enabled(self, overrides=None):
        return resources(render(merged(ENABLED, overrides or {})))

    def test_disabled_preserves_ingress_and_policies(self):
        defaults = resources(render())
        self.assertFalse(any(doc["kind"] == "HTTPRoute" for doc in defaults))
        self.assertFalse(gateway_policies(defaults))
        ingress = only(defaults, "Ingress")
        self.assertEqual(ingress["spec"]["ingressClassName"], "nginx")
        self.assertEqual(ingress["spec"]["tls"][0]["secretName"], "artifact-keeper-tls")
        self.assertEqual(
            ingress["metadata"]["annotations"]["nginx.ingress.kubernetes.io/proxy-body-size"],
            "1024m",
        )
        both_off = resources(render({"ingress": {"enabled": False}}))
        self.assertFalse(any(doc["kind"] in ("Ingress", "HTTPRoute") for doc in both_off))

    def test_backend_paths_match_ingress_and_current_package_routes(self):
        ingress = only(resources(render()), "Ingress")
        paths = ingress["spec"]["rules"][0]["http"]["paths"]
        docs = self.enabled()
        self.assertFalse(any(doc["kind"] == "Ingress" for doc in docs))
        route = only(docs, "HTTPRoute")
        actual = route_paths(route)
        expected = [
            (
                path["path"],
                "PathPrefix" if path["pathType"] == "Prefix" else "Exact",
                {
                    "name": path["backend"]["service"]["name"],
                    "port": path["backend"]["service"]["port"]["number"],
                },
            )
            for path in paths
        ]
        self.assertEqual(actual, expected)
        # An independent inventory prevents a shared-helper omission passing parity.
        packages = {
            "/maven", "/npm", "/pypi", "/nuget", "/cargo", "/gems", "/go",
            "/helm", "/debian", "/rpm", "/alpine", "/composer", "/conan",
            "/conda", "/swift", "/terraform", "/cocoapods", "/hex", "/pub",
            "/lfs", "/ivy", "/chef", "/puppet", "/ansible", "/cran",
            "/huggingface", "/jetbrains", "/vscode", "/proto", "/incus", "/ext",
        }
        self.assertEqual(
            {path for path, _, _ in actual},
            packages | {"/api", "/v2", "/health", "/ready", "/"},
        )
        self.assertEqual(len(actual), len({path for path, _, _ in actual}))
        for path, match_type, backend in actual:
            self.assertEqual(match_type, "Exact" if path in ("/health", "/ready") else "PathPrefix")
            self.assertTrue(backend["name"].endswith("-web" if path == "/" else "-backend"))
        self.assertNotIn("tls", route["spec"])
        self.assertNotIn("annotations", route["metadata"])
        self.assertEqual([len(rule["matches"]) for rule in route["spec"]["rules"]], [8, 8, 8, 8, 3, 1])

    def test_custom_fields_and_backend_references(self):
        refs = [
            {
                "group": "gateway.networking.k8s.io", "kind": "Gateway",
                "name": "shared-gateway", "namespace": "networking",
                "sectionName": "https", "port": 443,
            },
            {"name": "local-gateway"},
        ]
        docs = self.enabled({
            "fullnameOverride": "custom-registry",
            "httpRoute": {
                "parentRefs": refs,
                "hostnames": ["registry.example.com", "*.packages.example.com"],
                "labels": {"team": "packages", "app.kubernetes.io/component": "cannot-override"},
                "annotations": {"example.com/setting": "custom"},
            },
            "backend": {"service": {"httpPort": 8081}},
            "web": {"service": {"port": 3001}},
        })
        route = only(docs, "HTTPRoute")
        self.assertEqual(route["metadata"]["name"], "custom-registry")
        self.assertEqual(route["metadata"]["labels"]["team"], "packages")
        self.assertEqual(route["metadata"]["labels"]["app.kubernetes.io/component"], "httproute")
        self.assertEqual(route["metadata"]["annotations"], {"example.com/setting": "custom"})
        self.assertEqual(route["spec"]["parentRefs"], refs)
        self.assertEqual(route["spec"]["hostnames"], ["registry.example.com", "*.packages.example.com"])
        services = {doc["metadata"]["name"]: doc for doc in docs if doc["kind"] == "Service"}
        for _, _, ref in route_paths(route):
            self.assertNotIn("namespace", ref)
            self.assertTrue(ref["name"].startswith("custom-registry-"))
            self.assertEqual(ref["port"], services[ref["name"]]["spec"]["ports"][0]["port"])

    def test_web_and_dependency_track_toggles(self):
        for web, dtrack in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(web=web, dtrack=dtrack):
                docs = self.enabled({
                    "web": {"enabled": web},
                    "dependencyTrack": {"enabled": dtrack},
                    "httpRoute": {"dtrack": {"enabled": dtrack, "corsAllowOrigin": "https://registry.example.com"}},
                })
                paths = {path: ref for path, _, ref in route_paths(only(docs, "HTTPRoute"))}
                self.assertEqual("/" in paths, web)
                self.assertEqual("/dtrack" in paths, dtrack)
                self.assertEqual(len(gateway_policies(docs)), 1 + web + dtrack)
                if dtrack:
                    self.assertEqual(paths["/dtrack"], {"name": "route-test-artifact-keeper-dtrack", "port": 8080})
                    deployment = next(
                        doc for doc in docs if doc["kind"] == "Deployment"
                        and doc["metadata"]["name"].endswith("-dtrack")
                    )
                    env = {entry["name"]: entry.get("value") for entry in deployment["spec"]["template"]["spec"]["containers"][0]["env"]}
                    self.assertEqual(env["ALPINE_CORS_ENABLED"], "true")
                    self.assertEqual(env["ALPINE_CORS_ALLOW_ORIGIN"], "https://registry.example.com")

    def test_gateway_policy_access_is_narrow_and_additive(self):
        docs = self.enabled({"httpRoute": {"dtrack": {"enabled": True}}})
        policies = gateway_policies(docs)
        self.assertEqual(len(policies), 3)
        for policy in policies:
            spec = policy["spec"]
            self.assertEqual(spec["policyTypes"], ["Ingress"])
            self.assertEqual(spec["podSelector"]["matchLabels"]["app.kubernetes.io/instance"], "route-test")
            self.assertIn(spec["podSelector"]["matchLabels"]["app.kubernetes.io/component"], ("backend", "web", "dependency-track"))
            self.assertEqual(spec["ingress"], [{
                "from": [{
                    "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "gateway-system"}},
                    "podSelector": {"matchLabels": {"app.kubernetes.io/name": "envoy"}},
                }],
                "ports": [{"port": "http", "protocol": "TCP"}],
            }])
        existing = [doc for doc in docs if doc["kind"] == "NetworkPolicy" and doc not in policies]
        baseline = [doc for doc in resources(render()) if doc["kind"] == "NetworkPolicy"]
        self.assertEqual(existing, baseline)
        self.assertFalse(gateway_policies(self.enabled({"networkPolicy": {"enabled": False}})))

    def test_fleet_guardrail_also_gets_gateway_access(self):
        docs = self.enabled({
            "networkPolicy": {"enabled": False},
            "fleet": {"enabled": True, "guardrails": {"networkPolicy": True}, "externalDatabaseBootstrap": {"enabled": False}},
        })
        self.assertEqual(len(gateway_policies(docs)), 2)

    def test_policy_configuration_is_required_only_with_active_policies(self):
        values = copy.deepcopy(ENABLED)
        del values["httpRoute"]["networkPolicy"]
        result = render(values)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("httpRoute.networkPolicy", result.stderr)
        values["httpRoute"]["networkPolicy"] = {"namespace": "gateway-system", "podSelector": {}}
        result = render(values)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-empty httpRoute.networkPolicy.podSelector", result.stderr)
        values["networkPolicy"] = {"enabled": False}
        docs = resources(render(values))
        self.assertFalse(gateway_policies(docs))
        self.assertEqual(len(route_paths(only(docs, "HTTPRoute"))), 36)
        values["fleet"] = {
            "enabled": True,
            "guardrails": {"networkPolicy": True},
            "externalDatabaseBootstrap": {"enabled": False},
        }
        result = render(values)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("httpRoute.networkPolicy", result.stderr)

    def test_multiple_listeners_on_same_gateway(self):
        refs = [
            {"name": "shared-gateway", "sectionName": "http"},
            {"name": "shared-gateway", "namespace": "artifacts", "sectionName": "https"},
        ]
        self.assertEqual(only(self.enabled({"httpRoute": {"parentRefs": refs}}), "HTTPRoute")["spec"]["parentRefs"], refs)

    def test_unused_ingress_settings_do_not_enable_dtrack_cors(self):
        docs = self.enabled({"ingress": {"dtrack": {"enabled": True}}})
        deployment = next(
            doc for doc in docs if doc["kind"] == "Deployment"
            and doc["metadata"]["name"].endswith("-dtrack")
        )
        env = {entry["name"]: entry.get("value") for entry in deployment["spec"]["template"]["spec"]["containers"][0]["env"]}
        self.assertEqual(env["ALPINE_CORS_ENABLED"], "false")
        self.assertNotIn("ALPINE_CORS_ALLOW_ORIGIN", env)

    def test_invalid_configuration_fails_clearly(self):
        cases = [
            ({"ingress": {"enabled": True}}, "mutually exclusive"),
            ({"route": {"enabled": True, "host": "registry.example.com"}}, "route.enabled (OpenShift Routes) are mutually exclusive"),
            ({"backend": {"enabled": False}}, "backend.enabled"),
            ({"dependencyTrack": {"enabled": False}, "httpRoute": {"dtrack": {"enabled": True}}}, "dependencyTrack.enabled"),
            ({"httpRoute": {"enabled": "true"}}, "httpRoute"),
            ({"httpRoute": {"parentRefs": []}}, "parentRefs"),
            ({"httpRoute": {"parentRefs": "gateway"}}, "parentRefs"),
            ({"httpRoute": {"parentRefs": [{}]}}, "name"),
            ({"httpRoute": {"parentRefs": [{"name": ""}]}}, "parentRefs"),
            ({"httpRoute": {"parentRefs": [{"name": "gateway", "namespace": ""}]}}, "namespace"),
            ({"httpRoute": {"parentRefs": [{"name": "gateway", "sectionName": ""}]}}, "sectionName"),
            ({"httpRoute": {"parentRefs": [{"name": "gateway", "kind": "Service"}]}}, "kind"),
            ({"httpRoute": {"parentRefs": [{"name": "gateway", "group": "wrong.example"}]}}, "group"),
            ({"httpRoute": {"parentRefs": [{"name": "gateway", "port": 65536}]}}, "port"),
            ({"httpRoute": {"parentRefs": [{"name": f"gateway-{i}"} for i in range(33)]}}, "parentRefs"),
            ({"httpRoute": {"parentRefs": [{"name": "gateway"}, {"name": "gateway", "namespace": "artifacts"}]}}, "distinct listener"),
            ({"httpRoute": {"parentRefs": [{"name": "gateway"}, {"name": "gateway", "sectionName": "https"}]}}, "consistent sectionName"),
            ({"httpRoute": {"hostnames": []}}, "hostnames"),
            ({"httpRoute": {"hostnames": "registry.example.com"}}, "hostnames"),
            ({"httpRoute": {"hostnames": ["https://registry.example.com"]}}, "hostnames"),
            ({"httpRoute": {"hostnames": ["127.0.0.1"]}}, "hostnames"),
            ({"httpRoute": {"hostnames": ["*"]}}, "hostnames"),
            ({"httpRoute": {"hostnames": [f"registry-{i}.example.com" for i in range(17)]}}, "hostnames"),
            ({"httpRoute": {"hostnames": ["registry.example.com"] * 2}}, "hostnames"),
            ({"httpRoute": {"annotations": {"example.com/key": True}}}, "annotations"),
            ({"httpRoute": {"labels": {"team": "not a label"}}}, "labels"),
            ({"httpRoute": {"networkPolicy": {"namespace": ""}}}, "httpRoute.networkPolicy.namespace"),
            ({"httpRoute": {"networkPolicy": {"namespace": "bad_namespace"}}}, "namespace"),
            ({"httpRoute": {"networkPolicy": {"podSelector": None}}}, "podSelector"),
            ({"httpRoute": {"networkPolicy": {"podSelector": {"app.kubernetes.io/name": None}}}}, "podSelector"),
            ({"httpRoute": {"dtrack": {"enabled": "false"}}}, "enabled"),
            ({"httpRoute": {"unknown": "typo"}}, "unknown"),
        ]
        for overrides, message in cases:
            with self.subTest(overrides=overrides):
                result = render(merged(ENABLED, overrides))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_official_gateway_schema_and_limits(self):
        crd_path = Path(os.environ.get("GATEWAY_API_CRD", TMP / "httproute-crd.yaml"))
        crd = yaml.safe_load(crd_path.read_text())
        schema = next(version["schema"]["openAPIV3Schema"] for version in crd["spec"]["versions"] if version["name"] == "v1")
        rules_schema = schema["properties"]["spec"]["properties"]["rules"]
        self.assertEqual(rules_schema["maxItems"], 16)
        max_matches = rules_schema["items"]["properties"]["matches"]["maxItems"]
        self.assertGreaterEqual(max_matches, 8)
        TMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="httproute-schema-", dir=TMP) as directory:
            schema_path = Path(directory) / "httproute.json"
            schema_path.write_text(json.dumps(schema))
            for overrides in (
                {},
                {"web": {"enabled": False}},
                {"httpRoute": {"dtrack": {"enabled": True}}},
                {"httpRoute": {"parentRefs": [{"name": "gateway", "namespace": "networking", "sectionName": "https", "port": 443}]}},
            ):
                route = only(self.enabled(overrides), "HTTPRoute")
                self.assertLessEqual(len(route["spec"]["rules"]), rules_schema["maxItems"])
                for rule in route["spec"]["rules"]:
                    self.assertLessEqual(len(rule["matches"]), 8)
                    self.assertLessEqual(len(rule["matches"]), max_matches)
                command = [
                    os.environ.get("KUBECONFORM", "kubeconform"),
                    "-strict", "-summary", "-schema-location", str(schema_path),
                ]
                result = subprocess.run(command, input=yaml.safe_dump(route), text=True, capture_output=True, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Valid: 1", result.stdout)
            # Prove validation is not silently skipping the CRD or its maxItems.
            route["spec"]["rules"][0]["matches"] = [
                {"path": {"type": "PathPrefix", "value": f"/test-{i}"}}
                for i in range(max_matches + 1)
            ]
            result = subprocess.run(command, input=yaml.safe_dump(route), text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(str(max_matches), result.stdout)


if __name__ == "__main__":
    unittest.main()
