"""Offline Helm render tests for backend.migrationJob (artifact-keeper#6194)."""

import os
from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM", "helm")


def render(values, *args):
    values = {"secrets": {"existingSecret": "migrate-render-test"}, **values}
    result = subprocess.run(
        [HELM, "template", "ak", str(CHART), "-f", "-", *args],
        input=yaml.safe_dump(values), capture_output=True, text=True,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return [d for d in yaml.safe_load_all(result.stdout) if d]


def jobs(docs):
    return [d for d in docs if d["kind"] == "Job" and d["metadata"]["name"].endswith("-backend-migrate")]


def backend_env(docs):
    deployment = next(
        d for d in docs
        if d["kind"] == "Deployment"
        and d["metadata"]["labels"].get("app.kubernetes.io/component") == "backend"
    )
    container = next(c for c in deployment["spec"]["template"]["spec"]["containers"] if c["name"] == "backend")
    return container["env"]


def env_names(env):
    return [e["name"] for e in env]


ENABLED = {"backend": {"migrationJob": {"enabled": True}}}


class MigrationJobRenderTests(unittest.TestCase):
    def test_disabled_by_default(self):
        for args in ((), ("--is-upgrade",)):
            with self.subTest(args=args):
                docs = render({}, *args)
                self.assertEqual(jobs(docs), [])
                self.assertNotIn("SKIP_MIGRATIONS", env_names(backend_env(docs)))

    def test_enabled_upgrade_renders_hook_and_skips_startup_migrations(self):
        docs = render(ENABLED, "--is-upgrade")
        (job,) = jobs(docs)
        self.assertEqual(job["metadata"]["annotations"]["helm.sh/hook"], "pre-upgrade")
        self.assertEqual(job["spec"]["activeDeadlineSeconds"], 3600)
        pod = job["spec"]["template"]["spec"]
        self.assertEqual(pod["restartPolicy"], "Never")
        (container,) = pod["containers"]
        self.assertEqual(container["command"], ["artifact-keeper", "db-migrate"])
        self.assertNotIn("ports", container)
        deployment_env = backend_env(docs)
        database_url = next(e for e in deployment_env if e["name"] == "DATABASE_URL")
        self.assertEqual(container["env"], [database_url])
        self.assertIn({"name": "SKIP_MIGRATIONS", "value": "true"}, deployment_env)

    def test_job_uses_the_backend_image(self):
        docs = render({"backend": {"migrationJob": {"enabled": True}, "image": {"tag": "9.9.9"}}}, "--is-upgrade")
        (job,) = jobs(docs)
        self.assertTrue(job["spec"]["template"]["spec"]["containers"][0]["image"].endswith(":9.9.9"))

    def test_enabled_install_keeps_startup_migrations(self):
        docs = render(ENABLED)
        self.assertEqual(len(jobs(docs)), 1)
        self.assertNotIn("SKIP_MIGRATIONS", env_names(backend_env(docs)))

    def test_backend_env_skip_migrations_renders_once(self):
        values = {"backend": {"migrationJob": {"enabled": True}, "env": {"SKIP_MIGRATIONS": "false"}}}
        names = env_names(backend_env(render(values, "--is-upgrade")))
        self.assertEqual(names.count("SKIP_MIGRATIONS"), 1)
        self.assertIn({"name": "SKIP_MIGRATIONS", "value": "true"}, backend_env(render(values, "--is-upgrade")))

    def test_external_database_secret(self):
        values = {
            "backend": {"migrationJob": {"enabled": True}},
            "postgres": {"enabled": False},
            "externalDatabase": {"existingSecret": "ext-db", "existingSecretKey": "url"},
        }
        (job,) = jobs(render(values, "--is-upgrade"))
        (env,) = job["spec"]["template"]["spec"]["containers"][0]["env"]
        self.assertEqual(env["valueFrom"]["secretKeyRef"], {"name": "ext-db", "key": "url"})

    def test_deadline_and_backoff_are_configurable(self):
        values = {"backend": {"migrationJob": {"enabled": True, "activeDeadlineSeconds": 7200, "backoffLimit": 0}}}
        (job,) = jobs(render(values, "--is-upgrade"))
        self.assertEqual(job["spec"]["activeDeadlineSeconds"], 7200)
        self.assertEqual(job["spec"]["backoffLimit"], 0)


if __name__ == "__main__":
    unittest.main()
