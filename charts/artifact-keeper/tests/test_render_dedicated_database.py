"""Render tests for dedicated database mode (values-cnpg.yaml)."""

from pathlib import Path
import os
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
CHART = ROOT / "charts/artifact-keeper"
PROFILE = CHART / "values-cnpg.yaml"
JWT = "a1B2c3D4e5F6g7H8i9J0" * 3

SECRET_MODES = {
    "chart-managed": {"secrets": {"jwtSecret": JWT}},
    "existing-secret": {"secrets": {"existingSecret": "operator-secret"}},
    "external-secrets": {"externalSecrets": {"enabled": True}},
}


def render(values=None, profile=True):
    command = [os.environ.get("HELM", "helm"), "template", "dedicated", str(CHART)]
    if profile:
        command += ["-f", str(PROFILE)]
    return subprocess.run(
        command + ["-f", "-"],
        input=yaml.safe_dump(values or {}),
        capture_output=True,
        text=True,
        check=False,
    )


def documents(values=None, profile=True):
    result = render(values, profile)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def deployment(docs, suffix):
    return next(
        document
        for document in docs
        if document["kind"] == "Deployment" and document["metadata"]["name"].endswith(suffix)
    )


def pod_spec(docs, suffix):
    return deployment(docs, suffix)["spec"]["template"]["spec"]


def env_of(container):
    return {entry["name"]: entry for entry in container.get("env", [])}


def secret_ref(entry):
    return entry["valueFrom"]["secretKeyRef"]


def init_container(spec, name):
    return next(c for c in spec["initContainers"] if c["name"] == name)


def secret_key_refs(node):
    """Every secretKeyRef mapping anywhere under node."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "secretKeyRef":
                yield value
            else:
                yield from secret_key_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from secret_key_refs(value)


class SecretModes(unittest.TestCase):
    def test_every_mode_wires_each_service_to_its_own_secret(self):
        for mode, values in SECRET_MODES.items():
            with self.subTest(mode=mode):
                docs = documents(values)
                backend = pod_spec(docs, "-backend")
                dtrack = pod_spec(docs, "-dtrack")

                url = secret_ref(env_of(backend["containers"][0])["DATABASE_URL"])
                self.assertEqual(url, {"name": "ak-backend-db-app", "key": "uri"})

                env = env_of(dtrack["containers"][0])
                for name, key in (
                    ("ALPINE_DATABASE_URL", "jdbc-uri"),
                    ("ALPINE_DATABASE_USERNAME", "username"),
                    ("ALPINE_DATABASE_PASSWORD", "password"),
                ):
                    self.assertEqual(
                        secret_ref(env[name]), {"name": "ak-dtrack-db-app", "key": key}
                    )
                self.assertNotIn("_DTRACK_DB_HOST", env)

    def test_no_empty_secret_names_in_any_mode(self):
        for mode, values in SECRET_MODES.items():
            with self.subTest(mode=mode):
                for document in documents(values):
                    for ref in secret_key_refs(document):
                        self.assertTrue(ref.get("name"), document["metadata"]["name"])

    def test_wait_containers_use_each_service_uri(self):
        docs = documents(SECRET_MODES["chart-managed"])
        for suffix, secret in (("-backend", "ak-backend-db-app"), ("-dtrack", "ak-dtrack-db-app")):
            wait = init_container(pod_spec(docs, suffix), "wait-for-postgres")
            self.assertEqual(
                secret_ref(env_of(wait)["WAIT_DATABASE_URI"]), {"name": secret, "key": "uri"}
            )
            self.assertIn('pg_isready -d "$WAIT_DATABASE_URI"', wait["args"][0])

    def test_shared_secret_holds_no_database_credentials(self):
        docs = documents(SECRET_MODES["chart-managed"])
        secret = next(
            d for d in docs if d["kind"] == "Secret" and d["metadata"]["name"].endswith("-secrets")
        )
        self.assertIn("JWT_SECRET", secret["stringData"])
        self.assertNotIn("DATABASE_URL", secret["stringData"])
        self.assertNotIn("POSTGRES_PASSWORD", secret["stringData"])

    def test_external_secret_does_not_sync_database_credentials(self):
        docs = documents(SECRET_MODES["external-secrets"])
        synced = [
            entry["secretKey"]
            for d in docs
            if d["kind"] == "ExternalSecret"
            for entry in d["spec"]["data"]
        ]
        self.assertIn("JWT_SECRET", synced)
        self.assertNotIn("DATABASE_URL", synced)
        self.assertNotIn("POSTGRES_PASSWORD", synced)

    def test_key_names_can_be_remapped(self):
        docs = documents(
            {
                "secrets": {"jwtSecret": JWT},
                "backend": {"dedicatedDatabase": {"secretKeys": {"uri": "fqdn-uri"}}},
                "dependencyTrack": {
                    "dedicatedDatabase": {"secretKeys": {"jdbcUri": "fqdn-jdbc-uri", "uri": "fqdn-uri"}}
                },
            }
        )
        backend = pod_spec(docs, "-backend")
        dtrack = pod_spec(docs, "-dtrack")
        self.assertEqual(secret_ref(env_of(backend["containers"][0])["DATABASE_URL"])["key"], "fqdn-uri")
        self.assertEqual(
            secret_ref(env_of(dtrack["containers"][0])["ALPINE_DATABASE_URL"])["key"], "fqdn-jdbc-uri"
        )
        wait = init_container(dtrack, "wait-for-postgres")
        self.assertEqual(secret_ref(env_of(wait)["WAIT_DATABASE_URI"])["key"], "fqdn-uri")


class LeftoverExternalDatabase(unittest.TestCase):
    LEFTOVER = {
        "externalDatabase": {
            "enabled": False,
            "host": "old-db.example.com",
            "existingSecret": "old-db",
            "existingPasswordKey": "old-password",
            "existingHostKey": "old-host",
        },
    }

    def test_leftover_settings_cannot_mix_credentials(self):
        for mode, values in SECRET_MODES.items():
            for host in ("old-db.example.com", ""):
                with self.subTest(mode=mode, host=host):
                    leftover = yaml.safe_load(yaml.safe_dump(self.LEFTOVER))
                    leftover["externalDatabase"]["host"] = host
                    docs = documents({**values, **leftover})
                    for suffix in ("-backend", "-dtrack"):
                        rendered = yaml.safe_dump(deployment(docs, suffix))
                        self.assertNotIn("old-db", rendered)
                        self.assertNotIn("_DTRACK_DB_HOST", rendered)

    def test_leftover_host_is_not_added_to_no_proxy(self):
        docs = documents(
            {
                **SECRET_MODES["chart-managed"],
                **self.LEFTOVER,
                "global": {"proxy": {"httpProxy": "http://proxy.example.com:3128"}},
            }
        )
        no_proxy = env_of(pod_spec(docs, "-backend")["containers"][0])["NO_PROXY"]["value"]
        self.assertNotIn("old-db.example.com", no_proxy)


class Failures(unittest.TestCase):
    def assert_fails(self, values, message):
        result = render(values)
        self.assertNotEqual(result.returncode, 0, "render unexpectedly succeeded")
        self.assertIn(message, result.stderr)

    def test_missing_existing_secret_fails_in_every_mode(self):
        for mode, values in SECRET_MODES.items():
            with self.subTest(mode=mode, service="backend"):
                self.assert_fails(
                    {**values, "backend": {"dedicatedDatabase": {"existingSecret": ""}}},
                    "backend.dedicatedDatabase.existingSecret is required",
                )
            with self.subTest(mode=mode, service="dependencyTrack"):
                self.assert_fails(
                    {**values, "dependencyTrack": {"dedicatedDatabase": {"existingSecret": ""}}},
                    "dependencyTrack.dedicatedDatabase.existingSecret is required",
                )

    def test_disabled_service_needs_no_secret(self):
        docs = documents(
            {
                **SECRET_MODES["chart-managed"],
                "dependencyTrack": {"enabled": False, "dedicatedDatabase": {"existingSecret": ""}},
            }
        )
        self.assertTrue(deployment(docs, "-backend"))
        docs = documents(
            {
                **SECRET_MODES["chart-managed"],
                "backend": {"enabled": False, "dedicatedDatabase": {"existingSecret": ""}},
            }
        )
        self.assertTrue(deployment(docs, "-dtrack"))

    def test_fleet_fails_in_every_mode(self):
        for mode, values in SECRET_MODES.items():
            with self.subTest(mode=mode):
                self.assert_fails(
                    {**values, "fleet": {"enabled": True, "instanceId": "acme"}},
                    "fleet.enabled cannot be combined with dedicated database mode",
                )

    def test_schema_refuses_the_database_string_used_as_a_map(self):
        self.assert_fails(
            {**SECRET_MODES["chart-managed"], "dependencyTrack": {"database": {"existingSecret": "x"}}},
            "dependencyTrack.database",
        )


class GeneratedSecrets(unittest.TestCase):
    """The chart generates secrets.jwtSecret, and never a database credential here."""

    def shared_secret(self, values=None):
        docs = documents(values)
        return next(
            document
            for document in docs
            if document["kind"] == "Secret"
            and document["metadata"]["name"] == "dedicated-artifact-keeper-secrets"
        )

    def test_profile_alone_renders_and_generates_only_the_jwt_secret(self):
        data = self.shared_secret()["stringData"]
        self.assertEqual(len(data["JWT_SECRET"]), 64)
        self.assertNotIn("POSTGRES_PASSWORD", data)
        self.assertNotIn("DATABASE_URL", data)

    def test_supplied_jwt_secret_wins(self):
        data = self.shared_secret({"secrets": {"jwtSecret": JWT}})["stringData"]
        self.assertEqual(data["JWT_SECRET"], JWT)

    def test_leftover_database_values_do_not_reach_the_shared_secret(self):
        data = self.shared_secret(
            {
                "postgres": {"auth": {"password": "leftover"}},
                "externalDatabase": {"host": "db", "username": "u", "password": "leftover"},
            }
        )["stringData"]
        self.assertNotIn("POSTGRES_PASSWORD", data)
        self.assertNotIn("DATABASE_URL", data)
        self.assertNotIn("leftover", yaml.safe_dump(data))

    def test_generate_false_still_requires_the_jwt_secret(self):
        result = render({"secrets": {"generate": False}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("secrets.jwtSecret is required", result.stderr)

    def test_missing_dedicated_secret_fails_with_generated_jwt(self):
        result = render({"backend": {"dedicatedDatabase": {"existingSecret": ""}}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("backend.dedicatedDatabase.existingSecret is required", result.stderr)


class OtherModesUnchanged(unittest.TestCase):
    def test_postgres_disabled_alone_stays_on_external_database(self):
        docs = documents(
            {
                "secrets": {"jwtSecret": JWT},
                "postgres": {"enabled": False},
                "externalDatabase": {"host": "db.example.com", "username": "u", "password": "p"},
            },
            profile=False,
        )
        backend = pod_spec(docs, "-backend")
        self.assertEqual(
            secret_ref(env_of(backend["containers"][0])["DATABASE_URL"]),
            {"name": "dedicated-artifact-keeper-secrets", "key": "DATABASE_URL"},
        )
        self.assertNotIn("wait-for-postgres", [c["name"] for c in backend["initContainers"]])

    def test_externaldatabase_disabled_is_ignored_with_in_cluster_postgres(self):
        docs = documents(
            {
                "secrets": {"jwtSecret": JWT},
                "postgres": {"enabled": True, "auth": {"password": "p"}},
                "externalDatabase": {"enabled": False},
            },
            profile=False,
        )
        wait = init_container(pod_spec(docs, "-backend"), "wait-for-postgres")
        self.assertNotIn("env", wait)


if __name__ == "__main__":
    unittest.main()
