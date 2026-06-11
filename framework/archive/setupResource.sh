#!/usr/bin/env bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


## WIP. THIS SCRIPT IS NOT FULLY IMPLEMENTED.

# Redirect stdout and stderr to a log file with a timestamp
mkdir -p logs
timestamp=$(date +%Y%m%d%H%M%S)
exec 3>&1 4>&2
trap 'exec 2>&4 1>&3' 0 1 2 3
exec 1>$global_log_path/setupResource_${timestamp}.log 2>&1

startTime=$(date +%s)
echo -e "Starting configuration of the server... $(date +%H:%M:%S) \n"

currentPath=$(dirname $(realpath "$0"))
echo "Current path: $currentPath"
echo "Common scripts location: $commonScriptsLocation"

## Add calls to the framework scripts as needed to configure the server for the validation scenario

## Begin framework scripts calls
#############################

resourceConfigFile=$currentPath/resource-config.yaml
echo "Using local config file: $resourceConfigFile"

. $currentPath/loadResourceConfig.sh -p $resourceConfigFile

echo -e "Creating folders and transfering data to the NFS server \n"
${commonScriptsLocation}/setupNFS.sh 

echo -e "Creating caslibs needed for the validation scenario \n"
# ${commonScriptsLocation}/setupCAS.sh #-p "$configFile"

echo -e "Importing projects into the SAS Viya environment for each user in the configuration file \n"
# ${commonScriptsLocation}/importModelStudioProjects.sh #-p "$configFile"

#############################
## End framework scripts calls

finishTime=$(date +%s)

# Calculate the total runtime
totalRuntime=$((finishTime - startTime))

# Convert total runtime to hours, minutes, and seconds
hours=$((totalRuntime / 3600))
minutes=$(( (totalRuntime % 3600) / 60 ))
seconds=$((totalRuntime % 60))

echo ""
echo "Completed configuration of the server... $(date +%H:%M:%S)"
echo "Total runtime: ${hours}h ${minutes}m ${seconds}s"
