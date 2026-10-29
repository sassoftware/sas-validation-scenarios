#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# Installs or upgrades the single, cluster-wide locust-k8s-operator from the vendored manifest.
# USAGE: install-locust-k8s-operator.sh [[NAMESPACE] KUBECONFIG]
#   NAMESPACE defaults to 'locust-operator'; `sas-validation preflight --fix` passes
#   sas-validation.execution.namespace. Install only one operator per cluster.
if [ "${BASH_SOURCE[0]}" != "$0" ]; then echo -e "\nWARNING: this script should not be sourced\n"; return 1; fi
THISDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

MANIFEST_NAMESPACE=locust-operator
OPERATOR_NAMESPACE=$MANIFEST_NAMESPACE
OPERATOR_NAME=locust-operator
LEGACY_NAME=locust-operator-locust-k8s-operator
MANIFEST="$THISDIR/locust-k8s-operator.yaml"

if [ $# -ge 2 ]; then
  if [ -n "$1" ]; then OPERATOR_NAMESPACE=$1; fi
  shift
fi
if [ -n "$1" ]; then export KUBECONFIG=$1; fi

if [ ${#OPERATOR_NAMESPACE} -gt 63 ] || ! [[ "$OPERATOR_NAMESPACE" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]]; then
  echo -e "\nERROR: '$OPERATOR_NAMESPACE' is not a valid Kubernetes namespace name\n"
  exit 1
fi

run() { echo "$*"; "$@" || { echo -e "\nERROR: command failed: $*\n"; exit 1; }; }

if ! kubectl get ns >/dev/null 2>&1; then
  echo -e "\nERROR: 'kubectl get ns' failed, confirm you have exported an admin KUBECONFIG\n"
  exit 1
fi
if [ ! -f "$MANIFEST" ]; then
  echo -e "\nERROR: $MANIFEST not found\n"
  exit 1
fi

legacy=$( kubectl get deployments --all-namespaces --field-selector metadata.name=$LEGACY_NAME \
  -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{end}' 2>/dev/null )
if [ -n "$legacy" ]; then
  echo
  echo "WARNING: the legacy locust-k8s-operator 0.8.0 is still deployed in: $legacy"
  echo "         It may also act on LocustTests. Remove it with:"
  for ns in $legacy; do
    echo "  kubectl -n $ns delete deployment,serviceaccount,role,rolebinding $LEGACY_NAME"
  done
  echo "  kubectl delete clusterrolebinding,clusterrole $LEGACY_NAME"
fi

echo
kubectl get namespace "$OPERATOR_NAMESPACE" >/dev/null 2>&1 || run kubectl create namespace "$OPERATOR_NAMESPACE"
# The vendored manifest is rendered for namespace '$MANIFEST_NAMESPACE'; retarget its namespaced
# resources and the ClusterRoleBinding subject.
# Server-side apply: the CRD exceeds the 256KB limit of the client-side last-applied annotation.
echo "kubectl apply --server-side --force-conflicts -f $MANIFEST (namespace: $OPERATOR_NAMESPACE)"
sed -E "s/^([[:space:]]*namespace:)[[:space:]]+$MANIFEST_NAMESPACE[[:space:]]*\$/\1 $OPERATOR_NAMESPACE/" "$MANIFEST" \
  | kubectl apply --server-side --force-conflicts -f - \
  || { echo -e "\nERROR: kubectl apply of $MANIFEST failed\n"; exit 1; }
run kubectl wait --for condition=established --timeout=60s crd/locusttests.locust.io
run kubectl -n "$OPERATOR_NAMESPACE" rollout status deployment/$OPERATOR_NAME --timeout=300s
echo
echo "INFO: locust-k8s-operator is ready in namespace '$OPERATOR_NAMESPACE'"
