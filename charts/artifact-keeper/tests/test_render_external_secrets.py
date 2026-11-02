"""Render tests for External Secrets Operator wiring."""

from pathlib import Path
import os
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
ESO = {"externalSecrets": {"enabled": True}}


def render(values, *args):
    result = subprocess.run(
        [os.environ.get("HELM", "helm"), "template", "ak", str(CHART), *args, "-f", "-"],
        input=yaml.safe_dump(values), capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return [d for d in yaml.safe_load_all(result.stdout) if d]


def merge(base, extra):
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def backend_env(docs):
    deploy = next(d for d in docs if d["kind"] == "Deployment"
                  and d["metadata"]["name"].endswith("-backend"))
    container = next(c for c in deploy["spec"]["template"]["spec"]["containers"]
                     if c["name"] == "backend")
    return {e["name"]: e for e in container["env"]}


def external_secret(docs):
    return next(d for d in docs if d["kind"] == "ExternalSecret")


class SmtpPasswordTests(unittest.TestCase):
    """#211: SMTP_PASSWORD must follow the ExternalSecret, not secrets.smtpPassword."""

    def test_eso_supplied_password_is_injected_without_inline_value(self):
        docs = render(merge(ESO, {
            "secrets": {"smtpPassword": ""},
            "externalSecrets": {"secrets": {"smtpPassword": "ak-secrets"}},
        }))
        mapped = [d["secretKey"] for d in external_secret(docs)["spec"]["data"]]
        self.assertIn("SMTP_PASSWORD", mapped)
        env = backend_env(docs)
        self.assertEqual(env["SMTP_PASSWORD"]["valueFrom"]["secretKeyRef"],
                         {"name": "ak-artifact-keeper-secrets", "key": "SMTP_PASSWORD"})

    def test_eso_without_smtp_path_does_not_reference_missing_key(self):
        docs = render(merge(ESO, {
            "secrets": {"smtpPassword": "inline-is-ignored-with-eso"},
            "externalSecrets": {"secrets": {"smtpPassword": ""}},
        }))
        mapped = [d["secretKey"] for d in external_secret(docs)["spec"]["data"]]
        self.assertNotIn("SMTP_PASSWORD", mapped)
        self.assertNotIn("SMTP_PASSWORD", backend_env(docs))

    def test_chart_secret_keeps_value_based_injection(self):
        args = ("--set", "secrets.jwtSecret=" + "a1B2c3D4e5F6g7H8i9J0" * 3,
                "--set", "postgres.auth.password=render-test-password")
        docs = render({"secrets": {"smtpPassword": "smtp-pass"}}, *args)
        self.assertIn("SMTP_PASSWORD", backend_env(docs))
        docs = render({}, *args)
        self.assertNotIn("SMTP_PASSWORD", backend_env(docs))



class ApiVersionTests(unittest.TestCase):
    """#271: the ExternalSecret apiVersion is configurable."""

    def test_default_is_v1(self):
        self.assertEqual(external_secret(render(ESO))["apiVersion"], "external-secrets.io/v1")

    def test_older_operator_version(self):
        docs = render(merge(ESO, {"externalSecrets": {"apiVersion": "external-secrets.io/v1beta1"}}))
        self.assertEqual(external_secret(docs)["apiVersion"], "external-secrets.io/v1beta1")

    def test_empty_falls_back_to_v1(self):
        docs = render(merge(ESO, {"externalSecrets": {"apiVersion": ""}}))
        self.assertEqual(external_secret(docs)["apiVersion"], "external-secrets.io/v1")

    def test_other_groups_fail_the_render(self):
        result = subprocess.run(
            [os.environ.get("HELM", "helm"), "template", "ak", str(CHART), "-f", "-"],
            input=yaml.safe_dump(merge(ESO, {"externalSecrets": {"apiVersion": "v1"}})),
            capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not an External Secrets Operator API version", result.stderr)


if __name__ == "__main__":
    unittest.main()
