"""Offline Helm render tests for backend.shutdown (backend 1.13.0, artifact-keeper#5921)."""

import os
from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM", "helm")


def run(values):
    values = {"secrets": {"existingSecret": "shutdown-render-test"}, **values}
    return subprocess.run(
        [HELM, "template", "ak", str(CHART), "-f", "-"],
        input=yaml.safe_dump(values), capture_output=True, text=True,
    )


def backend_pod(values):
    """Return (pod spec, backend container) of the backend Deployment."""
    result = run(values)
    if result.returncode:
        raise AssertionError(result.stderr)
    deployment = next(
        doc for doc in yaml.safe_load_all(result.stdout)
        if doc and doc["kind"] == "Deployment"
        and doc["metadata"]["labels"].get("app.kubernetes.io/component") == "backend"
    )
    pod = deployment["spec"]["template"]["spec"]
    container = next(c for c in pod["containers"] if c["name"] == "backend")
    return pod, container


def env_of(container):
    return {e["name"]: e.get("value") for e in container["env"]}


def shutdown(**fields):
    return {"backend": {"shutdown": fields}}


class BackendShutdownRenderTests(unittest.TestCase):
    def assert_fails(self, values, message):
        result = run(values)
        self.assertNotEqual(result.returncode, 0, result.stdout[:200])
        self.assertIn(message, result.stderr)

    def test_defaults_render_nothing(self):
        pod, container = backend_pod({})
        self.assertNotIn("terminationGracePeriodSeconds", pod)
        self.assertNotIn("lifecycle", container)
        self.assertNotIn("SHUTDOWN_DRAIN_SECS", env_of(container))

    def test_a_drain_renders_the_variable_and_a_grace_period_that_covers_it(self):
        pod, container = backend_pod(shutdown(drainSecs=10))
        self.assertEqual(env_of(container)["SHUTDOWN_DRAIN_SECS"], "10")
        # 10 drain + 15 longest request + 5 flush = 30, Kubernetes' default.
        self.assertEqual(pod["terminationGracePeriodSeconds"], 30)
        self.assertNotIn("lifecycle", container)

    def test_the_derived_grace_period_adds_the_prestop_hook_and_the_longest_request(self):
        pod, container = backend_pod(
            shutdown(drainSecs=10, preStopSleepSecs=5, longestRequestSecs=120))
        self.assertEqual(pod["terminationGracePeriodSeconds"], 5 + 10 + 120 + 5)
        self.assertEqual(
            container["lifecycle"]["preStop"]["exec"]["command"], ["sleep", "5"])

    def test_the_derived_grace_period_is_never_below_the_kubernetes_default(self):
        pod, _ = backend_pod(shutdown(drainSecs=2, longestRequestSecs=0))
        self.assertEqual(pod["terminationGracePeriodSeconds"], 30)

    def test_a_drain_set_in_backend_env_counts_toward_the_grace_period(self):
        pod, container = backend_pod({"backend": {"env": {"SHUTDOWN_DRAIN_SECS": "20"}}})
        self.assertEqual(pod["terminationGracePeriodSeconds"], 20 + 15 + 5)
        names = [e["name"] for e in container["env"]]
        self.assertEqual(names.count("SHUTDOWN_DRAIN_SECS"), 1)

    def test_an_explicit_grace_period_is_rendered_as_given(self):
        pod, _ = backend_pod(shutdown(drainSecs=10, terminationGracePeriodSeconds=90))
        self.assertEqual(pod["terminationGracePeriodSeconds"], 90)
        pod, _ = backend_pod(shutdown(terminationGracePeriodSeconds=60))
        self.assertEqual(pod["terminationGracePeriodSeconds"], 60)

    def test_a_grace_period_the_drain_does_not_fit_in_fails(self):
        self.assert_fails(
            shutdown(drainSecs=10, preStopSleepSecs=5, terminationGracePeriodSeconds=20),
            "must exceed preStopSleepSecs + drain + 5 (20)")

    def test_a_conflicting_backend_env_entry_fails(self):
        self.assert_fails(
            {"backend": {"env": {"SHUTDOWN_DRAIN_SECS": "20"}, "shutdown": {"drainSecs": 10}}},
            "conflicts with backend.shutdown.drainSecs")
        pod, container = backend_pod(
            {"backend": {"env": {"SHUTDOWN_DRAIN_SECS": "10"}, "shutdown": {"drainSecs": 10}}})
        self.assertEqual(env_of(container)["SHUTDOWN_DRAIN_SECS"], "10")

    def test_invalid_values_fail(self):
        for values, message in (
            (shutdown(drainSecs=2.5), "drainSecs must be a whole number"),
            (shutdown(drainSecs=-1), "drainSecs must be a whole number"),
            (shutdown(drainSecs="10"), "drainSecs must be a whole number"),
            (shutdown(drainSecs=301), "drainSecs must be at most 300"),
            (shutdown(preStopSleepSecs=-5), "preStopSleepSecs must be a whole number"),
        ):
            with self.subTest(values=values):
                self.assert_fails(values, message)


if __name__ == "__main__":
    unittest.main()
