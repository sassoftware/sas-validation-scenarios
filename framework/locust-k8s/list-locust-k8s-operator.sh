#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# USAGE: list-locust-k8s-operator.sh [[NAMESPACE] KUBECONFIG]
#   NAMESPACE is where the operator was installed (default: locust-operator).
if [ "${BASH_SOURCE[0]}" != "$0" ]; then echo -e "\nWARNING: this script should not be sourced\n"; return 1; fi

OPERATOR_NAMESPACE=locust-operator
OPERATOR_NAME=locust-operator
if [ $# -ge 2 ]; then
  if [ -n "$1" ]; then OPERATOR_NAMESPACE=$1; fi
  shift
fi
if [ -n "$1" ]; then export KUBECONFIG=$1; fi

if ! kubectl get ns >/dev/null 2>&1; then
  echo -e "\nERROR: 'kubectl get ns' failed, confirm you have exported an admin KUBECONFIG\n"
  exit 1
fi

echo
echo "#----------=----------# CRD versions"
kubectl get crd locusttests.locust.io -o jsonpath='{range .spec.versions[*]}{.name} served={.served} storage={.storage}{"\n"}{end}'
echo
echo "#----------=----------# Globally scoped resources"
kubectl get clusterrole,clusterrolebinding $OPERATOR_NAME
echo
echo "#----------=----------# Resources in namespace $OPERATOR_NAMESPACE"
kubectl -n $OPERATOR_NAMESPACE get deployment,pod,serviceaccount,poddisruptionbudget
echo
