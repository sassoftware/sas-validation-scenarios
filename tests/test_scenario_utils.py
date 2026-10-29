# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for namespace resolution of the users secret in scenario_utils."""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATHS = [
    REPOSITORY_ROOT / "framework/execution/common/scenario_utils.py",
    REPOSITORY_ROOT / "validation-scenarios/locust-commandline/scenario_utils.py",
]


def _load(path):
    stubs = {}
    for name in ("locust_plugins", "locust_plugins.csvreader", "kubernetes",
                 "kubernetes.client", "kubernetes.client.rest"):
        stubs[name] = ModuleType(name)
    stubs["locust_plugins.csvreader"].CSVReader = MagicMock()
    stubs["kubernetes"].client = MagicMock()
    stubs["kubernetes"].config = MagicMock()
    stubs["kubernetes.client.rest"].ApiException = type("ApiException", (Exception,), {})
    with patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location("scenario_utils_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class NamespaceResolutionTest(unittest.TestCase):
    def test_namespace_resolution(self):
        for path in MODULE_PATHS:
            with self.subTest(path=str(path.relative_to(REPOSITORY_ROOT))):
                module = _load(path)
                manager = module.UsersManager()
                with tempfile.TemporaryDirectory() as tmp:
                    ns_file = Path(tmp) / "namespace"
                    ns_file.write_text("validation-scenarios\n")
                    with patch.object(module, "SERVICE_ACCOUNT_NAMESPACE_FILE", str(ns_file)):
                        with patch.dict(os.environ, {}, clear=True):
                            self.assertEqual("validation-scenarios", manager.get_namespace())
                        with patch.dict(os.environ, {"POD_NAMESPACE": "from-env"}, clear=True):
                            self.assertEqual("from-env", manager.get_namespace())
                    missing = str(Path(tmp) / "absent")
                    with patch.object(module, "SERVICE_ACCOUNT_NAMESPACE_FILE", missing):
                        with patch.dict(os.environ, {}, clear=True):
                            self.assertEqual("testing", manager.get_namespace())

    def test_get_user_list_uses_resolved_namespace(self):
        for path in MODULE_PATHS:
            with self.subTest(path=str(path.relative_to(REPOSITORY_ROOT))):
                module = _load(path)
                manager = module.UsersManager()
                with patch.object(module.os.path, "exists", return_value=False), \
                        patch.object(manager, "get_namespace", return_value="ns-a"), \
                        patch.object(manager, "get_users_from_k8s_secret", return_value=[]) as secret:
                    manager.get_user_list()
                    secret.assert_called_once_with("validation-scenarios", "ns-a", "users-file-dict")
                    secret.reset_mock()
                    manager.get_user_list(namespace="explicit")
                    secret.assert_called_once_with("validation-scenarios", "explicit", "users-file-dict")


if __name__ == "__main__":
    unittest.main()
