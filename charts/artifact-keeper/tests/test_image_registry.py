"""Offline Helm rendering tests; requires Helm and the CI-pinned PyYAML."""

import copy
from pathlib import Path
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
VALUES = yaml.safe_load((CHART / "values.yaml").read_text())
APP_VERSION = yaml.safe_load((CHART / "Chart.yaml").read_text())["appVersion"]
DIGEST = "sha256:" + "a" * 64
OPTIONAL = {
    "edge.enabled": True,
    "cosign.enabled": True,
    "opensearch.fixOwnership.enabled": True,
    "trivy.db.preseed.enabled": True,
}
VARIANTS = {
    "default": {},
    "optional": OPTIONAL,
    "opensearch-cluster": {**OPTIONAL, "opensearch.replicaCount": 3},
    "fleet": {
        **OPTIONAL,
        "fleet.enabled": True,
        "fleet.instanceId": "registry-test",
        "fleet.externalDatabaseBootstrap.host": "postgres.example.com",
        "fleet.externalDatabaseBootstrap.adminSecret": "db-admin",
        "fleet.externalDatabaseBootstrap.existingSecret": "db-instance",
        "postgres.enabled": False,
    },
}


def image_values(node, path=()):
    """Discover all image maps, including nested helper/init image values."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "image" and isinstance(value, dict) and "repository" in value:
                yield ".".join((*path, key)), value
            else:
                yield from image_values(value, (*path, key))


IMAGES = dict(image_values(VALUES))


def render(overrides=None, chart=CHART):
    values = {"secrets": {"existingSecret": "registry-render-test"}}
    for path, value in (overrides or {}).items():
        node = values
        *parents, key = path.split(".")
        for parent in parents:
            node = node.setdefault(parent, {})
        node[key] = value
    result = subprocess.run(
        ["helm", "template", "ak", str(chart), "-f", "-"],
        input=yaml.safe_dump(values),
        capture_output=True,
        text=True,
        check=True,
    )
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def containers(node, path=()):
    """Find pod containers without assuming resource names or workload kinds."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("containers", "initContainers", "ephemeralContainers"):
                for container in value or []:
                    yield (*path, key, container["name"]), container
            else:
                yield from containers(value, (*path, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from containers(value, (*path, index))


def rendered_images(documents):
    return {
        (doc["kind"], doc["metadata"]["name"], *path): container["image"]
        for doc in documents
        for path, container in containers(doc)
    }


class ImageRegistryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baselines = {
            name: render({**overrides, "global.imageRegistry": ""})
            for name, overrides in VARIANTS.items()
        }

    def assert_cosign_target(self, documents):
        for doc in documents:
            pod_containers = dict(
                (container["name"], container) for _, container in containers(doc)
            )
            if "verify-image-signature" in pod_containers:
                self.assertEqual(
                    pod_containers["verify-image-signature"]["command"][-1],
                    pod_containers["backend"]["image"],
                )

    def test_default_preserves_repositories_and_covers_every_image_map(self):
        self.assertEqual(VALUES["global"]["imageRegistry"], "")
        expected = {
            f'{image["repository"]}:{image["tag"] or APP_VERSION}'
            for image in IMAGES.values()
        }
        self.assertEqual(
            set(rendered_images(self.baselines["optional"]).values()), expected
        )
        for variant, overrides in VARIANTS.items():
            with self.subTest(variant=variant):
                self.assertEqual(render(overrides), self.baselines[variant])
                self.assert_cosign_target(self.baselines[variant])
        fleet_hooks = {
            doc["metadata"]["annotations"]["helm.sh/hook"]
            for doc in self.baselines["fleet"]
            if "helm.sh/hook" in doc["metadata"].get("annotations", {})
        }
        self.assertIn("pre-install,pre-upgrade", fleet_hooks)
        self.assertIn("post-install,post-upgrade", fleet_hooks)

    def test_global_rewrites_every_container_and_only_image_references(self):
        # All default paths are known here, but the workload/container set is
        # discovered from each render so a newly added image cannot be skipped.
        paths = {
            f'{image["repository"]}:{image["tag"] or APP_VERSION}': (
                image["repository"].split("/", 1)[1]
                if image["repository"].startswith(("ghcr.io/", "gcr.io/"))
                else (
                    image["repository"]
                    if "/" in image["repository"]
                    else "library/" + image["repository"]
                )
            ) + f':{image["tag"] or APP_VERSION}'
            for image in IMAGES.values()
        }
        for registry in ("registry.example.com", "registry.example.com:5000/proxy"):
            for variant, overrides in VARIANTS.items():
                with self.subTest(registry=registry, variant=variant):
                    documents = render({**overrides, "global.imageRegistry": registry})
                    original = rendered_images(self.baselines[variant])
                    self.assertEqual(
                        rendered_images(documents),
                        {key: f"{registry}/{paths[ref]}" for key, ref in original.items()},
                    )
                    expected = copy.deepcopy(self.baselines[variant])
                    for doc in expected:
                        for _, container in containers(doc):
                            container["image"] = f'{registry}/{paths[container["image"]]}'
                            if container["name"] == "verify-image-signature":
                                target = container["command"][-1]
                                container["command"][-1] = f"{registry}/{paths[target]}"
                    self.assertEqual(documents, expected)
                    self.assert_cosign_target(documents)

    def test_custom_values_for_every_image_map_including_hooks(self):
        overrides = {}
        replacement = {}
        for index, (path, image) in enumerate(IMAGES.items()):
            overrides[f"{path}.repository"] = f"source.example.com:5443/team/image-{index}"
            overrides[f"{path}.tag"] = f"build-{index}@{DIGEST}"
            old = f'{image["repository"]}:{image["tag"] or APP_VERSION}'
            replacement[old] = f"team/image-{index}:build-{index}@{DIGEST}"
        for registry in ("", "registry.example.com:5000/proxy"):
            for variant, options in VARIANTS.items():
                with self.subTest(registry=registry, variant=variant):
                    documents = render({
                        **options, **overrides, "global.imageRegistry": registry
                    })
                    prefix = registry or "source.example.com:5443"
                    self.assertEqual(
                        rendered_images(documents),
                        {
                            key: f"{prefix}/{replacement[ref]}"
                            for key, ref in rendered_images(self.baselines[variant]).items()
                        },
                    )
                    self.assert_cosign_target(documents)

    def test_repository_normalization_and_reference_precedence(self):
        prefix = "registry.example.com:5000/proxy"
        cases = [
            (prefix, "alpine", "3.20", f"{prefix}/library/alpine:3.20"),
            (prefix, "alpine:3.21", "ignored", f"{prefix}/library/alpine:3.21"),
            (prefix, "docker.io/alpine", "3.20", f"{prefix}/library/alpine:3.20"),
            (prefix, "docker.io/library/alpine", "3.20", f"{prefix}/library/alpine:3.20"),
            (prefix, "index.docker.io/alpine", "3.20", f"{prefix}/library/alpine:3.20"),
            (prefix, "registry-1.docker.io/alpine", "3.20", f"{prefix}/library/alpine:3.20"),
            (prefix, "aquasec/trivy", "dev", f"{prefix}/aquasec/trivy:dev"),
            (prefix, "library/alpine", "3.20", f"{prefix}/library/alpine:3.20"),
            (prefix, "ghcr.io/team/backend", "dev", f"{prefix}/team/backend:dev"),
            (prefix, "source.example.com/backend", "dev", f"{prefix}/backend:dev"),
            (prefix, "localhost:5001/backend", "dev", f"{prefix}/backend:dev"),
            (prefix, "localhost/backend", "dev", f"{prefix}/backend:dev"),
            (prefix, "registry:5001/team/backend", "dev", f"{prefix}/team/backend:dev"),
            (prefix, "[2001:db8::1]:5001/backend", "dev", f"{prefix}/backend:dev"),
            (prefix, "docker.io:5001/alpine", "dev", f"{prefix}/alpine:dev"),
            (prefix, f"{prefix}/team/backend", "dev", f"{prefix}/team/backend:dev"),
            (prefix, f"{prefix}-other/backend", "dev", f"{prefix}/proxy-other/backend:dev"),
            (f" /{prefix}// ", " /ghcr.io//team/backend/ ", "dev", f"{prefix}/team/backend:dev"),
            ("docker.io", "docker.io/alpine", "3.20", "docker.io/library/alpine:3.20"),
            ("localhost:5000", "ghcr.io/team/backend", "dev", "localhost:5000/team/backend:dev"),
            ("mirror:5000", "alpine", "3.20", "mirror:5000/library/alpine:3.20"),
            ("[2001:db8::2]:5000/proxy", "alpine", "3.20", "[2001:db8::2]:5000/proxy/library/alpine:3.20"),
            (prefix, f"alpine@{DIGEST}", "ignored", f"{prefix}/library/alpine@{DIGEST}"),
            (prefix, f"ghcr.io/team/backend:dev@{DIGEST}", "ignored", f"{prefix}/team/backend:dev@{DIGEST}"),
            (prefix, "ghcr.io/team/backend", f"dev@{DIGEST}", f"{prefix}/team/backend:dev@{DIGEST}"),
            ("", "localhost:5001/team/backend", "dev", "localhost:5001/team/backend:dev"),
            ("", "alpine", "3.20", "alpine:3.20"),
            ("", f"ghcr.io/team/backend@{DIGEST}", "ignored", f"ghcr.io/team/backend@{DIGEST}"),
            ("", "ghcr.io/team/backend:pinned", "ignored", "ghcr.io/team/backend:pinned"),
            ("", "ghcr.io/team/backend", f"dev@{DIGEST}", f"ghcr.io/team/backend:dev@{DIGEST}"),
        ]
        for registry, repository, tag, expected in cases:
            with self.subTest(registry=registry, repository=repository, tag=tag):
                documents = render({
                    **OPTIONAL,
                    "global.imageRegistry": registry,
                    "backend.image.repository": repository,
                    "backend.image.tag": tag,
                })
                backend = next(
                    container
                    for doc in documents
                    for _, container in containers(doc)
                    if container["name"] == "backend"
                )
                self.assertEqual(backend["image"], expected)
                self.assert_cosign_target(documents)

    def test_app_version_fallback_and_explicit_tags(self):
        components = ("backend", "web", "edge", "scannerAdapter")
        for tag in ("", "custom", f"custom@{DIGEST}"):
            with self.subTest(tag=tag):
                documents = render({
                    **OPTIONAL,
                    "global.imageRegistry": "registry.example.com/mirror",
                    **{f"{component}.image.tag": tag for component in components},
                })
                expected = {
                    "registry.example.com/mirror/"
                    + VALUES[component]["image"]["repository"].removeprefix("ghcr.io/")
                    + f":{tag or APP_VERSION}"
                    for component in components
                }
                self.assertTrue(expected <= set(rendered_images(documents).values()))
                self.assert_cosign_target(documents)

    def test_invalid_registry_fails_explicitly(self):
        for registry in (
            "https://registry.example.com/proxy",
            "oci://registry.example.com",
            "registry.example.com/proxy:tag",
            f"registry.example.com@{DIGEST}",
            "registry.example.com/path with space",
            "mirror",
            "///",
        ):
            with self.subTest(registry=registry):
                with self.assertRaises(subprocess.CalledProcessError) as error:
                    render({"global.imageRegistry": registry})
                self.assertIn("global.imageRegistry must be a registry host", error.exception.stderr)

    def test_numeric_tag_is_not_confused_with_registry_port(self):
        documents = render({
            "global.imageRegistry": "registry.example.com:5000",
            "postgres.image.repository": "source.example.com:5001/database",
            "postgres.image.tag": 0,
        })
        postgres = next(
            container
            for doc in documents
            for _, container in containers(doc)
            if container["name"] == "postgres"
        )
        self.assertEqual(postgres["image"], "registry.example.com:5000/database:0")

    def test_runtime_downloads_and_extra_manifests_are_not_rewritten(self):
        documents = render({
            "global.imageRegistry": "registry.example.com/mirror",
            "trivy.db.preseed.enabled": True,
            "trivy.db.repository": "ghcr.io/aquasecurity/trivy-db:2",
            "trivy.db.javaRepository": "ghcr.io/aquasecurity/trivy-java-db:1",
            "extraManifests": [
                yaml.safe_dump({
                    "apiVersion": "v1",
                    "kind": "Pod",
                    "metadata": {"name": "user-owned"},
                    "spec": {"containers": [{"name": "user-owned", "image": "alpine:3.20"}]},
                }),
            ],
        })
        for doc in documents:
            for _, container in containers(doc):
                if container["name"] == "user-owned":
                    self.assertEqual(container["image"], "alpine:3.20")
                if container["name"] in ("trivy", "trivy-db-init"):
                    env = {entry["name"]: entry.get("value") for entry in container["env"]}
                    self.assertEqual(env["TRIVY_DB_REPOSITORY"], "ghcr.io/aquasecurity/trivy-db:2")
                    self.assertEqual(env["TRIVY_JAVA_DB_REPOSITORY"], "ghcr.io/aquasecurity/trivy-java-db:1")


if __name__ == "__main__":
    unittest.main()
