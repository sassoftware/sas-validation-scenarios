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

echo
echo "INFO: Deleting namespace scoped resources:"
echo kubectl -n $TESTINGNAMESPACE delete -f $THISDIR/locust-k8s-operator.namespace-resources.yaml
     kubectl -n $TESTINGNAMESPACE delete -f $THISDIR/locust-k8s-operator.namespace-resources.yaml
echo
echo "WARNING: If you also want to delete the globally scoped resources, run the following commands:"
echo kubectl delete -f $THISDIR/locust-k8s-operator.global-resources.yaml
echo kubectl delete -f $THISDIR/locust-k8s-operator.global-crb.yaml
echo
