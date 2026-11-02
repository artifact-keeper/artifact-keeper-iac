"""Offline Helm render tests for backend.extraFormatPaths (#359)."""

import os
from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM", "helm")
EXTRA = ["/myformat", "/plugin-2"]
HTTPROUTE = {
    "ingress": {"enabled": False},
    "networkPolicy": {"enabled": False},
    "httpRoute": {
        "enabled": True,
        "parentRefs": [{"name": "shared-gateway"}],
        "hostnames": ["registry.example.com"],
    },
}
OPENSHIFT = {
    "ingress": {"enabled": False},
    "route": {"enabled": True, "host": "registry.example.com"},
}


def run(extra, overrides=None):
    values = {"secrets": {"existingSecret": "paths-render-test"}}
    values.update(overrides or {})
    if extra is not None:
        values.setdefault("backend", {})["extraFormatPaths"] = extra
    return subprocess.run(
        [HELM, "template", "ak", str(CHART), "-f", "-"],
        input=yaml.safe_dump(values), capture_output=True, text=True,
    )


def docs(extra, overrides=None):
    result = run(extra, overrides)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def ingress_paths(extra):
    ingress = next(doc for doc in docs(extra) if doc["kind"] == "Ingress")
    return [
        (p["path"], p["pathType"], p["backend"]["service"]["name"])
        for p in ingress["spec"]["rules"][0]["http"]["paths"]
    ]


def httproute_paths(extra, overrides=None):
    route = next(
        doc for doc in docs(extra, {**HTTPROUTE, **(overrides or {})})
        if doc["kind"] == "HTTPRoute"
    )
    return route, [
        (m["path"]["value"], m["path"]["type"], rule["backendRefs"][0]["name"])
        for rule in route["spec"]["rules"] for m in rule["matches"]
    ]


def openshift_paths(extra):
    return {
        doc["spec"]["path"]: (doc["metadata"]["name"], doc["spec"]["to"]["name"])
        for doc in docs(extra, OPENSHIFT) if doc["kind"] == "Route"
    }


class ExtraFormatPathTests(unittest.TestCase):
    def assert_fails(self, extra, message, overrides=None):
        result = run(extra, overrides)
        self.assertNotEqual(result.returncode, 0, result.stdout[:200])
        self.assertIn(message, result.stderr)

    def test_empty_list_changes_nothing(self):
        for extra in ([], None):
            with self.subTest(extra=extra):
                self.assertEqual(ingress_paths(extra), ingress_paths(None))

    def test_ingress_appends_extra_prefixes_to_backend(self):
        base = ingress_paths([])
        paths = ingress_paths(EXTRA)
        web = [p for p in base if p[0] == "/"]
        self.assertEqual(
            [p for p in paths if p[0] != "/"],
            [p for p in base if p[0] != "/"]
            + [(path, "Prefix", "ak-artifact-keeper-backend") for path in EXTRA],
        )
        self.assertEqual([p for p in paths if p[0] == "/"], web)

    def test_httproute_and_ingress_stay_in_parity(self):
        _, route_paths = httproute_paths(EXTRA)
        expected = [
            (path, "PathPrefix" if kind == "Prefix" else "Exact", service)
            for path, kind, service in ingress_paths(EXTRA)
        ]
        self.assertEqual(route_paths, expected)

    def test_openshift_routes_get_one_route_per_extra_prefix(self):
        base = openshift_paths([])
        routes = openshift_paths(EXTRA)
        self.assertEqual(set(routes) - set(base), set(EXTRA))
        for path in EXTRA:
            self.assertEqual(
                routes[path],
                ("ak-artifact-keeper-route-" + path[1:], "ak-artifact-keeper-backend"),
            )

    def test_invalid_entries_fail(self):
        shape = "must be a single path segment"
        reserved = "is reserved"
        cases = [
            ("/myformat", None),
            (["myformat"], shape),
            (["/my format"], shape),
            (["/my\tformat"], shape),
            (["/MyFormat"], shape),
            (["/nested/path"], shape),
            (["/trailing/"], shape),
            (["/-dash"], shape),
            (["/"], shape),
            ([""], shape),
            ([42], shape),
            ([None], shape),
            (["/maven"], reserved),
            (["/general"], reserved),
            (["/api"], reserved),
            (["/v2"], reserved),
            (["/health"], reserved),
            (["/ready"], reserved),
            (["/metrics"], reserved),
            (["/dtrack"], reserved),
            (["/myformat", "/myformat"], "more than once"),
        ]
        for extra, message in cases:
            with self.subTest(extra=extra):
                self.assert_fails(
                    extra, message or "backend.extraFormatPaths must be a list"
                )

    def test_validation_applies_to_every_routing_mode(self):
        for overrides in (HTTPROUTE, OPENSHIFT):
            with self.subTest(mode=list(overrides)[1]):
                self.assert_fails(["/maven"], "is reserved", overrides)

    def test_httproute_rule_limit(self):
        # 40 built-in backend matches plus N extras, eight per rule, plus the
        # web rule must stay within the CRD's 16 rules.
        fits = [f"/p{i}" for i in range(80)]
        route, _ = httproute_paths(fits)
        self.assertEqual(len(route["spec"]["rules"]), 16)
        self.assert_fails(fits + ["/p80"], "more than the Gateway API limit of 16", HTTPROUTE)
        dtrack = {
            "dependencyTrack": {"enabled": True},
            "httpRoute": {**HTTPROUTE["httpRoute"], "dtrack": {"enabled": True}},
        }
        route, _ = httproute_paths(fits[:72], dtrack)
        self.assertEqual(len(route["spec"]["rules"]), 16)
        self.assert_fails(fits[:73], "more than the Gateway API limit of 16", {**HTTPROUTE, **dtrack})


if __name__ == "__main__":
    unittest.main()
