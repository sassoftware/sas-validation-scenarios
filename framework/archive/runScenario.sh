#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


# Run a scenario that is defined in the ./scenarios directory 
# This script generates workload artifacts based on the scenario provided in the -s parameter
# and the global configuration file provided in the -g parameter.
# The generated workload artifacts are stored in the ./generated directory
# and the logs are stored in the ./generated/logs directory.

# The workload definition file used running the scenario is created in the ./generated/workload-execution/{scenario-name} directory.

# Usage: ./runScenario.sh -g <global-config-file> -s <scenario-name>

# Check if the -w parameter is passed into the script
while getopts ":g:s:o:" opt; do
  case $opt in
    g)
      globalConfig=$OPTARG
      ;;  
    s)
      scenarioName=$OPTARG
      ;;  
     o)
      workloadsOverrides=$OPTARG
      ;;    
    \?)
      echo "Invalid option: -$OPTARG" >&2
      exit 1
      ;;
    :)
      echo "Option -$OPTARG requires valid options." >&2
      exit 1
      ;;
  esac
done

if [ -z "$globalConfig" ]; then
  echo "Error: -g parameter is required. Please provide a valid global configuration file." 
  exit 1
fi

if [ ! -f "$globalConfig" ]; then
  echo "Error: The specified global configuration file does not exist. ${configFile}" 
  exit 1
fi

if [ -z "$scenarioName" ]; then
  echo "Error: -s parameter is required. Please provide a valid scenario name." 
  exit 1
fi

globalConfigFullPath=$(realpath $globalConfig)
export globalConfigFullPath=$globalConfigFullPath

# Check if the workloadsOverrides parameter is passed into the script
if [ -n "$workloadsOverrides" ]; then
  workloadsOverridesFullPath=$(realpath $workloadsOverrides)
  export workloadsOverridesFullPath=$workloadsOverridesFullPath
fi

timestamp=`date +%Y%m%d%H%M%S`

# Set the backupGeneratedDir variable to false so that later scripts can check if the generated directory was backed up
export backupGeneratedDir="false"
if [ -d "generated" ]; then
  echo "Renaming the existing 'generated' directory to 'generated-'${timestamp}"
  mv generated generated-${timestamp}
  #We don't want downstream scripts to backup the generated directory, so we set an environment variable
  export backupGeneratedDir="false"
fi


generatedBaseDir="generated"
mkdir $generatedBaseDir
export generatedBaseDir=$generatedBaseDir

# Redirect stdout and stderr to a log file with a timestamp
mkdir -p $generatedBaseDir/logs
exec 3>&1 4>&2
trap 'exec 2>&4 1>&3' 0 1 2 3
exec > >(tee -a $generatedBaseDir/logs/generateWorkloadDefinition${timestamp}.log) 2>&1

startTime=$(date +%s)
echo -e "Starting to generate a workload artifact... $(date +%H:%M:%S) \n"

echo "Using global config file: $globalConfig"
echo "Full path to workload definition file: $globalConfigFullPath"

buildDir=$generatedBaseDir/build
echo "Creating build directory: $buildDir"
mkdir -p $buildDir

frameworkScriptsLocation=$(yq e '.global-config.framework-base-location' "$globalConfig")
frameworkScriptsLocationFullPath=$(realpath $frameworkScriptsLocation)
export frameworkScriptsLocationFullPath=$frameworkScriptsLocationFullPath
echo "Framework scripts location: $frameworkScriptsLocationFullPath"

scenariosLocation=$(yq e '.global-config.scenarios-base-location' "$globalConfig")
scenariosLocationFullPath=$(realpath $scenariosLocation)
export scenariosLocationFullPath=$scenariosLocationFullPath
echo "Scenarios location: $scenariosLocationFullPath "

export scriptBasePath=$(pwd)

# Verify the the scenario location exists in scenariosLocationFullPath
if [ ! -d "${scenariosLocationFullPath}/${scenarioName}" ]; then
  echo "Error: The specified scenario (${scenarioName}) was not found. Scenario base location: ${scenariosLocationFullPath}" 
  exit 1
fi

if [ -z "$workloadsOverrides" ]; then
  python3 ../framework/python/createWorkloadDefinitionFromScenario.py \
      -g $globalConfigFullPath \
      -s $scenariosLocationFullPath \
      -n $scenarioName \
      -p $generatedBaseDir/build

else
  python3 ../framework/python/createWorkloadDefinitionFromScenario.py \
      -g $globalConfigFullPath \
      -o $workloadsOverridesFullPath \
      -s $scenariosLocationFullPath \
      -n $scenarioName \
      -p $generatedBaseDir/build

fi
 
echo "Scenario have been processed."

finishTime=$(date +%s)

# Calculate the total runtime
totalRuntime=$((finishTime - startTime))

# Convert total runtime to hours, minutes, and seconds
hours=$((totalRuntime / 3600))
minutes=$(( (totalRuntime % 3600) / 60 ))
seconds=$((totalRuntime % 60))

echo ""
echo "Completed running the scenario... $(date +%H:%M:%S)"
echo "Total runtime: ${hours}h ${minutes}m ${seconds}s"
