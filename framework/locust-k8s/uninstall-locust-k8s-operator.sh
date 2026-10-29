#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# USAGE: uninstall-locust-k8s-operator.sh [[NAMESPACE] KUBECONFIG]
#   NAMESPACE is where the operator was installed (default: locust-operator).
if [ "${BASH_SOURCE[0]}" != "$0" ]; then echo -e "\nWARNING: this script should not be sourced\n"; return 1; fi

OPERATOR_NAMESPACE=locust-operator
OPERATOR_NAME=locust-operator
if [ $# -ge 2 ]; then
  if [ -n "$1" ]; then OPERATOR_NAMESPACE=$1; fi
  shift
fi
if [ -n "$1" ]; then export KUBECONFIG=$1; fi

echo
echo "WARNING: this operator serves every namespace in the cluster."
echo kubectl -n $OPERATOR_NAMESPACE delete deployment,poddisruptionbudget,serviceaccount $OPERATOR_NAME --ignore-not-found
     kubectl -n $OPERATOR_NAMESPACE delete deployment,poddisruptionbudget,serviceaccount $OPERATOR_NAME --ignore-not-found
echo kubectl delete clusterrolebinding,clusterrole $OPERATOR_NAME --ignore-not-found
     kubectl delete clusterrolebinding,clusterrole $OPERATOR_NAME --ignore-not-found
echo
echo "The CRD was kept. Deleting it removes every LocustTest in the cluster:"
echo "  kubectl delete crd locusttests.locust.io"
echo
