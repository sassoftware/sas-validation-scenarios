#!/usr/bin/env bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


echo "==================================="
echo "Script: $(basename "$0")"
echo "Script full path: $(realpath "$0")"
echo "Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "==================================="

# Check if the -w parameter is passed into the script
while getopts ":w:g:d:l:u:" opt; do
  case $opt in
    w)
      workloadConfig=$OPTARG
      ;;
    g)
      globalConfig=$OPTARG
      ;;  
    d)
      frameworkDefaults=$OPTARG
      ;;  
    l)
      logLevel=$OPTARG
      ;;    
    u)
      usersFile=$OPTARG
      ;;  
    h)
      echo "Usage: $0 -w <workloadConfig> -g <globalConfig> -d <frameworkDefaults> [-l <logLevel>]"
      echo ""
      echo "  -w  Path to the workload definition file (required)"
      echo "  -g  Path to the global configuration file (required)"
      echo "  -d  Path to the framework defaults file (required)"
      echo "  -l  Log level (optional: WARN, INFO, DEBUG, WARNING)"
      echo "  -u  Path to the users file (optional)"
      echo "  -h  Show this help message and exit"
      exit 0  
      ;;  
    \?)
      echo "Invalid option: -$OPTARG" >&2
      exit 1
      ;;
    :)
      echo "Option -$OPTARG requires a valid workload definition file." >&2
      exit 1
      ;;
  esac
done

# Ensure the workloadConfig and globalConfig variables are set
if [ -z "$workloadConfig" ]; then
  echo "Error: -w parameter is required. Please provide a valid workload definition file." 
  exit 1
fi

if [ -z "$globalConfig" ]; then
  echo "Error: -g parameter is required. Please provide a valid global configuration file." 
  exit 1
fi

# Ensure the frameworkDefaults variable is set
if [ -z "$frameworkDefaults" ]; then
  echo "Error: -d parameter is required. Please provide a valid framework defaults file." 
  exit 1
fi

# ensure the workloadConfig and globalConfig variables points to valid files
if [ ! -f "$workloadConfig" ]; then
  echo "Error: The specified workload definition file does not exist: ${workloadConfig}" 
  exit 1
fi

if [ ! -f "$globalConfig" ]; then
  echo "Error: The specified global configuration file does not exist: ${globalConfig}" 
  exit 1
fi

# if [ ! -f "$usersFile" ]; then
#   echo "Error: The specified users file does not exist: ${usersFile}" 
#   exit 1
# fi

# Ensure the frameworkDefaults variable points to a valid file
if [ ! -f "$frameworkDefaults" ]; then
  echo "Error: The specified framework defaults file does not exist: ${frameworkDefaults}" 
  exit 1
fi

workloadConfigFullPath=$(realpath $workloadConfig)
globalConfigFullPath=$(realpath $globalConfig)
frameworkDefaultsFullPath=$(realpath $frameworkDefaults)


if [ -n "$usersFile" ]; then
  usersFileFullPath=$(realpath $usersFile)
fi

export workloadConfigFullPath=$workloadConfigFullPath
export globalConfigFullPath=$globalConfigFullPath
export frameworkDefaultsFullPath=$frameworkDefaultsFullPath

if [ -n "$usersFile" ]; then
  export usersFileFullPath=$usersFileFullPath
fi

# Redirect stdout and stderr to a log file with a timestamp
workloadBaseDir=$(dirname $workloadConfigFullPath)
mkdir -p $workloadBaseDir/logs
timestamp=`date +%Y%m%d%H%M%S`
exec 3>&1 4>&2
trap 'exec 2>&4 1>&3' 0 1 2 3
exec > >(tee -a $workloadBaseDir/logs/createWorkloadArtifacts_${timestamp}.log) 2>&1

startTime=$(date +%s)
echo -e "Starting to create artifacts for the  workload... $(date +%H:%M:%S) \n"

echo "Using workload definition file: $workloadConfig"
echo "Full path to workload definition file: $workloadConfigFullPath"

# Read properties from the specified config file into the current shell 
buildDir=$workloadBaseDir/build
mkdir -p $buildDir
artifactsDir=$workloadBaseDir/artifacts
mkdir -p $artifactsDir

if [ -n "$logLevel" ]; then
  ## TODO Add commandline args code
  commandLineArgs+=" -l $logLevel"
  echo "Log level set to: $logLevel"
else
  logLevel="INFO"
  echo "Log level not set. Defaulting to: $logLevel"
fi


echo "Framework resources location: $frameworkScriptsLocationFullPath"

# export scenariosFullPath=$(realpath $scenariosBaseLocation)
# echo "Scenarios folder full path: $scenariosFullPath"

#python3 ${frameworkScriptsLocationFullPath}/python/loadConfiguration.py -w $workloadConfigFullPath -g $globalConfigFullPath -d $frameworkDefaultsFullPath -u $usersFileFullPath -p $buildDir

# Build up the command line arguments for the createWorkloadDefinitions.sh script
commandLineArgs="-w $workloadConfigFullPath -g $globalConfigFullPath -d $frameworkDefaultsFullPath -p $buildDir"

if [ -n "$usersFile" ] && [ "$usersFile" != "none" ]; then
  commandLineArgs="$commandLineArgs -u $usersFileFullPath "
fi

echo ">> Command line arguments for loadConfiguration: $commandLineArgs"
python3 ${frameworkScriptsLocationFullPath}/python/loadConfiguration.py $commandLineArgs
echo -e "Source the generated variables... \n"
source "${buildDir}/setVariables.sh"


## Add calls to the framework scripts as needed to configure the environment for the validation scenario

## Begin framework scripts calls
#############################

# Copy the users file to the artifacts directory, if it was passed in
if [ -n "$usersFile" ]; then
  echo "Copying the users file to the artifacts directory as : $artifactsDir/users.csv"
  cp $usersFileFullPath $artifactsDir/users.csv
fi

# Create the custom resources
python3 ${frameworkScriptsLocationFullPath}/python/createCustomResource.py -a $artifactsDir -t $frameworkScriptsLocationFullPath/python/templates/k8s-custom-resource.yaml.template

# Create the config map script
python3 ${frameworkScriptsLocationFullPath}/python/createConfigMapCommand.py -a $artifactsDir -l $logLevel

# Create the run workload script
python3 ${frameworkScriptsLocationFullPath}/python/createRunWorkloadScript.py -a $artifactsDir -t $frameworkScriptsLocationFullPath/python/templates/run-workload.sh.template -ht $frameworkScriptsLocationFullPath/python/templates/run-workload-log-header.sh.template -l $logLevel

#############################
## End framewwork scripts calls
