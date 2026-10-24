"""Dependency-Track bootstrap egress regression (#304)."""
import os
from pathlib import Path
import subprocess
import unittest

import yaml

CHART = Path(__file__).resolve().parents[1]


def render(enabled=True):
    output = subprocess.check_output(
        [os.environ.get("HELM", "helm"), "template", "other", str(CHART),
         "--namespace", "test", "--set", "secrets.existingSecret=render-test",
         "--set", "networkPolicy.enabled=" + str(enabled).lower()], text=True,
    )
    return [d for d in yaml.safe_load_all(output) if d]


class DtrackNetworkPolicyTests(unittest.TestCase):
    def test_bootstrap_can_reach_only_same_release_api_on_8080(self):
        docs = render()
        policy = next(d for d in docs if d["kind"] == "NetworkPolicy"
                      and d["metadata"]["name"].endswith("-dtrack"))
        job = next(d for d in docs if d["kind"] == "Job"
                   and d["metadata"]["name"].endswith("-dtrack-init"))
        service = next(d for d in docs if d["kind"] == "Service"
                       and d["metadata"]["name"].endswith("-dtrack"))
        selector = policy["spec"]["podSelector"]["matchLabels"]
        labels = job["spec"]["template"]["metadata"]["labels"]
        self.assertTrue(all(labels[k] == v for k, v in selector.items()))
        rules = [r for r in policy["spec"]["egress"]
                 if {"port": 8080, "protocol": "TCP"} in r.get("ports", [])]
        self.assertEqual(rules, [{"to": [{"podSelector": {
            "matchLabels": service["spec"]["selector"]}}],
            "ports": [{"port": 8080, "protocol": "TCP"}]}])
        self.assertEqual(selector["app.kubernetes.io/instance"], "other")
        ports = {p["port"] for r in policy["spec"]["egress"] for p in r["ports"]}
        self.assertTrue({53, 5432, 443, 8080}.issubset(ports))

    def test_disabled_network_policy_does_not_add_dtrack_policy(self):
        self.assertFalse(any(d["kind"] == "NetworkPolicy"
                            and d["metadata"]["name"].endswith("-dtrack")
                            for d in render(False)))
