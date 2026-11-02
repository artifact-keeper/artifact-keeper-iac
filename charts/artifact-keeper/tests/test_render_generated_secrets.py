"""Render tests for the generated JWT secret and Postgres password (#317)."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import urlsplit

import yaml


CHART = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM", "helm")
SECRET = "ak-artifact-keeper-secrets"
JWT = "a1B2c3D4e5F6g7H8i9J0" * 3
LOOKUP = re.compile(r'lookup "v1" "Secret" \.root\.Release\.Namespace \(include "artifact-keeper\.secretName" \.root\)')


def run(values=None, chart=CHART, files=()):
    args = [HELM, "template", "ak", str(chart)]
    for name in files:
        args += ["-f", str(chart / name)]
    return subprocess.run(
        args + ["-f", "-"], input=yaml.safe_dump(values or {}), capture_output=True, text=True,
    )


def render(values=None, chart=CHART, files=()):
    result = run(values, chart, files)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def chart_secret(docs):
    return next(
        (d for d in docs if d["kind"] == "Secret" and d["metadata"]["name"] == SECRET),
        None,
    )


def workload(docs, kind, name):
    return next(d for d in docs if d["kind"] == kind and d["metadata"]["name"] == name)


def secret_ref(doc, container, env_name):
    pod = doc["spec"]["template"]["spec"]
    env = next(c for c in pod["containers"] if c["name"] == container)["env"]
    return next(e for e in env if e["name"] == env_name)["valueFrom"]["secretKeyRef"]


def chart_copy(tmp):
    chart = Path(tmp) / "artifact-keeper"
    shutil.copytree(CHART, chart, ignore=shutil.ignore_patterns("tests"))
    return chart


def notes(values=None, files=()):
    """`helm template` skips NOTES.txt, so render a copy wrapped in a ConfigMap."""
    with tempfile.TemporaryDirectory() as tmp:
        chart = chart_copy(tmp)
        body = (chart / "templates/NOTES.txt").read_text()
        (chart / "templates/NOTES.txt").unlink()
        (chart / "templates/notes-test.yaml").write_text(
            "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: notes\ndata:\n  notes: |\n"
            + "".join(f"    {line}\n" for line in body.splitlines())
        )
        docs = render(values, chart, files)
        return next(d for d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "notes")["data"]["notes"]


def render_with_stored_secret(stored, values=None):
    """Render as if lookup found `stored`, which `helm template` can't do.

    The real lookup is covered by the chart-testing install and upgrade in CI;
    this pins the order the chart resolves values in.
    """
    with tempfile.TemporaryDirectory() as tmp:
        chart = chart_copy(tmp)
        helpers = chart / "templates/_helpers.tpl"
        data = " ".join(f'"{k}" ("{v}" | b64enc)' for k, v in stored.items())
        text, count = LOOKUP.subn(f'dict "data" (dict {data})', helpers.read_text())
        assert count == 1, "the lookup in artifact-keeper.generatedSecret moved"
        helpers.write_text(text)
        return chart_secret(render(values, chart))["stringData"]


class GeneratedSecretsTests(unittest.TestCase):
    def test_default_values_render_with_no_input(self):
        data = chart_secret(render())["stringData"]
        self.assertTrue(data["JWT_SECRET"])
        self.assertTrue(data["POSTGRES_PASSWORD"])

    def test_jwt_secret_meets_the_backend_requirements(self):
        secret = chart_secret(render())["stringData"]["JWT_SECRET"]
        # backend/src/config.rs: at least 32 characters and 128 estimated bits.
        self.assertEqual(len(secret), 64)
        self.assertRegex(secret, r"^[A-Za-z0-9]+$")

    def test_password_is_the_same_everywhere_in_one_render(self):
        for _ in range(3):
            docs = render()
            data = chart_secret(docs)["stringData"]
            password = data["POSTGRES_PASSWORD"]
            self.assertRegex(password, r"^[A-Za-z0-9]{32}$")
            self.assertEqual(urlsplit(data["DATABASE_URL"]).password, password)

    def test_workloads_read_the_one_secret(self):
        docs = render()
        backend = workload(docs, "Deployment", "ak-artifact-keeper-backend")
        postgres = workload(docs, "StatefulSet", "ak-artifact-keeper-postgres")
        self.assertEqual(secret_ref(backend, "backend", "DATABASE_URL"), {"name": SECRET, "key": "DATABASE_URL"})
        self.assertEqual(secret_ref(backend, "backend", "JWT_SECRET"), {"name": SECRET, "key": "JWT_SECRET"})
        self.assertEqual(secret_ref(postgres, "postgres", "POSTGRES_PASSWORD"), {"name": SECRET, "key": "POSTGRES_PASSWORD"})

    def test_offline_renders_generate_new_values(self):
        # The documented GitOps trap: no lookup, so nothing is stable. If this
        # ever changes, the warnings in the README and NOTES.txt need revisiting.
        first = chart_secret(render())["stringData"]
        second = chart_secret(render())["stringData"]
        self.assertNotEqual(first["JWT_SECRET"], second["JWT_SECRET"])
        self.assertNotEqual(first["POSTGRES_PASSWORD"], second["POSTGRES_PASSWORD"])

    def test_generated_values_are_not_dumped_outside_the_secret(self):
        docs = render()
        data = chart_secret(docs)["stringData"]
        others = yaml.safe_dump_all([d for d in docs if d is not chart_secret(docs)])
        self.assertNotIn(data["JWT_SECRET"], others)
        self.assertNotIn(data["POSTGRES_PASSWORD"], others)


class SuppliedValuesTests(unittest.TestCase):
    def test_supplied_values_win(self):
        data = chart_secret(render({
            "secrets": {"jwtSecret": JWT}, "postgres": {"auth": {"password": "supplied"}},
        }))["stringData"]
        self.assertEqual(data["JWT_SECRET"], JWT)
        self.assertEqual(data["POSTGRES_PASSWORD"], "supplied")
        self.assertEqual(urlsplit(data["DATABASE_URL"]).password, "supplied")

    def test_supplying_one_still_generates_the_other(self):
        data = chart_secret(render({"secrets": {"jwtSecret": JWT}}))["stringData"]
        self.assertEqual(data["JWT_SECRET"], JWT)
        self.assertRegex(data["POSTGRES_PASSWORD"], r"^[A-Za-z0-9]{32}$")

    def test_external_database_is_not_given_a_generated_password(self):
        data = chart_secret(render({
            "postgres": {"enabled": False},
            "externalDatabase": {"host": "db", "username": "u", "password": "external"},
        }))["stringData"]
        self.assertEqual(data["POSTGRES_PASSWORD"], "external")
        self.assertEqual(urlsplit(data["DATABASE_URL"]).password, "external")
        self.assertRegex(data["JWT_SECRET"], r"^[A-Za-z0-9]{64}$")

    def test_existing_secret_renders_no_secret(self):
        docs = render({"secrets": {"existingSecret": "mine"}})
        self.assertIsNone(chart_secret(docs))
        backend = workload(docs, "Deployment", "ak-artifact-keeper-backend")
        self.assertEqual(secret_ref(backend, "backend", "JWT_SECRET")["name"], "mine")

    def test_external_secrets_renders_no_secret(self):
        docs = render({"externalSecrets": {"enabled": True}})
        self.assertIsNone(chart_secret(docs))
        self.assertTrue([d for d in docs if d["kind"] == "ExternalSecret"])


class StoredValueTests(unittest.TestCase):
    STORED = {"JWT_SECRET": "stored-jwt", "POSTGRES_PASSWORD": "stored-password"}

    def test_stored_values_are_kept(self):
        data = render_with_stored_secret(self.STORED)
        self.assertEqual(data["JWT_SECRET"], "stored-jwt")
        self.assertEqual(data["POSTGRES_PASSWORD"], "stored-password")
        self.assertEqual(urlsplit(data["DATABASE_URL"]).password, "stored-password")

    def test_supplied_value_beats_the_stored_one(self):
        data = render_with_stored_secret(self.STORED, {"postgres": {"auth": {"password": "new"}}})
        self.assertEqual(data["POSTGRES_PASSWORD"], "new")
        self.assertEqual(urlsplit(data["DATABASE_URL"]).password, "new")
        self.assertEqual(data["JWT_SECRET"], "stored-jwt")

    def test_secret_without_the_key_gets_a_generated_value(self):
        data = render_with_stored_secret({"JWT_SECRET": "stored-jwt"})
        self.assertEqual(data["JWT_SECRET"], "stored-jwt")
        self.assertRegex(data["POSTGRES_PASSWORD"], r"^[A-Za-z0-9]{32}$")


class FailFastTests(unittest.TestCase):
    def assert_fails(self, result, *expected):
        self.assertNotEqual(result.returncode, 0)
        for text in expected:
            self.assertIn(text, result.stderr)

    def test_generate_false_fails_on_a_missing_value(self):
        self.assert_fails(run({"secrets": {"generate": False}}), "secrets.jwtSecret is required")
        self.assert_fails(
            run({"secrets": {"generate": False, "jwtSecret": JWT}}), "postgres.auth.password is required",
        )

    def test_generate_false_accepts_supplied_values(self):
        data = chart_secret(render({
            "secrets": {"generate": False, "jwtSecret": JWT}, "postgres": {"auth": {"password": "supplied"}},
        }))["stringData"]
        self.assertEqual(data["JWT_SECRET"], JWT)

    def test_unset_generate_means_on(self):
        # helm upgrade --reuse-values from a chart without the key leaves it unset.
        data = chart_secret(render({"secrets": {"generate": None}}))["stringData"]
        self.assertRegex(data["JWT_SECRET"], r"^[A-Za-z0-9]{64}$")

    def test_schema_refuses_a_non_boolean(self):
        self.assert_fails(run({"secrets": {"generate": "false"}}), "generate")

    def test_production_and_staging_still_fail_fast(self):
        self.assert_fails(
            run({"externalSecrets": {"enabled": False}}, files=["values-production.yaml"]),
            "secrets.jwtSecret is required",
        )
        self.assert_fails(run(files=["values-staging.yaml"]), "secrets.jwtSecret is required")

    def test_opensearch_password_is_still_required(self):
        self.assert_fails(
            run({"opensearch": {"disableSecurityPlugin": False}}), "opensearch.auth.password is required",
        )


class NotesTests(unittest.TestCase):
    HEADING = "Generated credentials:"

    def test_default_install_names_both_and_warns_about_gitops(self):
        text = notes()
        self.assertIn(f"{self.HEADING} secrets.jwtSecret, postgres.auth.password", text)
        self.assertIn(SECRET, text)
        self.assertIn("Argo CD", text)
        self.assertIn("PostgreSQL password mismatch", text)

    def test_names_only_what_is_generated(self):
        self.assertIn(f"{self.HEADING} postgres.auth.password\n", notes({"secrets": {"jwtSecret": JWT}}))

    def test_quiet_when_nothing_is_generated(self):
        for values in (
            {"secrets": {"jwtSecret": JWT}, "postgres": {"auth": {"password": "supplied"}}},
            {"secrets": {"existingSecret": "mine"}},
            {"externalSecrets": {"enabled": True}},
        ):
            with self.subTest(values=values):
                self.assertNotIn(self.HEADING, notes(values))


class DocumentationTests(unittest.TestCase):
    def test_readme_keeps_the_gitops_warning(self):
        readme = (CHART / "README.md").read_text()
        self.assertIn("#### Generated credentials", readme)
        self.assertIn("### Recovering a PostgreSQL password mismatch", readme)

    def test_ci_install_exercises_generation(self):
        values = yaml.safe_load((CHART / "ci/test-values.yaml").read_text())
        self.assertNotIn("jwtSecret", values["secrets"])
        self.assertNotIn("password", values["postgres"]["auth"])


if __name__ == "__main__":
    unittest.main()
