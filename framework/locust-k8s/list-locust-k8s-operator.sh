#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

#if [ "${BASH_SOURCE[0]}" == "$0" ]; then IVE_BEEN_SOURCED=false; echo -e "\nWARNING: this script should     be sourced\n"; exit 1  ; else IVE_BEEN_SOURCED=true ; fi
if [ "${BASH_SOURCE[0]}" != "$0" ]; then IVE_BEEN_SOURCED=true ; echo -e "\nWARNING: this script should not be sourced\n"; return 1; else IVE_BEEN_SOURCED=false; fi
export THISDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

if [ "$1" != "" ]; then export TESTINGNAMESPACE=$1; fi
if [ "$2" != "" ]; then export KUBECONFIG=$2; fi
if [ "$2" == "" ]; then 
  echo -e "\nUSAGE: $0 \$TESTINGNAMESPACE  # or export TESTINGNAMESPACE & KUBECONFIG environment variables prior to running this script\n"
  exit 0
fi

if [ "$KUBECONFIG" == "" ]; then
  echo -e "\nERROR: KUBECONFIG must be exported prior to running this script\n"
  exit 1
else
  kubectl get ns 1>/dev/null 2>/dev/null
  RC_kgetns=$?
  if [ "$RC_kgetns" != "0" ]; then
    echo -e "\nERROR: 'kubectl get ns' failed, confirm you have exported an admin KUBECONFIG\n"
    exit $RC_kgetns
  fi
fi

echo
echo "#----------=----------# Globally scoped resources"
echo
echo "kubectl get CustomResourceDefinition,ClusterRole,ClusterRoleBinding | grep -e NAME -e locust"
      kubectl get CustomResourceDefinition,ClusterRole,ClusterRoleBinding | grep -e NAME -e locust
echo
echo "kubectl get -o json ClusterRoleBinding/locust-operator-locust-k8s-operator | jq -r '.subjects[] | [.kind,.name,.namespace] | @csv'"
      kubectl get -o json ClusterRoleBinding/locust-operator-locust-k8s-operator | jq -r '.subjects[] | [.kind,.name,.namespace] | @csv'
echo
echo "#----------=----------# Namespace scoped resources"
echo
echo "kubectl -n $TESTINGNAMESPACE get ServiceAccount,Role,RoleBinding,Deployment"
      kubectl -n $TESTINGNAMESPACE get ServiceAccount,Role,RoleBinding,Deployment
echo
