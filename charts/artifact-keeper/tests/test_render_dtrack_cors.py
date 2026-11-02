"""Render tests for Dependency-Track CORS on each public exposure path."""

from pathlib import Path
import os
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
ROUTE = {"route": {"enabled": True, "host": "ak.apps.example.com", "dtrack": {"enabled": True}}}


def merge(base, extra):
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def run_helm(values):
    return subprocess.run(
        [os.environ.get("HELM", "helm"), "template", "ak", str(CHART),
         "--set", "secrets.existingSecret=render-test", "-f", "-"],
        input=yaml.safe_dump(values), capture_output=True, text=True, check=False,
    )


def cors(values):
    result = run_helm(values)
    if result.returncode:
        raise AssertionError(result.stderr)
    docs = [d for d in yaml.safe_load_all(result.stdout) if d]
    deploy = next(d for d in docs if d["kind"] == "Deployment"
                  and d["metadata"]["name"].endswith("-dtrack"))
    env = {e["name"]: e.get("value") for e in deploy["spec"]["template"]["spec"]["containers"][0]["env"]}
    return env["ALPINE_CORS_ENABLED"], env.get("ALPINE_CORS_ALLOW_ORIGIN")


class RouteCorsTests(unittest.TestCase):
    """#351: the OpenShift /dtrack Route gets the same CORS settings."""

    def test_route_derives_https_origin_from_host(self):
        self.assertEqual(cors(ROUTE), ("true", "https://ak.apps.example.com"))

    def test_route_without_tls_derives_http_origin(self):
        values = merge(ROUTE, {"route": {"tls": {"enabled": False}}})
        self.assertEqual(cors(values), ("true", "http://ak.apps.example.com"))

    def test_route_origin_override(self):
        values = merge(ROUTE, {"route": {"dtrack": {"corsAllowOrigin": "https://dt.example.com"}}})
        self.assertEqual(cors(values), ("true", "https://dt.example.com"))

    def test_route_host_falls_back_to_fleet_host(self):
        values = merge(ROUTE, {"route": {"host": ""}, "fleet": {"host": "fleet.example.com"}})
        self.assertEqual(cors(values), ("true", "https://fleet.example.com"))

    def test_route_without_dtrack_or_disabled_routes_keep_cors_off(self):
        for values in ({}, merge(ROUTE, {"route": {"dtrack": {"enabled": False}}}),
                       merge(ROUTE, {"route": {"enabled": False}})):
            with self.subTest(values=values):
                self.assertEqual(cors(values), ("false", None))

    def test_ingress_precedence_is_unchanged(self):
        values = merge(ROUTE, {"ingress": {"dtrack": {"enabled": True, "corsAllowOrigin": "https://ingress"}}})
        self.assertEqual(cors(values), ("true", "https://ingress"))
        values = {"ingress": {"dtrack": {"enabled": True}}}
        self.assertEqual(cors(values), ("true", "*"))


if __name__ == "__main__":
    unittest.main()
