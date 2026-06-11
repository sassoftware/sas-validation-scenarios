#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

#if [ "${BASH_SOURCE[0]}" == "$0" ]; then IVE_BEEN_SOURCED=false; echo -e "\nWARNING: this script should     be sourced\n"; exit 1  ; else IVE_BEEN_SOURCED=true ; fi
if [ "${BASH_SOURCE[0]}" != "$0" ]; then IVE_BEEN_SOURCED=true ; echo -e "\nWARNING: this script should not be sourced\n"; return 1; else IVE_BEEN_SOURCED=false; fi
export THISDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

if [ "$1" != "" ]; then export TESTINGNAMESPACE=$1; fi # override exported TESTINGNAMESPACE env var if set via cmd line arg
if [ "$2" != "" ]; then export KUBECONFIG=$2; fi       # override exported KUBECONFIG env var if set via cmd line arg
if [ "$TESTINGNAMESPACE" == "" ] && [ "$KUBECONFIG" == "" ]; then 
  echo
  echo "USAGE: $0 \$TESTINGNAMESPACE \$KUBECONFIG"
  echo "# alternatively, you can export TESTINGNAMESPACE & KUBECONFIG env variables prior to running the script without any args"
  echo
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
echo "INFO: Create globally scoped ClusterRole & CustomResourceDefinition "
echo kubectl apply -f $THISDIR/locust-k8s-operator.global-resources.yaml
     kubectl apply -f $THISDIR/locust-k8s-operator.global-resources.yaml

echo
echo "INFO: Create ClusterRoleBinding (CRB) if not yet created (so as to not wipe out its pre-existing 'namespace ServiceAccount subjects')"
crblist=$( kubectl get ClusterRoleBinding/locust-operator-locust-k8s-operator --no-headers 2>/dev/null )
if [ "$crblist" == "" ]; then
  echo
  echo "INFO: ClusterRoleBinding/locust-operator-locust-k8s-operator does not exist, so I will create it"
  echo kubectl apply -f $THISDIR/locust-k8s-operator.global-crb.yaml
       kubectl apply -f $THISDIR/locust-k8s-operator.global-crb.yaml
fi

echo
echo "INFO: If TESTINGNAMESPACE($TESTINGNAMESPACE) ServiceAccount is not in the CRB, then add it"
checkCRB=$( kubectl get -o json ClusterRoleBinding/locust-operator-locust-k8s-operator | jq ".subjects[] | select( .namespace == \"$TESTINGNAMESPACE\" )" )
if [ "$checkCRB" == "" ]; then
  echo
  echo "      adding to CRB"
  echo kubectl patch ClusterRoleBinding locust-operator-locust-k8s-operator --type=json -p \"[{\\\"op\\\": \\\"add\\\", \\\"path\\\": \\\"/subjects/-\\\", \\\"value\\\": {\\\"kind\\\":\\\"ServiceAccount\\\",\\\"name\\\":\\\"locust-operator-locust-k8s-operator\\\",\\\"namespace\\\":\\\"$TESTINGNAMESPACE\\\"} }]\"
       kubectl patch ClusterRoleBinding locust-operator-locust-k8s-operator --type=json -p  "[{\"op\": \"add\", \"path\": \"/subjects/-\", \"value\": {\"kind\":\"ServiceAccount\",\"name\":\"locust-operator-locust-k8s-operator\",\"namespace\":\"$TESTINGNAMESPACE\"} }]"
else
  echo "      already exists in CRB"
fi
echo "INFO: The following namespace scoped locust-k8s-operator ServiceAccount 'subjects' are granted the ClusterRole via this CRB (ClusterRoleBinding):"
echo "kubectl get -o json ClusterRoleBinding/locust-operator-locust-k8s-operator | jq -r '.subjects[] | [.kind,.name,.namespace] | @csv'"
      kubectl get -o json ClusterRoleBinding/locust-operator-locust-k8s-operator | jq -r '.subjects[] | [.kind,.name,.namespace] | @csv'

# Create namespace scoped resources
echo
echo kubectl -n $TESTINGNAMESPACE apply -f $THISDIR/locust-k8s-operator.namespace-resources.yaml
     kubectl -n $TESTINGNAMESPACE apply -f $THISDIR/locust-k8s-operator.namespace-resources.yaml

# Wait for pod to exist then wait for pod to reach condition = ContainersReady
echo
echo -n "INFO: Wait for locust-k8s-operator pod to exist..." #, then wait for it to reach ContainersReady condition"
iseethepod=false
for iii in {0..60}; do  # 1 minute timeout
  podlist=$( kubectl -n $TESTINGNAMESPACE get pod -l "app.kubernetes.io/name"="locust-k8s-operator" --no-headers 2>/dev/null | awk '{print $1}' )
  if echo "$podlist" | grep -q locust-k8s-operator; then iseethepod=true; break; else echo -n .; sleep 1s; fi
done
if ! $iseethepod; then echo; echo "ERROR: I waited for 60s, but still dont see the pod... this is unexpected and may require admin help"; echo; exit 1; fi
echo DONE
echo
echo "INFO: Wait for locust-k8s-operator pod to reach ContainersReady condition"
echo kubectl -n $TESTINGNAMESPACE wait --for=condition=ContainersReady pod -l 'app.kubernetes.io/name'='locust-k8s-operator' --timeout=300s
     kubectl -n $TESTINGNAMESPACE wait --for=condition=ContainersReady pod -l 'app.kubernetes.io/name'='locust-k8s-operator' --timeout=300s
RC_kwaitcrdy=$?; if [ "$RC_kwaitcrdy" != "0" ]; then echo; echo "ERROR: Timed out waiting on locust-k8s-operator pod to reach condition = ContainersReady... fix this before proceeding."; echo; exit $RC_kwaitcrdy; fi
echo
echo "INFO: This script has completed successfully"
echo
