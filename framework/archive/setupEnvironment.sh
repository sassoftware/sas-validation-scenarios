#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


# Redirect stdout and stderr to a log file with a timestamp
# mkdir -p logs
# timestamp=`date +%Y%m%d%H%M%S`
# exec 3>&1 4>&2
# trap 'exec 2>&4 1>&3' 0 1 2 3
# exec 1>logs/setupEnvironment_${timestamp}.log 2>&1

# startTime=$(date +%s)
echo ""
echo -e "Setting up scenario environment...\n"

# Check if the -p parameter is passed into the script
OPTIND=1 # Ensure OPTIND is reset for each function call
while getopts ":p:" opt; do
  case $opt in
    p)
      configFile=$OPTARG
      ;;
    \?)
      echo "Invalid option: -$OPTARG" >&2
      exit 1
      ;;
    :)
      echo "Option -$OPTARG requires a valid configuration file." >&2
      exit 1
      ;;
  esac
done

# Ensure the configFile variable is set
if [ -z "$configFile" ]; then
  echo "Error: -p parameter is required. Please provide a valid configuration file." >&2
  exit 1
fi

echo "Using config file: $configFile"
echo ""

# Read each property from validation-config.yaml and assign them to local variables.
# The name of the variables should be in camel case instead of hyphanated. Also, do not use the root level 
# of the yaml hierarchy (validation-scenario) in the variables name.

# Read properties from the specified config file and assign them to local variables
description=$(yq e '.validation-scenario.description' "$configFile")
echo "Description: $description"
commonScriptsLocation=$(yq e '.validation-scenario.framework-resources-location' "$configFile")
echo "Location of shared script library: $commonScriptsLocation"
hostname=$(yq e '.validation-scenario.hostname' "$configFile")
echo "Hostname: $hostname"
sasAdminUser=$(yq e '.validation-scenario.sas-admin-user' "$configFile")
echo "SAS Admin User: $sasAdminUser"
sasAdminPasswd=$(yq e '.validation-scenario.sas-admin-passwd' "$configFile")
echo "SAS Admin Password: *****"
workingDir=$(yq e '.validation-scenario.working-dir' "$configFile")
echo "Working Directory: $workingDir"
casServer=$(yq e '.validation-scenario.cas.server' "$configFile")
echo "CAS Server: $casServer"
# casLib=$(yq e '.validation-scenario.cas.data-location' "$configFile")
# echo "CAS Library: $casLib"
# casTable=$(yq e '.validation-scenario.cas.source-data-table' "$configFile")
# echo "CAS Table: $casTable"
# createFolders=$(yq e '.validation-scenario.nfs.create-folders' "$configFile")
# echo "Create Folders: $createFolders"
server=$(yq e '.validation-scenario.nfs.server' "$configFile") 
echo "NFS Server: $server"
user=$(yq e '.validation-scenario.nfs.user' "$configFile")
echo "User: $user"
pemFile=$(yq e '.validation-scenario.pem-file' "$configFile")
echo "PEM File: $pemFile"  
kubeConfig=$(yq e '.validation-scenario.kube-config' "$configFile")
echo "KubeConfig: $kubeConfig"
# rootFolder=$(yq e '.validation-scenario.nfs.root-folder' "$configFile")
# echo -e "Root Folder: $rootFolder \n"
cliProfile=$(yq e '.validation-scenario.cli-profile' "$configFile")
echo "CLI Profile: $cliProfile"
# projectName=$(yq e '.validation-scenario.project-import.project-name' "$configFile")
# echo "Project Name: $projectName"
# projectLocation=$(yq e '.validation-scenario.project-import.project-zip-location' "$configFile")
# echo "Project Location: $projectLocation"
# validationResetScript=$(yq e '.validation-scenario.project-import.validation-reset-script' "$configFile")
# echo "Validation Reset Script: $validationResetScript"
workingDir=$(yq e '.validation-scenario.working-dir' "$configFile")
echo "Working Directory: $workingDir"
# importConverter=$(yq e '.validation-scenario.project-import.import-converter' "$configFile")
# echo "Import Converter: $importConverter"



# finishTime=$(date +%s)

# # Calculate the total runtime
# totalRuntime=$((finishTime - startTime))

# # Convert total runtime to hours, minutes, and seconds
# hours=$((totalRuntime / 3600))
# minutes=$(( (totalRuntime % 3600) / 60 ))
# seconds=$((totalRuntime % 60))

# echo ""
# echo "Completed scenario validation find... $(date +%H:%M:%S)"
# echo "Total runtime: ${hours}h ${minutes}m ${seconds}s"
