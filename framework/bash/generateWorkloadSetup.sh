#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


echo ""
echo "==================================="
echo "Script: $(basename "$0")"
echo "Script full path: $(realpath "$0")"
echo "Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "==================================="


# Check if the -w parameter is passed into the script
while getopts ":g:r:l:u:w:" opt; do
  case $opt in
    g)
      globalConfig=$OPTARG
      ;;  
    w)
      workloadsConfig=$OPTARG
      ;;    
    s)
      scenarioConfig=$OPTARG
      ;;  
    l)
      logLevel=$OPTARG
      ;;  
    u)
      usersFile=$OPTARG
      ;;
    h)  
      echo "Usage: $0 -g <globalConfig> -r <scenarioConfig> [-l <logLevel>]"
      echo ""
      echo "  -g  Path to the global configuration file (required)"
      echo "  -w  Path to the workloads configuration file (required)"
      # echo "  -s  Path to the scenario configuration file (required)"
      echo "  -u  Path to the users file (optional)"
      echo "  -l  Log level (optional: WARN, INFO, DEBUG, WARNING)"
      echo "  -h  Show this help message and exit"
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

if [ -z "$globalConfig" ]; then
  echo "Error: -g parameter is required. Please provide a valid global configuration file. Use -h for help." 
  exit 1
fi

if [ ! -f "$globalConfig" ]; then
  echo "Error: The specified global configuration file does not exist. ${configFile}.  Use -h for help." 
  exit 1
fi

if [ -z "$workloadsConfig" ]; then
  echo "Error: -w parameter is required. Please provide a valid workload configuration file. Use -h for help." 
  exit 1
fi

if [ ! -f "$workloadsConfig" ]; then
  echo "Error: The specified workload configuration file does not exist: ${workloadsConfig}. Use -h for help." 
  exit 1
fi

# if [ -z "$scenarioConfig" ]; then
#   echo "Error: -r parameter is required. Please provide a valid scenario name. Use -h for help." 
#   exit 1
# fi

# If the users file is passed in, validate it exists
if [ -n "$usersFile" ] && [ ! -f "$usersFile" ]; then
  echo "Error: The specified users file does not exist: ${usersFile}. Use -h for help." 
  exit 1
fi

globalConfigFullPath=$(realpath $globalConfig)
export globalConfigFullPath=$globalConfigFullPath

workloadsConfigFullPath=$(realpath $workloadsConfig)
export workloadsConfigFullPath=$workloadsConfigFullPath

# scenarioConfigFullPath=$(realpath $scenarioConfig)
# export scenarioConfigFullPath=$scenarioConfigFullPath

if [ -n "$usersFile" ]; then
  usersFileFullPath=$(realpath $usersFile)
  export usersFileFullPath=$usersFileFullPath
fi

timestamp=`date +%Y%m%d%H%M%S`

#Check if $backupGeneratedDir is set to true
echo "Checking if the backupGeneratedDir variable is set to true. value: ${backupGeneratedDir}"
if [ -d "generated" ] &&  [ -z "$backupGeneratedDir" ] && [[ "$backupGeneratedDir" != "false" ]] ; then
   echo "Renaming the existing 'generated' directory to 'generated-'${timestamp}"
   mv generated generated-${timestamp}
fi

generatedBaseDir="generated"
mkdir -p $generatedBaseDir

# Redirect stdout and stderr to a log file with a timestamp
mkdir -p $generatedBaseDir/logs
exec 3>&1 4>&2
trap 'exec 2>&4 1>&3' 0 1 2 3
exec > >(tee -a $generatedBaseDir/logs/generateWorkloadSetup${timestamp}.log) 2>&1

startTime=$(date +%s)
echo -e "Starting to generate workload setup artifacts... $(date +%H:%M:%S) \n"

echo "Using global config file: $globalConfig"
echo "Full path to global config file: $globalConfigFullPath"

echo "Full path to workload definition file: $workloadsConfigFullPath"

# echo "Using scenario config file: $scenarioConfig"
# echo -e "Full path to scenario config file: $scenarioConfigFullPath \n"

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

# Verify the the scenario location exists in scenariosLocationFullPath
if [ ! -d "${scenariosLocationFullPath}/${scenarioName}" ]; then
  echo "Error: The specified scenario (${scenarioName}) was not found. Scenario base location: ${scenariosLocationFullPath}" 
  exit 1
fi

#scenarioConfigFullPath=${scenariosLocationFullPath}/${scenarioConfig}
# if [ ! -f "$scenarioConfigFullPath" ]; then
#   echo "Error: The specified scenario configuration file does not exist. ${scenarioConfigFullPath}" 
#   exit 1
# else
#   echo "Using scenario config file: $scenarioConfig"
#   echo "Full path to scenario definition file: $scenarioConfigFullPath"  
# fi

commandLineArgs=" -g $globalConfigFullPath  -w $workloadsConfigFullPath "  
if [ -n "$usersFile" ]; then
  commndLineArgs="$commndLineArgs -u $usersFileFullPath"
fi

if [ -n "$logLevel" ]; then
  commandLineArgs+=" -l $logLevel"
  echo "Log level set to: $logLevel"
else
  logLevel="INFO"
  echo "Log level not set. Defaulting to: $logLevel"
fi

echo "Command line arguments for createWorkloadSetup.py: $commandLineArgs"
python3 ../framework/python/createWorkloadSetup.py $commandLineArgs

finishTime=$(date +%s)

# Calculate the total runtime
totalRuntime=$((finishTime - startTime))

# Convert total runtime to hours, minutes, and seconds
hours=$((totalRuntime / 3600))
minutes=$(( (totalRuntime % 3600) / 60 ))
seconds=$((totalRuntime % 60))

# echo ""
# echo "Completed running the scenario setup... $(date +%H:%M:%S)"
# echo "Total runtime: ${hours}h ${minutes}m ${seconds}s"
