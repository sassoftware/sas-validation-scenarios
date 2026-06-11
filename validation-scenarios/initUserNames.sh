#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


timestamp=`date +%Y%m%d%H%M%S`

generatedBaseDir="init_logs"
mkdir -p $generatedBaseDir

# Redirect stdout and stderr to a log file with a timestamp
mkdir -p $generatedBaseDir/logs
exec 3>&1 4>&2
trap 'exec 2>&4 1>&3' 0 1 2 3
exec > >(tee -a $generatedBaseDir/initValidationScenarios_${timestamp}.log) 2>&1

while getopts ":u:n:" opt; do
  case $opt in
    u)
      usersFile=$OPTARG
      ;;
    n)
      namespace=$OPTARG
      ;;  
    h)
      echo "Usage: $0 -u <users csv file> -n <namespace>"
      echo ""
      echo "  -u  Path to the users file (required)"
      echo "  -n  Kubernetes namespace (required)"
      exit 0
      ;;
    \?)
      echo "Invalid option: -$OPTARG. Use -h for help." >&2
      exit 1
      ;;
    :)
      echo "Error: Option -$OPTARG requires a valid file path for the corresponding configuration. Use -h for help." >&2
      exit 1
      ;;
  esac
done

## Validate required parameters
if [ -z "$usersFile" ]; then
  echo "Error: -u parameter is required. Please provide a valid users file. Use -h for help." 
  exit 1
fi
if [ ! -f "$usersFile" ]; then
  echo "Error: The specified users file does not exist: ${usersFile}. Use -h for help." 
  exit 1
fi

if [ -z "$namespace" ]; then
  echo "Error: -n parameter is required. Please provide a valid Kubernetes namespace. Use -h for help." 
  exit 1
fi

## Validate that kubectl is installed
if ! command -v kubectl &> /dev/null
then
    echo "kubectl could not be found, please install it to proceed"
    exit 1
fi

## Validate that KUBECONFIG is set
if [ -z "$KUBECONFIG" ]; then
  echo "Error: KUBECONFIG environment variable is not set. Please set it to point to your kubeconfig file."
  exit 1
fi

## Validate that python3 is installed
if ! command -v python3 &> /dev/null
then
    echo "python3 could not be found, please install it to proceed"
    exit 1
fi

echo "Starting initialization of test users..."
startTime=$(date +%s)

echo "Using namespace: $namespace"
export namespace=$namespace

# echo "Creating namespace $namespace if it doesn't exist..."
# kubectl get namespace $namespace >/dev/null 2>&1 || kubectl create namespace $namespace

# ## Install the Locust operator in the specified namespace if it does not exist
# echo "Install the Locust operator in namespace $namespace if it is not already installed..."
# kubectl get deployment locust-operator-locust-k8s-operator -n $namespace >/dev/null 2>&1 || ../framework/locust-k8s/install-locust-k8s-operator.sh $namespace $KUBECONFIG

# You can run the following script to list all the resources that were just created
# ../framework/locust-k8s/list-locust-k8s-operator.sh $namespace $KUBECONFIG

# echo "Adding required python packages..."
# pip install kubernetes
# pip install cryptography
# pip install pyyaml
# pip install deepmerge
# pip install yaspin
# pip install debugpy

echo "Loading users users file to K8s Secrets: $usersFile"
python3  ../framework/python/initUsersListSecrets.py -f $usersFile -n $namespace -l INFO


finishTime=$(date +%s)

# Calculate the total runtime
totalRuntime=$((finishTime - startTime))

# Convert total runtime to hours, minutes, and seconds
hours=$((totalRuntime / 3600))
minutes=$(( (totalRuntime % 3600) / 60 ))
seconds=$((totalRuntime % 60))

echo ""
echo "Completed initialization of validation scenarios."
echo "Total runtime: ${hours}h ${minutes}m ${seconds}s"
