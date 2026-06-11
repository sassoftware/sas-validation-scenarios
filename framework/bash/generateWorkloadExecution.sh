#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


# Check if the -w parameter is passed into the script
while getopts ":g:w:o:l:u:" opt; do
  case $opt in
    g)
      globalConfig=$OPTARG
      ;;  
    w)
      workloadsConfig=$OPTARG
      ;;  
    o)
      workloadsOverrides=$OPTARG
      ;;  
    l)
      logLevel=$OPTARG
      ;;
    u)
      usersFile=$OPTARG
      ;;  
    h)
      echo "Usage: $0 -g <globalConfig> -w <workloadsConfig> [-o <workloadsOverrides>] [-l <logLevel>]"
      echo ""
      echo "  -g  Path to the global configuration file (required)"
      echo "  -w  Path to the workloads configuration file (required)"
      echo "  -o  Path to the workloads overrides file (optional)"
      echo "  -l  Log level (optional: WARN, INFO, DEBUG, WARNING)"
      echo "  -u  Path to the users file (optional)"
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

# if [ -z "$usersFile" ]; then
#   echo "Error: -u parameter is required. Please provide a valid users file. Use -h for help." 
#   exit 1
# fi

if [ ! -f "$globalConfig" ]; then
  echo "Error: The specified global configuration file does not exist: ${configFile}. Use -h for help." 
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

if [ -n "$usersFile" ] && [ ! -f "$usersFile" ]; then
  echo "Error: The specified users file does not exist: ${usersFile}. Use -h for help." 
  exit 1
fi

globalConfigFullPath=$(realpath $globalConfig)
export globalConfigFullPath=$globalConfigFullPath

workloadsConfigFullPath=$(realpath $workloadsConfig)
export workloadsConfigFullPath=$workloadsConfigFullPath

if [ -z "$usersFile" ]; then
  usersFile="none"
  echo "INFO: -u parameter is not set. No users file will be applied."
else
  echo "Using users file: $usersFile"
  usersFileFullPath=$(realpath $usersFile)
  export usersFileFullPath=$usersFileFullPath 
fi  



# Check if the workloadsOverrides parameter is passed into the script
if [ -n "$workloadsOverrides" ]; then
  workloadsOverridesFullPath=$(realpath $workloadsOverrides)
  export workloadsOverridesFullPath=$workloadsOverridesFullPath
fi

timestamp=`date +%Y%m%d%H%M%S`

#Check if $backupGeneratedDir is set to true
echo "Checking if the backupGeneratedDir variable is set to true. value: ${backupGeneratedDir}"
if [ -d "generated" ] &&  [ -z "$backupGeneratedDir" ] && [[ "$backupGeneratedDir" != "false" ]] ; then
   echo "Renaming the existing 'generated' directory to 'generated-'${timestamp}."
   mv generated generated-${timestamp}
fi

generatedBaseDir="generated"
mkdir -p $generatedBaseDir

# Redirect stdout and stderr to a log file with a timestamp
mkdir -p $generatedBaseDir/logs
exec 3>&1 4>&2
trap 'exec 2>&4 1>&3' 0 1 2 3
exec > >(tee -a $generatedBaseDir/logs/generateWorkloadExecution${timestamp}.log) 2>&1

startTime=$(date +%s)
echo -e "Starting to generate workload execution artifacts... $(date +%H:%M:%S) \n"

echo "Using global config file: $globalConfig"
echo "Full path to workload definition file: $globalConfigFullPath"

echo "Using workload config file: $workloadsConfig"
echo "Full path to workload definition file: $workloadsConfigFullPath"

if [ -n "$usersFile" ]; then
  echo "Using users file: $usersFile"
  echo "Full path to users file: $usersFileFullPath"
fi

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

frameworkDefaults=${frameworkScriptsLocationFullPath}"/framework-defaults.yaml"
frameworkDefaultsFullPath=$(realpath $frameworkDefaults)
if [ ! -f "$frameworkDefaultsFullPath" ]; then
  echo "Error: The specified framework defaults file does not exist. ${frameworkDefaults}" 
  exit 1
fi
export frameworkDefaultsFullPath=$frameworkDefaultsFullPath
echo "Framework defaults location: $frameworkDefaultsFullPath"

# Build up the command line arguments for the createWorkloadDefinitions.sh script
commndLineArgs="-g $globalConfigFullPath -w $workloadsConfigFullPath "

if [ -n "$usersFile" ] && [ "$usersFile" != "none" ]; then
  commndLineArgs="$commndLineArgs -u $usersFileFullPath"
fi

if [ -n "$workloadsOverrides" ]; then
  commndLineArgs="$commndLineArgs -o $workloadsOverridesFullPath"
fi

if [ -n "$logLevel" ]; then
  commndLineArgs="$commndLineArgs -l $logLevel"
  echo "Log level set to: $logLevel"
else
  logLevel="INFO"
  echo "Log level not set. Defaulting to: $logLevel"
fi

echo "Command line arguments for workload execution generation: $commndLineArgs"
python3 ../framework/python/createWorkloadDefinitions.py $commndLineArgs

echo "All of the workload definitions have been processed."
