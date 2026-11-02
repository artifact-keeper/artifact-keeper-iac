"""Render and real HTTP/TLS bootstrap regressions for managed DT keys (#299)."""
import base64
import http.server
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import unittest
import urllib.parse

import yaml

CHART = Path(__file__).resolve().parents[1]
MANAGED = {"dependencyTrack": {"existingApiKeySecret": "ak-dtrack-key",
           "bootstrap": {"manageApiKeySecret": True}}}
NEW_KEY = "new-dtrack-key-1234567890"
OLD_KEY = "existing-dtrack-key-1234567890"


def run_helm(values):
    return subprocess.run(
        [os.environ.get("HELM", "helm"), "template", "ak", str(CHART),
         "--namespace", "test", "--set", "secrets.existingSecret=render-test", "-f", "-"],
        input=yaml.safe_dump(values), text=True, capture_output=True,
    )


def render(values):
    result = run_helm(values)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [d for d in yaml.safe_load_all(result.stdout) if d]


def named(docs, kind, suffix):
    return next(d for d in docs if d["kind"] == kind
                and d["metadata"]["name"].endswith(suffix))


class ManagedSecretRenderTests(unittest.TestCase):
    def test_managed_key_uses_scoped_rbac_and_no_shared_pvc(self):
        docs = render(MANAGED)
        role = named(docs, "Role", "-dtrack-bootstrap")
        self.assertEqual(role["rules"], [
            {"apiGroups": [""], "resources": ["secrets"], "verbs": ["create"]},
            {"apiGroups": [""], "resources": ["secrets"], "verbs": ["get"],
             "resourceNames": ["ak-dtrack-key"]}])
        binding = named(docs, "RoleBinding", "-dtrack-bootstrap")
        self.assertEqual(binding["subjects"][0]["namespace"], "test")
        self.assertEqual(binding["roleRef"]["name"], role["metadata"]["name"])
        for kind in ("Role", "RoleBinding", "ServiceAccount"):
            self.assertEqual(named(docs, kind, "-dtrack-bootstrap")["metadata"]
                             ["annotations"]["argocd.argoproj.io/sync-wave"], "-1")
        backend = named(docs, "Deployment", "-backend")["spec"]["template"]["spec"]
        env = next(c for c in backend["containers"] if c["name"] == "backend")["env"]
        self.assertIn({"name": "DEPENDENCY_TRACK_API_KEY", "valueFrom": {
            "secretKeyRef": {"name": "ak-dtrack-key", "key": "API_KEY"}}}, env)
        self.assertNotIn("shared-config", {v["name"] for v in backend["volumes"]})
        self.assertFalse(any(d["kind"] == "PersistentVolumeClaim"
                             and d["metadata"]["name"].endswith("-shared-config")
                             for d in docs))
        self.assertFalse(any(d["kind"] == "Secret"
                             and d["metadata"]["name"] == "ak-dtrack-key" for d in docs))

    def test_sync_job_can_start_before_secret_and_helm_wait(self):
        job = named(render(MANAGED), "Job", "-dtrack-init-1")
        annotations = job["metadata"]["annotations"]
        self.assertEqual(annotations["argocd.argoproj.io/hook"], "Sync")
        self.assertEqual(annotations["argocd.argoproj.io/sync-wave"], "0")
        self.assertNotIn("helm.sh/hook", annotations)
        pod = job["spec"]["template"]["spec"]
        self.assertTrue(pod["automountServiceAccountToken"])
        self.assertTrue(pod["serviceAccountName"].endswith("-dtrack-bootstrap"))
        volume = next(v for v in pod["volumes"] if v["name"] == "existing-api-key")
        self.assertTrue(volume["secret"]["optional"])
        self.assertEqual(volume["secret"]["items"], [{"key": "API_KEY", "path": "api-key"}])
        self.assertNotIn("shared-config", {v["name"] for v in pod["volumes"]})
        self.assertNotIn("DEPENDENCY_TRACK_API_KEY_FILE",
                         {e["name"] for e in pod["containers"][0]["env"]})

    def test_legacy_and_external_secret_modes_keep_existing_contract(self):
        for values, has_pvc in (({}, True),
                               ({"dependencyTrack": {"existingApiKeySecret": "external"}}, False)):
            with self.subTest(values=values):
                docs = render(values)
                job = named(docs, "Job", "-dtrack-init")
                self.assertEqual(job["metadata"]["annotations"]["helm.sh/hook"],
                                 "post-install,post-upgrade")
                pod = job["spec"]["template"]["spec"]
                self.assertFalse(pod["automountServiceAccountToken"])
                self.assertNotIn("serviceAccountName", pod)
                self.assertEqual("shared-config" in {v["name"] for v in pod["volumes"]}, has_pvc)
                self.assertFalse(any(d["kind"] in ("Role", "RoleBinding")
                                     and d["metadata"]["name"].endswith("-dtrack-bootstrap")
                                     for d in docs))

    def test_invalid_configuration_fails_at_render_time(self):
        for settings, message in (({}, "valid existingApiKeySecret"),
                                  ({"existingApiKeySecret": 'bad"name'}, "valid existingApiKeySecret"),
                                  ({"existingApiKeySecret": "key", "existingApiKeySecretKey": "other"},
                                   "existingApiKeySecretKey=API_KEY"),
                                  ({"existingApiKeySecret": "key", "bootstrap": {
                                      "enabled": False, "manageApiKeySecret": True}}, "bootstrap.enabled=true")):
            values = {"dependencyTrack": {"bootstrap": {"manageApiKeySecret": True}, **settings}}
            with self.subTest(settings=settings):
                result = run_helm(values)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)


class BootstrapScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cert_dir = tempfile.TemporaryDirectory()
        cls.cert = Path(cls.cert_dir.name) / "ca.crt"
        cls.key = Path(cls.cert_dir.name) / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(cls.key), "-out", str(cls.cert), "-days", "1",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"],
                       check=True, capture_output=True)
        cls.script = named(render(MANAGED), "ConfigMap", "-dtrack-init")["data"]["init-dtrack.sh"]

    @classmethod
    def tearDownClass(cls):
        cls.cert_dir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.projected_key = self.root / "projected-key"
        self.secret = None
        self.read_status = None
        self.create_status = 201
        self.requests = []
        self.generated = 0
        self.change_password = False
        self.password_changed = False
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def handle_request(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                owner.requests.append((self.command, self.path, body, dict(self.headers)))
                status, payload = 200, {}
                if self.path == "/api/version":
                    payload = {"version": "4.11.4"}
                elif self.path == "/api/v1/user/login":
                    form = urllib.parse.parse_qs(body.decode())
                    if form.get("password") != ["test-password&=+%"]:
                        status = 401
                    elif owner.change_password and not owner.password_changed:
                        status = 401
                    else:
                        payload = "test-dtrack-session-token"
                elif self.path == "/api/v1/user/forceChangePassword":
                    owner.password_changed = True
                elif self.path == "/api/v1/team":
                    payload = [{"uuid": "11111111-1111-1111-1111-111111111111", "name": "Automation"}]
                elif self.path.endswith("/key") and self.command == "PUT":
                    owner.generated += 1
                    payload = {"key": NEW_KEY}
                elif self.path == "/api/v1/namespaces/test/secrets/ak-dtrack-key":
                    status = owner.read_status or (200 if owner.secret is not None else 404)
                elif self.path == "/api/v1/namespaces/test/secrets" and self.command == "POST":
                    status = owner.create_status
                    if status == 201:
                        owner.secret = json.loads(body)
                    elif status == 409:
                        owner.existing_secret(OLD_KEY)
                else:
                    status = 500
                self.send_response(status)
                self.end_headers()
                if isinstance(payload, str):
                    self.wfile.write(payload.encode())
                else:
                    self.wfile.write(json.dumps(payload, separators=(",", ":")).encode())

            do_GET = do_POST = do_PUT = handle_request

        self.dt = http.server.ThreadingHTTPServer(("localhost", 0), Handler)
        self.kube = http.server.ThreadingHTTPServer(("localhost", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.cert, self.key)
        self.kube.socket = context.wrap_socket(self.kube.socket, server_side=True)
        for server in (self.dt, self.kube):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        sa = self.root / "serviceaccount"
        sa.mkdir()
        (sa / "namespace").write_text("test")
        (sa / "token").write_text("test-kubernetes-token")
        (sa / "ca.crt").write_bytes(self.cert.read_bytes())
        self.path = self.root / "bootstrap.sh"
        self.path.write_text(self.script.replace(
            "/var/run/secrets/kubernetes.io/serviceaccount", str(sa)).replace(
            "https://kubernetes.default.svc", f"https://localhost:{self.kube.server_port}").replace(
            "/existing-api-key/api-key", str(self.projected_key)))

    def tearDown(self):
        for server in (self.dt, self.kube):
            server.shutdown()
            server.server_close()
        self.tmp.cleanup()

    def existing_secret(self, key):
        self.secret = {"data": {"API_KEY": base64.b64encode(key.encode()).decode()}}
        self.projected_key.write_text(key)

    def execute(self, managed=True, file=None):
        env = {"PATH": os.environ["PATH"],
               "DEPENDENCY_TRACK_URL": f"http://localhost:{self.dt.server_port}",
               "DEPENDENCY_TRACK_ADMIN_PASSWORD": "test-password&=+%"}
        if managed:
            env["DEPENDENCY_TRACK_API_KEY_SECRET"] = "ak-dtrack-key"
        if file:
            env["DEPENDENCY_TRACK_API_KEY_FILE"] = str(file)
        result = subprocess.run(["sh", str(self.path)], env=env, text=True,
                                capture_output=True, timeout=15)
        for value in (NEW_KEY, OLD_KEY, "test-kubernetes-token", "test-password&=+%"):
            self.assertNotIn(value, result.stdout + result.stderr)
        return result

    def test_first_install_creates_secret_over_verified_tls(self):
        self.change_password = True
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.password_changed)
        self.assertEqual(self.generated, 1)
        self.assertEqual(self.secret["stringData"], {"API_KEY": NEW_KEY})
        self.assertNotIn("ownerReferences", self.secret["metadata"])
        self.assertNotIn("app.kubernetes.io/instance", self.secret["metadata"]["labels"])
        kube_requests = [r for r in self.requests if r[1].startswith("/api/v1/namespaces/")]
        self.assertEqual([r[0] for r in kube_requests], ["GET", "POST"])
        self.assertTrue(all(r[3]["Authorization"] == "Bearer test-kubernetes-token" for r in kube_requests))

    def test_existing_secret_is_preserved_without_generating_key(self):
        self.existing_secret(OLD_KEY)
        original = self.secret.copy()
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.generated, 0)
        self.assertEqual(self.secret, original)
        self.assertFalse(any(r[0] == "POST" and r[1].endswith("/secrets") for r in self.requests))

    def test_empty_existing_secret_fails_before_touching_dtrack(self):
        self.existing_secret("")
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no nonempty API_KEY", result.stderr)
        self.assertEqual(self.generated, 0)
        self.assertEqual(len(self.requests), 1)

    def test_read_denial_fails_without_generating_key(self):
        self.read_status = 403
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HTTP 403", result.stderr)
        self.assertEqual(self.generated, 0)

    def test_create_denial_does_not_report_success(self):
        self.create_status = 403
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HTTP 403", result.stderr)
        self.assertIsNone(self.secret)

    def test_concurrent_creator_is_not_overwritten(self):
        self.create_status = 409
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(base64.b64decode(self.secret["data"]["API_KEY"]).decode(), OLD_KEY)
        self.assertEqual(sum(r[0] == "POST" and r[1].endswith("/secrets") for r in self.requests), 1)

    def test_legacy_file_create_and_preservation(self):
        path = self.root / "api-key"
        result = self.execute(managed=False, file=path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.read_text().strip(), NEW_KEY)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.requests.clear()
        result = self.execute(managed=False, file=path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.generated, 1)
        self.assertEqual(self.requests, [])

    def test_operator_supplied_secret_only_reconciles_admin(self):
        result = self.execute(managed=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.generated, 0)
        self.assertFalse(any(r[1].startswith("/api/v1/namespaces/") for r in self.requests))
