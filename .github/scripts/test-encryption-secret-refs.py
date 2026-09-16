#!/usr/bin/env python3
"""Offline Helm regression tests for optional backend encryption key references."""

import itertools
import os
from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[2] / "charts" / "artifact-keeper"
KEYS = {
    "migrationEncryptionKey": "MIGRATION_ENCRYPTION_KEY",
    "webhookSecretKey": "AK_WEBHOOK_SECRET_KEY",
}
HELM = os.environ.get("HELM_BIN", "helm")


def render(values):
    return subprocess.run(
        [
            HELM, "template", "ak", str(CHART),
            "--set", "secrets.jwtSecret=test-only-jwt",
            "--set", "postgres.auth.password=test-only-postgres",
            "--set", "dependencyTrack.adminPassword=test-only-dtrack",
            "--values", "-",
        ],
        input=yaml.safe_dump(values),
        text=True,
        capture_output=True,
        check=False,
    )


class EncryptionSecretRefsTest(unittest.TestCase):
    def manifests(self, values):
        result = render(values)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [doc for doc in yaml.safe_load_all(result.stdout) if doc]

    def backend_env(self, docs):
        deployment = next(
            doc for doc in docs
            if doc["kind"] == "Deployment"
            and doc["metadata"]["name"] == "ak-artifact-keeper-backend"
        )
        container = next(
            item for item in deployment["spec"]["template"]["spec"]["containers"]
            if item["name"] == "backend"
        )
        entries = container["env"]
        names = [entry["name"] for entry in entries]
        self.assertEqual(len(names), len(set(names)), "duplicate env names")
        return {entry["name"]: entry for entry in entries}

    def assert_ref(self, env, name, secret, key=None, optional=None):
        ref = {"name": secret, "key": key or name}
        if optional is not None:
            ref["optional"] = optional
        self.assertEqual(
            env[name], {"name": name, "valueFrom": {"secretKeyRef": ref}}
        )

    def assert_no_secret_resources(self, docs):
        self.assertFalse(
            any(doc["kind"] in ("Secret", "ExternalSecret") for doc in docs)
        )

    def assert_error(self, values, message):
        result = render(values)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_existing_secret_without_flags_keeps_optional_keys_absent(self):
        docs = self.manifests({"secrets": {"existingSecret": "app-credentials"}})
        env = self.backend_env(docs)
        self.assert_no_secret_resources(docs)
        self.assert_ref(env, "JWT_SECRET", "app-credentials")
        self.assert_ref(env, "DATABASE_URL", "app-credentials")
        for name in KEYS.values():
            self.assertNotIn(name, env)

    def test_existing_secret_flags_are_independent_and_only_render_references(self):
        for enabled in itertools.product((False, True), repeat=2):
            with self.subTest(enabled=enabled):
                secrets = {"existingSecret": "app-credentials"}
                secrets.update(
                    (key + "Enabled", flag) for key, flag in zip(KEYS, enabled)
                )
                docs = self.manifests({"secrets": secrets})
                env = self.backend_env(docs)
                self.assert_no_secret_resources(docs)
                for name, flag in zip(KEYS.values(), enabled):
                    if flag:
                        self.assert_ref(env, name, "app-credentials")
                    else:
                        self.assertNotIn(name, env)
                rendered = yaml.safe_dump_all(docs)
                for key in KEYS:
                    self.assertNotIn(key + "Enabled", rendered)

    def test_chart_managed_inline_values_keep_original_behavior(self):
        for enabled in itertools.product((False, True), repeat=2):
            with self.subTest(enabled=enabled):
                secrets = {
                    key: "test-only-" + key
                    for key, flag in zip(KEYS, enabled) if flag
                }
                docs = self.manifests({"secrets": secrets})
                env = self.backend_env(docs)
                secret = next(doc for doc in docs if doc["kind"] == "Secret")
                self.assertEqual(
                    secret["metadata"]["name"], "ak-artifact-keeper-secrets"
                )
                for key, flag in zip(KEYS, enabled):
                    name = KEYS[key]
                    if flag:
                        self.assertEqual(secret["stringData"][name], secrets[key])
                        self.assert_ref(env, name, "ak-artifact-keeper-secrets")
                    else:
                        self.assertNotIn(name, secret["stringData"])
                        self.assertNotIn(name, env)

    def test_existing_secret_legacy_values_still_enable_refs_without_leaking(self):
        for flag in (False, True):
            with self.subTest(flag=flag):
                secrets = {"existingSecret": "app-credentials"}
                for key in KEYS:
                    secrets[key] = "unused-placeholder-" + key
                    secrets[key + "Enabled"] = flag
                docs = self.manifests({"secrets": secrets})
                env = self.backend_env(docs)
                self.assert_no_secret_resources(docs)
                for key, name in KEYS.items():
                    self.assert_ref(env, name, "app-credentials")
                    self.assertNotIn(secrets[key], yaml.safe_dump_all(docs))

    def test_eso_paths_control_injection_and_inline_values_remain_ignored(self):
        for enabled in itertools.product((False, True), repeat=2):
            with self.subTest(enabled=enabled):
                paths = {
                    key: "provider/" + key
                    for key, flag in zip(KEYS, enabled) if flag
                }
                docs = self.manifests({
                    "secrets": {key: "ignored-inline-" + key for key in KEYS},
                    "externalSecrets": {"enabled": True, "secrets": paths},
                })
                env = self.backend_env(docs)
                self.assertFalse(any(doc["kind"] == "Secret" for doc in docs))
                external = next(
                    doc for doc in docs if doc["kind"] == "ExternalSecret"
                )
                data = {
                    entry["secretKey"]: entry for entry in external["spec"]["data"]
                }
                for key, flag in zip(KEYS, enabled):
                    name = KEYS[key]
                    if flag:
                        self.assert_ref(env, name, "ak-artifact-keeper-secrets")
                        self.assertEqual(data[name]["remoteRef"]["key"], paths[key])
                    else:
                        self.assertNotIn(name, data)
                        self.assertNotIn(name, env)
                self.assertNotIn("ignored-inline-", yaml.safe_dump_all(docs))

    def test_custom_key_names_and_optional_refs_use_environment_secrets(self):
        for optional in (None, False, True):
            with self.subTest(optional=optional):
                entries = []
                for key, name in KEYS.items():
                    ref = {"name": "encryption-credentials", "key": key}
                    if optional is not None:
                        ref["optional"] = optional
                    entries.append({"name": name, "secretKeyRef": ref})
                docs = self.manifests({
                    "secrets": {"existingSecret": "app-credentials"},
                    "backend": {"environmentSecrets": entries},
                })
                env = self.backend_env(docs)
                self.assert_no_secret_resources(docs)
                for key, name in KEYS.items():
                    self.assert_ref(
                        env, name, "encryption-credentials", key, optional
                    )

    def test_different_keys_can_use_different_sources(self):
        docs = self.manifests({
            "secrets": {
                "existingSecret": "app-credentials",
                "migrationEncryptionKeyEnabled": True,
            },
            "backend": {"environmentSecrets": [{
                "name": "AK_WEBHOOK_SECRET_KEY",
                "secretKeyRef": {"name": "webhook-credentials", "key": "custom-key"},
            }]},
        })
        env = self.backend_env(docs)
        self.assert_ref(env, "MIGRATION_ENCRYPTION_KEY", "app-credentials")
        self.assert_ref(env, "AK_WEBHOOK_SECRET_KEY", "webhook-credentials", "custom-key")

    def test_backend_env_alone_still_works(self):
        values = {name: "test-only-" + key for key, name in KEYS.items()}
        env = self.backend_env(self.manifests({"backend": {"env": values}}))
        for name, value in values.items():
            self.assertEqual(env[name], {"name": name, "value": value})

    def test_flags_require_booleans(self):
        for key, value in itertools.product(
            KEYS, ("false", "true", "", 0, 1, [], {}, None)
        ):
            with self.subTest(key=key, value=value):
                self.assert_error(
                    {"secrets": {
                        "existingSecret": "app-credentials",
                        key + "Enabled": value,
                    }},
                    "secrets." + key + "Enabled must be a boolean",
                )

    def test_flags_require_existing_secret_without_eso(self):
        for key, eso, existing in itertools.product(
            KEYS, (False, True), ("", "app-credentials")
        ):
            if existing and not eso:
                continue
            with self.subTest(key=key, eso=eso, existing=existing):
                self.assert_error({
                    "secrets": {
                        "existingSecret": existing,
                        key + "Enabled": True,
                    },
                    "externalSecrets": {"enabled": eso},
                }, "requires secrets.existingSecret and externalSecrets.enabled=false")

    def test_automatic_refs_reject_manual_env_conflicts(self):
        for key, mode, manual in itertools.product(
            KEYS, ("flag", "inline", "legacy", "eso"), ("env", "environmentSecrets")
        ):
            with self.subTest(key=key, mode=mode, manual=manual):
                name = KEYS[key]
                values = {"secrets": {}, "backend": {}}
                if mode in ("flag", "legacy"):
                    values["secrets"]["existingSecret"] = "app-credentials"
                if mode == "flag":
                    values["secrets"][key + "Enabled"] = True
                elif mode in ("inline", "legacy"):
                    values["secrets"][key] = "test-only-inline"
                else:
                    values["externalSecrets"] = {
                        "enabled": True, "secrets": {key: "provider/key"},
                    }
                if manual == "env":
                    values["backend"]["env"] = {name: "test-only-env"}
                else:
                    values["backend"]["environmentSecrets"] = [{
                        "name": name,
                        "secretKeyRef": {"name": "other-credentials", "key": "key"},
                    }]
                self.assert_error(values, name + " has multiple definitions")

    def test_manual_refs_reject_duplicates_and_plaintext_conflicts(self):
        for name, conflict in itertools.product(KEYS.values(), ("env", "duplicate")):
            with self.subTest(name=name, conflict=conflict):
                entry = {
                    "name": name,
                    "secretKeyRef": {"name": "encryption-credentials", "key": "key"},
                }
                backend = {"environmentSecrets": [entry]}
                if conflict == "env":
                    backend["env"] = {name: "test-only-env"}
                else:
                    backend["environmentSecrets"].append(entry)
                self.assert_error(
                    {"backend": backend}, name + " has multiple definitions"
                )

    def test_disabled_backend_does_not_inject_encryption_refs(self):
        docs = self.manifests({
            "backend": {"enabled": False},
            "secrets": {
                "existingSecret": "app-credentials",
                "migrationEncryptionKeyEnabled": True,
                "webhookSecretKeyEnabled": True,
            },
        })
        self.assert_no_secret_resources(docs)
        self.assertFalse(any(
            doc["kind"] == "Deployment"
            and doc["metadata"]["name"] == "ak-artifact-keeper-backend"
            for doc in docs
        ))


if __name__ == "__main__":
    unittest.main()
