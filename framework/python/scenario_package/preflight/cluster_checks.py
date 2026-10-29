# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Checks for the Kubernetes cluster that hosts the Locust load generators."""

import re
from pathlib import Path
from typing import List, Optional

from . import k8s
from .core import Check, CheckResult, PreflightContext, fail, ok, warn
from .http import HttpError

INSTALL_SCRIPT = Path("locust-k8s") / "install-locust-k8s-operator.sh"
UNINSTALL_SCRIPT = Path("locust-k8s") / "uninstall-locust-k8s-operator.sh"
CUSTOM_RESOURCE_TEMPLATE = Path("python") / "templates" / "k8s-custom-resource.yaml.template"
LOCUST_CONFIG = Path("locust-k8s") / "locust-config.yaml"
DEFAULT_POD_CPU = 2.0
DEFAULT_POD_MEMORY = 1024 * 1024**2
INSTALL_OPERATOR_SUMMARY = (
    "Install/upgrade the cluster-wide locust-k8s-operator in the testing namespace "
    "(sas-validation.execution.namespace), or in place where it already runs "
    "(CRD, ClusterRole/Binding, Deployment; waits for the rollout) - can take several minutes"
)


def _template_value(context: PreflightContext, key: str) -> Optional[str]:
    if context.framework_root is None:
        return None
    template = context.framework_root / CUSTOM_RESOURCE_TEMPLATE
    if not template.is_file():
        return None
    match = re.search(
        rf"^\s*{re.escape(key)}:\s*(\S+)\s*$",
        template.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return match.group(1) if match else None


def _operator_target_namespace(context: PreflightContext) -> str:
    """Where to install: the testing namespace, unless the one cluster operator runs elsewhere."""
    existing = sorted(k8s.operator_deployments(context.kube()))
    if not existing or context.namespace in existing:
        if not context.namespace:
            raise k8s.KubeError("set 'sas-validation.execution.namespace' or pass --namespace")
        return context.namespace
    if len(existing) == 1:
        return existing[0]
    raise k8s.KubeError(
        f"the locust-k8s-operator runs in several namespaces ({', '.join(existing)}); "
        "uninstall all but one before re-running with --fix"
    )


def _install_operator(context: PreflightContext) -> str:
    script = context.framework_root / INSTALL_SCRIPT
    namespace = _operator_target_namespace(context)
    kubeconfig = context.environ.get("KUBECONFIG", "")
    completed = context.run_command(
        [str(script), namespace, kubeconfig], max(context.timeout, 420.0)
    )
    if completed.returncode != 0:
        raise k8s.KubeError(
            f"{script} exited {completed.returncode}: "
            f"{(completed.stderr or completed.stdout or '').strip()[-500:]}"
        )
    return f"ran {script} (operator namespace '{namespace}')"


def _script_path(context: PreflightContext, script: Path) -> Path:
    return context.framework_root / script if context.framework_root is not None else script


def _operator_remedy(context: PreflightContext, namespace: Optional[str] = None) -> str:
    if context.framework_root is None:
        return (
            "Set 'sas-validation.framework-root' in sas-validation.yaml, then re-run with --fix"
        )
    target = namespace or context.namespace or "<namespace>"
    return f"{context.framework_root / INSTALL_SCRIPT} {target} $KUBECONFIG"


def _operator_fixable(context: PreflightContext) -> bool:
    return context.framework_root is not None and (
        context.framework_root / INSTALL_SCRIPT
    ).is_file()


def _operator_failure(
    context: PreflightContext, detail: str, namespace: Optional[str] = None
) -> CheckResult:
    return fail(
        detail,
        remedy=_operator_remedy(context, namespace),
        fixable=_operator_fixable(context),
    )


def _reachable(context: PreflightContext) -> CheckResult:
    try:
        kube = context.kube()
        kube.core.list_namespace(limit=1)
    except k8s.KubeError as error:
        return fail(str(error), remedy="Export an admin KUBECONFIG for the load generation cluster")
    except Exception as error:
        return fail(
            f"cluster API is not reachable: {error}",
            remedy="Export an admin KUBECONFIG for the load generation cluster",
        )
    return ok("cluster API reachable")


def _namespace(context: PreflightContext) -> CheckResult:
    kube = context.kube()
    if k8s.read_or_none(kube.core.read_namespace, context.namespace) is None:
        return fail(
            f"namespace '{context.namespace}' does not exist",
            remedy=f"kubectl create namespace {context.namespace}",
            fixable=True,
        )
    return ok(f"namespace '{context.namespace}' exists")


def _create_namespace(context: PreflightContext) -> str:
    k8s.create_namespace(context.kube(), context.namespace)
    return f"created namespace '{context.namespace}'"


def _crd(context: PreflightContext) -> CheckResult:
    versions = k8s.crd_served_versions(context.kube(), k8s.OPERATOR_CRD)
    if versions is None:
        return _operator_failure(context, f"CustomResourceDefinition '{k8s.OPERATOR_CRD}' is missing")
    api_version = _template_value(context, "apiVersion")
    if api_version is None:
        return ok(f"'{k8s.OPERATOR_CRD}' serves {', '.join(versions)}")
    required = api_version.split("/")[-1]
    if required not in versions:
        return _operator_failure(
            context,
            f"'{k8s.OPERATOR_CRD}' serves {', '.join(versions)} but the generated LocustTest "
            f"uses apiVersion '{api_version}'",
        )
    return ok(f"'{k8s.OPERATOR_CRD}' serves {required}")


def _cluster_rbac(context: PreflightContext) -> CheckResult:
    kube = context.kube()
    missing = []
    if k8s.read_or_none(kube.rbac.read_cluster_role, k8s.OPERATOR_NAME) is None:
        missing.append("ClusterRole")
    binding = k8s.read_or_none(kube.rbac.read_cluster_role_binding, k8s.OPERATOR_NAME)
    if binding is None:
        missing.append("ClusterRoleBinding")
    if missing:
        return _operator_failure(
            context, f"missing {' and '.join(missing)} '{k8s.OPERATOR_NAME}'"
        )
    bound = sorted(
        subject.namespace
        for subject in (getattr(binding, "subjects", None) or [])
        if subject.kind == "ServiceAccount" and subject.name == k8s.OPERATOR_NAME
    )
    running = sorted(k8s.operator_deployments(kube))
    if len(running) == 1 and running[0] not in bound:
        return _operator_failure(
            context,
            f"ClusterRoleBinding '{k8s.OPERATOR_NAME}' binds ServiceAccount "
            f"'{k8s.OPERATOR_NAME}' in {', '.join(repr(ns) for ns in bound) or 'no namespace'}, "
            f"but the operator runs in '{running[0]}'",
            namespace=running[0],
        )
    return ok(f"ClusterRole and ClusterRoleBinding '{k8s.OPERATOR_NAME}' exist")


def _operator_deployment(context: PreflightContext) -> CheckResult:
    deployments = k8s.operator_deployments(context.kube())
    if not deployments:
        return _operator_failure(
            context,
            f"Deployment '{k8s.OPERATOR_NAME}' is missing; it will be installed in "
            f"'{context.namespace}'",
        )
    uninstall = _script_path(context, UNINSTALL_SCRIPT)
    if len(deployments) > 1:
        namespaces = sorted(deployments)
        return warn(
            f"the locust-k8s-operator runs in {len(namespaces)} namespaces "
            f"({', '.join(namespaces)}); only one per cluster should run, as each one "
            "acts on every LocustTest",
            remedy=f"{uninstall} <namespace> $KUBECONFIG for all but one",
        )
    namespace, deployment = next(iter(deployments.items()))
    label = f"Deployment '{namespace}/{k8s.OPERATOR_NAME}'"
    ready = (deployment.status.ready_replicas if deployment.status else None) or 0
    if ready < 1:
        return fail(
            f"{label} has no ready replicas",
            remedy=f"kubectl -n {namespace} describe deployment {k8s.OPERATOR_NAME}",
        )
    if namespace != context.namespace:
        return warn(
            f"{label} has {ready} ready replica(s) and serves the whole cluster, so no "
            f"second operator is installed in the testing namespace '{context.namespace}'",
            remedy=(
                f"To move it: {uninstall} {namespace} $KUBECONFIG, then "
                "sas-validation preflight --fix"
            ),
        )
    return ok(f"{label} has {ready} ready replica(s)")


def _legacy_operator(context: PreflightContext) -> CheckResult:
    legacy = k8s.LEGACY_OPERATOR_NAME
    deployment = k8s.read_or_none(
        context.kube().apps.read_namespaced_deployment, legacy, context.namespace
    )
    if deployment is None:
        return ok(f"no legacy operator in '{context.namespace}'")
    return warn(
        f"the legacy locust-k8s-operator 0.8.0 is still deployed in '{context.namespace}' "
        "and may also act on LocustTests",
        remedy=(
            f"kubectl -n {context.namespace} delete deployment,serviceaccount,role,rolebinding "
            f"{legacy}; kubectl delete clusterrolebinding,clusterrole {legacy}"
        ),
    )


def _users_secret(context: PreflightContext) -> CheckResult:
    secret = k8s.read_or_none(
        context.kube().core.read_namespaced_secret, k8s.SECRET_NAME, context.namespace
    )
    remedy = (
        f"./initUserNames.sh -u <users.csv> -n {context.namespace}, or re-run with "
        "--users-file <users.csv> --fix"
    )
    if secret is None:
        return warn(
            f"secret '{k8s.SECRET_NAME}' does not exist in '{context.namespace}'",
            remedy=remedy,
            fixable=context.users_file is not None,
        )
    try:
        users = k8s.decode_users(secret)
    except Exception as error:
        return warn(str(error), remedy=remedy, fixable=context.users_file is not None)
    if not users:
        return warn(
            f"secret '{k8s.SECRET_NAME}' contains no users",
            remedy=remedy,
            fixable=context.users_file is not None,
        )
    return ok(f"secret '{k8s.SECRET_NAME}' holds {len(users)} user(s)")


def _load_users_secret(context: PreflightContext) -> str:
    users = k8s.users_from_csv(context.users_file)
    k8s.apply_users_secret(context.kube(), context.namespace, users)
    return f"stored {len(users)} user(s) from {context.users_file} in '{k8s.SECRET_NAME}'"


def _secrets_reader_rbac(context: PreflightContext) -> CheckResult:
    kube = context.kube()
    missing = []
    if (
        k8s.read_or_none(kube.rbac.read_namespaced_role, k8s.SECRETS_READER_ROLE, context.namespace)
        is None
    ):
        missing.append(f"Role '{k8s.SECRETS_READER_ROLE}'")
    if (
        k8s.read_or_none(
            kube.rbac.read_namespaced_role_binding, k8s.SECRETS_READER_BINDING, context.namespace
        )
        is None
    ):
        missing.append(f"RoleBinding '{k8s.SECRETS_READER_BINDING}'")
    if missing:
        return warn(
            f"missing {', '.join(missing)} in '{context.namespace}'",
            remedy=f"./initUserNames.sh -u <users.csv> -n {context.namespace}",
            fixable=True,
        )
    return ok(f"'{k8s.SECRETS_READER_SERVICE_ACCOUNT}' can read secret '{k8s.SECRET_NAME}'")


def _apply_secrets_reader_rbac(context: PreflightContext) -> str:
    k8s.apply_secrets_reader_rbac(context.kube(), context.namespace)
    return f"granted '{k8s.SECRETS_READER_SERVICE_ACCOUNT}' read access to '{k8s.SECRET_NAME}'"


def _image(context: PreflightContext) -> CheckResult:
    image = _template_value(context, "image")
    if image is None:
        return warn("could not determine the Locust image from the workload template")
    registry, _, repository = image.partition("/")
    repository, _, tag = repository.partition(":")
    tag = tag or "latest"
    if "." not in registry:
        return warn(f"image '{image}' is not registry qualified; pullability not checked")
    try:
        token_response = context.http.request(
            f"https://{registry}/oauth2/token?service={registry}"
            f"&scope=repository:{repository}:pull"
        )
        if token_response.status != 200:
            return warn(
                f"anonymous pull token for '{image}' returned HTTP {token_response.status}",
                remedy="Confirm registry access, or configure spec.imagePullSecrets",
            )
        token = token_response.json().get("access_token")
        manifest = context.http.request(
            f"https://{registry}/v2/{repository}/manifests/{tag}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.docker.distribution.manifest.v2+json,"
                "application/vnd.oci.image.manifest.v1+json,"
                "application/vnd.oci.image.index.v1+json",
            },
        )
    except HttpError as error:
        return warn(
            f"could not reach registry '{registry}': {error}",
            remedy="Check egress from this host to the container registry",
        )
    if manifest.status != 200:
        return warn(
            f"manifest for '{image}' returned HTTP {manifest.status}",
            remedy="Confirm the image tag exists, or configure spec.imagePullSecrets",
        )
    return ok(f"'{image}' is pullable anonymously")


def _pod_requests(context: PreflightContext):
    config = (
        context.framework_root / LOCUST_CONFIG if context.framework_root is not None else None
    )
    if config is None or not config.is_file():
        return DEFAULT_POD_CPU, DEFAULT_POD_MEMORY
    import yaml

    values = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    requests = ((values.get("locustPods") or {}).get("resources") or {}).get("requests") or {}
    return (
        k8s.parse_quantity(requests.get("cpu"), True) or DEFAULT_POD_CPU,
        k8s.parse_quantity(requests.get("memory"), False) or DEFAULT_POD_MEMORY,
    )


def _capacity(context: PreflightContext) -> CheckResult:
    kube = context.kube()
    cpu_request, memory_request = _pod_requests(context)
    nodes = kube.core.list_node().items
    schedulable = [
        node
        for node in nodes
        if not any(taint.effect == "NoSchedule" for taint in (node.spec.taints or []))
    ]
    per_node = [
        (
            k8s.parse_quantity((node.status.allocatable or {}).get("cpu"), True),
            k8s.parse_quantity((node.status.allocatable or {}).get("memory"), False),
        )
        for node in schedulable
    ]
    fits = [
        cpu >= cpu_request and memory >= memory_request for cpu, memory in per_node
    ]
    quotas = kube.core.list_namespaced_resource_quota(context.namespace).items
    quota_note = (
        f"; ResourceQuota in effect: {', '.join(quota.metadata.name for quota in quotas)}"
        if quotas
        else ""
    )
    summary = (
        f"{len(schedulable)} schedulable node(s), {sum(fits)} can host a Locust pod "
        f"({cpu_request:g} CPU / {memory_request / 1024 ** 2:.0f}Mi){quota_note}"
    )
    if not any(fits):
        return warn(
            f"no schedulable node has room for a single Locust pod - {summary}",
            remedy="Add capacity, or lower the requests in framework/locust-k8s/locust-config.yaml",
        )
    if quotas:
        return warn(summary, remedy="Confirm the quota allows your worker replica count")
    return ok(summary)


def checks() -> List[Check]:
    return [
        Check(
            "cluster.reachable",
            "cluster",
            "Cluster API",
            _reachable,
            requires=("client.kubeconfig",),
        ),
        Check(
            "cluster.namespace",
            "cluster",
            "Testing namespace",
            _namespace,
            fix=_create_namespace,
            requires=("cluster.reachable", "client.config"),
            fix_summary="Create the Kubernetes namespace",
        ),
        Check(
            "cluster.crd",
            "cluster",
            "LocustTest CRD",
            _crd,
            fix=_install_operator,
            requires=("cluster.reachable", "client.config"),
            fix_key="install-operator",
            fix_summary=INSTALL_OPERATOR_SUMMARY,
        ),
        Check(
            "cluster.cluster-rbac",
            "cluster",
            "Operator cluster RBAC",
            _cluster_rbac,
            fix=_install_operator,
            requires=("cluster.reachable", "client.config"),
            fix_key="install-operator",
            fix_summary=INSTALL_OPERATOR_SUMMARY,
        ),
        Check(
            "cluster.operator-deployment",
            "cluster",
            "Operator deployment",
            _operator_deployment,
            fix=_install_operator,
            requires=("cluster.reachable", "client.config"),
            fix_key="install-operator",
            fix_summary=INSTALL_OPERATOR_SUMMARY,
        ),
        Check(
            "cluster.legacy-operator",
            "cluster",
            "Legacy operator removed",
            _legacy_operator,
            requires=("cluster.namespace",),
        ),
        Check(
            "cluster.users-secret",
            "cluster",
            "Test user credentials secret",
            _users_secret,
            fix=_load_users_secret,
            requires=("cluster.namespace",),
            fix_summary="Store test user credentials in the 'validation-scenarios' secret",
            fix_available=lambda context: context.users_file is not None,
        ),
        Check(
            "cluster.secrets-reader-rbac",
            "cluster",
            "Credentials secret RBAC",
            _secrets_reader_rbac,
            fix=_apply_secrets_reader_rbac,
            requires=("cluster.namespace",),
            fix_summary="Grant the default ServiceAccount read access to that secret",
        ),
        Check("cluster.image", "cluster", "Locust image", _image, requires=("client.config",)),
        Check(
            "cluster.capacity",
            "cluster",
            "Cluster capacity",
            _capacity,
            requires=("cluster.namespace",),
        ),
    ]
