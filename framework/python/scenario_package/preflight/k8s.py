# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Thin Kubernetes accessors used by the cluster checks.

Secret/Role/RoleBinding shapes mirror framework/python/initUsersListSecrets.py, which stays
in place as the standalone entry point used by initValidationScenarios.sh.
"""

import base64
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

SECRET_NAME = "validation-scenarios"
SECRET_KEY = "users-file-dict"
SECRETS_READER_ROLE = "validation-scenarios-secrets-reader"
SECRETS_READER_BINDING = "validation-scenarios-secrets-reader-binding"
SECRETS_READER_SERVICE_ACCOUNT = "default"
OPERATOR_NAME = "locust-operator"
LEGACY_OPERATOR_NAME = "locust-operator-locust-k8s-operator"
OPERATOR_CRD = "locusttests.locust.io"


class KubeError(Exception):
    """Kubernetes access failed in a way a check should report rather than crash on."""


@dataclass
class KubeClients:
    core: object
    apps: object
    rbac: object
    extensions: object

    @classmethod
    def load(cls, kubeconfig: Optional[str]) -> "KubeClients":
        try:
            from kubernetes import client, config
        except ImportError as error:
            raise KubeError(
                "the 'kubernetes' python package is not installed: reinstall with 'pip install -e .'"
            ) from error
        try:
            config.load_kube_config(config_file=kubeconfig)
        except Exception as error:
            raise KubeError(f"could not load kubeconfig: {error}") from error
        return cls(
            core=client.CoreV1Api(),
            apps=client.AppsV1Api(),
            rbac=client.RbacAuthorizationV1Api(),
            extensions=client.ApiextensionsV1Api(),
        )


def _api_exception():
    from kubernetes.client.rest import ApiException

    return ApiException


def read_or_none(call, *args, **kwargs):
    """Return the object, or None when the API reports 404."""
    try:
        return call(*args, **kwargs)
    except Exception as error:
        if getattr(error, "status", None) == 404:
            return None
        raise KubeError(str(error)) from error


def users_from_csv(path: Path) -> Dict[str, str]:
    users: Dict[str, str] = {}
    with open(path, "r", newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if len(row) >= 2:
                users[row[0]] = row[1]
    if not users:
        raise KubeError(f"no 'user,password' rows found in {path}")
    return users


def decode_users(secret) -> Dict[str, str]:
    data = getattr(secret, "data", None) or {}
    encoded = data.get(SECRET_KEY)
    if encoded is None:
        raise KubeError(f"secret '{SECRET_NAME}' has no '{SECRET_KEY}' key")
    return json.loads(base64.b64decode(encoded).decode("utf-8"))


def apply_users_secret(kube: KubeClients, namespace: str, users: Dict[str, str]) -> None:
    from kubernetes import client

    api_exception = _api_exception()
    secret = client.V1Secret(
        api_version="v1",
        kind="Secret",
        metadata=client.V1ObjectMeta(name=SECRET_NAME, namespace=namespace),
        data={
            SECRET_KEY: base64.b64encode(json.dumps(users).encode("utf-8")).decode("utf-8")
        },
    )
    try:
        kube.core.create_namespaced_secret(namespace, secret)
    except api_exception as error:
        if error.status != 409:
            raise KubeError(str(error)) from error
        kube.core.replace_namespaced_secret(SECRET_NAME, namespace, secret)


def apply_secrets_reader_rbac(kube: KubeClients, namespace: str) -> None:
    from kubernetes import client

    api_exception = _api_exception()
    role = client.V1Role(
        api_version="rbac.authorization.k8s.io/v1",
        kind="Role",
        metadata=client.V1ObjectMeta(name=SECRETS_READER_ROLE, namespace=namespace),
        rules=[
            client.V1PolicyRule(
                api_groups=[""],
                resources=["secrets"],
                verbs=["get"],
                resource_names=[SECRET_NAME],
            )
        ],
    )
    try:
        kube.rbac.create_namespaced_role(namespace, role)
    except api_exception as error:
        if error.status != 409:
            raise KubeError(str(error)) from error
        kube.rbac.replace_namespaced_role(SECRETS_READER_ROLE, namespace, role)

    binding = client.V1RoleBinding(
        api_version="rbac.authorization.k8s.io/v1",
        kind="RoleBinding",
        metadata=client.V1ObjectMeta(name=SECRETS_READER_BINDING, namespace=namespace),
        subjects=[
            {
                "kind": "ServiceAccount",
                "name": SECRETS_READER_SERVICE_ACCOUNT,
                "namespace": namespace,
            }
        ],
        role_ref={
            "kind": "Role",
            "name": SECRETS_READER_ROLE,
            "apiGroup": "rbac.authorization.k8s.io",
        },
    )
    try:
        kube.rbac.create_namespaced_role_binding(namespace, binding)
    except api_exception as error:
        if error.status != 409:
            raise KubeError(str(error)) from error
        kube.rbac.replace_namespaced_role_binding(SECRETS_READER_BINDING, namespace, binding)


def create_namespace(kube: KubeClients, namespace: str) -> None:
    from kubernetes import client

    kube.core.create_namespace(
        client.V1Namespace(metadata=client.V1ObjectMeta(name=namespace))
    )


def operator_deployments(kube: KubeClients) -> Dict[str, object]:
    """Operator Deployments in any namespace, keyed by namespace."""
    try:
        deployments = kube.apps.list_deployment_for_all_namespaces(
            field_selector=f"metadata.name={OPERATOR_NAME}"
        )
    except Exception as error:
        raise KubeError(str(error)) from error
    return {
        deployment.metadata.namespace: deployment
        for deployment in (deployments.items or [])
    }


def crd_served_versions(kube: KubeClients, name: str) -> Optional[List[str]]:
    crd = read_or_none(kube.extensions.read_custom_resource_definition, name)
    if crd is None:
        return None
    return [version.name for version in crd.spec.versions if version.served]


def parse_quantity(value: Optional[str], is_cpu: bool) -> float:
    """Convert a Kubernetes quantity to cores (CPU) or bytes (memory)."""
    if not value:
        return 0.0
    text = str(value)
    if is_cpu:
        if text.endswith("m"):
            return float(text[:-1]) / 1000.0
        if text.endswith("n"):
            return float(text[:-1]) / 1_000_000_000.0
        return float(text)
    multipliers = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "K": 1000,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
    }
    for suffix, multiplier in multipliers.items():
        if text.endswith(suffix):
            return float(text[: -len(suffix)]) * multiplier
    return float(text)
