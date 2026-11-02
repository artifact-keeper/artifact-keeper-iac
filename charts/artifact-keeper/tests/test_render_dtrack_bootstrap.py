"""Render tests for the Dependency-Track bootstrap script settings."""

from pathlib import Path
import os
import re
import subprocess
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]
DEFAULT_PERMISSIONS = ("BOM_UPLOAD PROJECT_CREATION_UPLOAD PORTFOLIO_MANAGEMENT "
                       "VIEW_PORTFOLIO VIEW_VULNERABILITY VULNERABILITY_ANALYSIS")


def run_helm(values):
    return subprocess.run(
        [os.environ.get("HELM", "helm"), "template", "ak", str(CHART),
         "--set", "secrets.existingSecret=render-test", "-f", "-"],
        input=yaml.safe_dump(values), capture_output=True, text=True, check=False,
    )


def script(values=None):
    result = run_helm(values or {})
    if result.returncode:
        raise AssertionError(result.stderr)
    docs = [d for d in yaml.safe_load_all(result.stdout) if d]
    configmap = next(d for d in docs if d["kind"] == "ConfigMap"
                     and d["metadata"]["name"].endswith("-dtrack-init"))
    return configmap["data"]["init-dtrack.sh"]


def permissions(text):
    return re.search(r'^AUTOMATION_PERMISSIONS="([^"]*)"$', text, re.M).group(1)


class AutomationPermissionTests(unittest.TestCase):
    """#168: the Automation team gets the permissions the backend needs."""

    def test_default_permissions_are_granted_in_both_key_modes(self):
        managed = {"dependencyTrack": {"existingApiKeySecret": "ak-dtrack-key",
                                       "bootstrap": {"manageApiKeySecret": True}}}
        for values in ({}, managed):
            with self.subTest(values=values):
                text = script(values)
                self.assertEqual(permissions(text), DEFAULT_PERMISSIONS)
                self.assertIn('/api/v1/permission/$PERM/team/$TEAM_UUID', text)

    def test_existing_key_no_longer_skips_the_grants(self):
        text = script()
        self.assertIn('[ "$NVD_API_ENABLED" != "true" ] && [ "$GRANT_PERMISSIONS" != "true" ]', text)
        # The team lookup runs whenever grants are due, not only for a new key.
        self.assertIn('if [ "$NEED_KEY" = "true" ] || [ "$GRANT_PERMISSIONS" = "true" ]; then', text)

    def test_list_is_configurable_and_can_be_emptied(self):
        text = script({"dependencyTrack": {"bootstrap": {
            "automationPermissions": ["BOM_UPLOAD", "VIEW_PORTFOLIO", "BOM_UPLOAD"]}}})
        self.assertEqual(permissions(text), "BOM_UPLOAD VIEW_PORTFOLIO")
        text = script({"dependencyTrack": {"bootstrap": {"automationPermissions": []}}})
        self.assertEqual(permissions(text), "")

    def test_invalid_entries_fail_the_render(self):
        for value, message in ((["bom_upload"], "is not a Dependency-Track permission name"),
                               (["BOM_UPLOAD; rm -rf /"], "is not a Dependency-Track permission name"),
                               (["BOM UPLOAD"], "is not a Dependency-Track permission name"),
                               ([""], "is not a Dependency-Track permission name"),
                               ([1], "is not a Dependency-Track permission name"),
                               ("BOM_UPLOAD", "must be a list")):
            with self.subTest(value=value):
                result = run_helm({"dependencyTrack": {"bootstrap": {"automationPermissions": value}}})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)


class LegacyKeyFileModeTests(unittest.TestCase):
    """#318: the shared-volume key file must be group-readable for the backend."""

    def test_key_file_is_written_with_umask_027(self):
        text = script()
        self.assertRegex(text, r'umask 027\n\s*printf \'%s\\n\' "\$API_KEY" > "\$API_KEY_FILE\.tmp"')
        self.assertNotRegex(text, r'umask 077\n\s*printf \'%s\\n\' "\$API_KEY" > "\$API_KEY_FILE\.tmp"')
        self.assertNotIn("fsGroupChangePolicy defaults to", text)


if __name__ == "__main__":
    unittest.main()
