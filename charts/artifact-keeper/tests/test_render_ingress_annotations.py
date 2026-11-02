"""Render tests for the nginx proxy annotations on the Ingress (#326)."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM", "helm")
BODY = "nginx.ingress.kubernetes.io/proxy-body-size"
READ = "nginx.ingress.kubernetes.io/proxy-read-timeout"
SEND = "nginx.ingress.kubernetes.io/proxy-send-timeout"
DEFAULTS = {BODY: "1024m", READ: "300", SEND: "300"}


def run(chart, ingress):
    values = {"secrets": {"existingSecret": "ingress-render-test"}, "ingress": {"enabled": True, **ingress}}
    return subprocess.run(
        [HELM, "template", "ak", str(chart), "-f", "-"],
        input=yaml.safe_dump(values), capture_output=True, text=True,
    )


def annotations(**ingress):
    result = run(CHART, ingress)
    if result.returncode:
        raise AssertionError(result.stderr)
    doc = next(d for d in yaml.safe_load_all(result.stdout) if d and d["kind"] == "Ingress")
    return doc["metadata"].get("annotations") or {}


def notes(**ingress):
    """`helm template` skips NOTES.txt, so render a copy wrapped in a ConfigMap."""
    with tempfile.TemporaryDirectory() as tmp:
        chart = Path(tmp) / "artifact-keeper"
        shutil.copytree(CHART, chart)
        body = (chart / "templates/NOTES.txt").read_text()
        (chart / "templates/NOTES.txt").unlink()
        (chart / "templates/notes-test.yaml").write_text(
            "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: notes\ndata:\n  notes: |\n"
            + "".join(f"    {line}\n" for line in body.splitlines())
        )
        result = run(chart, ingress)
        if result.returncode:
            raise AssertionError(result.stderr)
        doc = next(
            d for d in yaml.safe_load_all(result.stdout)
            if d and d["kind"] == "ConfigMap" and d["metadata"]["name"] == "notes"
        )
        return doc["data"]["notes"]


class IngressAnnotationTests(unittest.TestCase):
    def test_nginx_class_keeps_the_derived_annotations(self):
        self.assertEqual(annotations(), DEFAULTS)
        self.assertEqual(annotations(className="nginx", nginxAnnotations=False), DEFAULTS)

    def test_other_class_gets_none_by_default(self):
        self.assertEqual(annotations(className="nginx-internal"), {})
        self.assertEqual(annotations(className=""), {})

    def test_other_class_can_opt_in(self):
        self.assertEqual(annotations(className="nginx-internal", nginxAnnotations=True), DEFAULTS)
        self.assertEqual(annotations(className="", nginxAnnotations=True), DEFAULTS)

    def test_dedicated_values_reach_the_opted_in_class(self):
        rendered = annotations(
            className="nginx-internal", nginxAnnotations=True,
            maxBodySize="0", proxyReadTimeoutSeconds=1800, proxySendTimeoutSeconds=None,
        )
        self.assertEqual(rendered, {BODY: "0", READ: "1800"})

    def test_explicit_annotation_wins(self):
        rendered = annotations(
            className="nginx-internal", nginxAnnotations=True, annotations={BODY: "5g", "custom": "kept"},
        )
        self.assertEqual(rendered, {**DEFAULTS, BODY: "5g", "custom": "kept"})

    def test_schema_refuses_a_non_boolean(self):
        result = run(CHART, {"nginxAnnotations": "true"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("nginxAnnotations", result.stderr)


class IngressNotesTests(unittest.TestCase):
    WARNING = "so ingress.maxBodySize"

    def test_warns_when_the_annotations_are_dropped(self):
        text = notes(className="nginx-internal")
        self.assertIn('ingress.className is "nginx-internal"', text)
        self.assertIn(f"Not rendered: {BODY}, {READ}, {SEND}", text)
        self.assertIn("ingress.nginxAnnotations=true", text)

    def test_warns_when_the_class_is_unset(self):
        self.assertIn('ingress.className is "unset"', notes(className=""))

    def test_quiet_when_they_render(self):
        self.assertNotIn(self.WARNING, notes())
        self.assertNotIn(self.WARNING, notes(className="nginx-internal", nginxAnnotations=True))

    def test_quiet_when_the_ingress_is_off(self):
        self.assertNotIn(self.WARNING, notes(enabled=False, className="traefik"))

    def test_quiet_when_nothing_is_lost(self):
        self.assertNotIn(self.WARNING, notes(
            className="traefik", maxBodySize="", proxyReadTimeoutSeconds=None, proxySendTimeoutSeconds=None,
        ))

    def test_annotation_set_by_hand_is_not_reported(self):
        text = notes(className="nginx-internal", annotations={BODY: "5g"})
        self.assertIn(f"Not rendered: {READ}, {SEND}", text)


if __name__ == "__main__":
    unittest.main()
