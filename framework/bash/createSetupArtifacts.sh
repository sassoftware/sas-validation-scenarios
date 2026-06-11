#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


echo ""
echo "==================================="
echo "Script: $(basename "$0")"
echo "Script full path: $(realpath "$0")"
echo "Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "==================================="

# Check if the -s & -g parameter is passed into the script
while getopts ":g:s:b:l:u:" opt; do
  case $opt in
    g)
      globalConfig=$OPTARG
      ;;  
    s)
      scenarioConfig=$OPTARG
      ;;    
    b)
      workloadSetupFullPath=$OPTARG
      ;;      
    l)
      logLevel=$OPTARG
      ;;  
    u)
      usersFile=$OPTARG
      ;;
    h)
      echo "Usage: $0 -g <globalConfig> -s <scenarioConfig> -b <workloadSetupFullPath> [-l <logLevel>]"
      echo ""
      echo "  -g  Path to the global configuration file (required)"
      echo "  -s  Path to the scenario definition file (required)"
      echo "  -b  Path to the workload setup directory (required)"
      echo "  -l  Log level (optional: WARN, INFO, DEBUG, WARNING)"
      echo "  -h  Show this help message and exit"
      exit 0  
      ;;  
    \?)
      echo "Invalid option: -$OPTARG" >&2
      exit 1
      ;;
    :)
      echo "Option -$OPTARG requires a valid scenario definition file." >&2
      exit 1
      ;;
  esac
done

# Ensure the scenarioConfig and globalConfig variables are set
if [ -z "$scenarioConfig" ]; then
  echo "Error: -s parameter is required. Please provide a valid scenario definition file." 
  exit 1
fi

if [ -z "$globalConfig" ]; then
  echo "Error: -g parameter is required. Please provide a valid global configuration file." 
  exit 1
fi

# if [ -z "$usersFile" ]; then
#   echo "Error: -u parameter is required. Please provide a valid users file. Use -h for help." 
#   exit 1
# fi

# ensure the scenarioConfig and globalConfig variables points to valid files
if [ ! -f "$scenarioConfig" ]; then
  echo "Error: The specified scenario definition file does not exist. ${configFile}" 
  exit 1
fi

if [ ! -f "$globalConfig" ]; then
  echo "Error: The specified global configuration file does not exist. ${configFile}" 
  exit 1
fi

if [ -z "$workloadSetupFullPath" ]; then
  echo "Error: -b parameter is required. Please provide a valid workload setup path." 
  exit 1
fi

# Ensure the workload setup path is a valid directory
if [ ! -d "$workloadSetupFullPath" ]; then
  echo "Error: The specified workload setup path does not exist or is not a directory: ${workloadSetupFullPath}" 
  exit 1
fi

if [ -n "$usersFile" ] && [ ! -f "$usersFile" ]; then
  echo "Error: The specified users file does not exist: ${usersFile}. Use -h for help." 
  exit 1
fi

scenarioConfigFullPath=$(realpath $scenarioConfig)
globalConfigFullPath=$(realpath $globalConfig)
scenarioBaseDir=$(dirname $scenarioConfigFullPath)

if [ -n "$usersFile" ]; then
  usersFileFullPath=$(realpath $usersFile)
fi

echo "Framework resources location: $frameworkScriptsLocationFullPath"

# Redirect stdout and stderr to a log file with a timestamp
mkdir -p $workloadSetupFullPath/logs
timestamp=`date +%Y%m%d%H%M%S`
exec 3>&1 4>&2
trap 'exec 2>&4 1>&3' 0 1 2 3
exec > >(tee -a $workloadSetupFullPath/logs/createConfigArtifacts_${timestamp}.log) 2>&1

export scenarioConfigFullPath=$scenarioConfigFullPath
export globalConfigFullPath=$globalConfigFullPath
export scenarioBaseDir=$scenarioBaseDir
export workloadSetupFullPath=$workloadSetupFullPath
echo "Scenario base directory: $scenarioBaseDir"
echo "Scenario config file: $scenarioConfig"
echo "Global config file: $globalConfig"
echo "Full path to scenario definition file: $scenarioConfigFullPath"
echo "Full path to global definition file: $globalConfigFullPath"
echo "Full path to scenario base directory: $scenarioBaseDir"
echo "Full path to workload setup directory: $workloadSetupFullPath"

startTime=$(date +%s)
echo -e "Starting to create artifacts for the  scenario... $(date +%H:%M:%S) \n"

echo "Using scenario definition file: $scenarioConfig"
echo "Full path to scenario definition file: $scenarioConfigFullPath"

# Read properties from the specified config file into the current shell 
buildDir=$workloadSetupFullPath/build
mkdir -p $buildDir
artifactsDir=$workloadSetupFullPath/artifacts
mkdir -p $artifactsDir

frameworkScriptsLocation=$(yq e '.global-config.framework-base-location' "$globalConfigFullPath")
frameworkScriptsLocationFullPath=$(realpath $frameworkScriptsLocation)
export frameworkScriptsLocationFullPath=$frameworkScriptsLocationFullPath
echo "Framework scripts location: $frameworkScriptsLocationFullPath"

frameworkDefaults=${frameworkScriptsLocationFullPath}"/framework-defaults.yaml"
frameworkDefaultsFullPath=$(realpath $frameworkDefaults)
if [ ! -f "$frameworkDefaultsFullPath" ]; then
  echo "Error: The specified framework defaults file does not exist. ${frameworkDefaults}" 
  exit 1
fi
export frameworkDefaultsFullPath=$frameworkDefaultsFullPath
echo "Framework defaults location: $frameworkDefaultsFullPath"


###loadConfiguration.py -w $workloadConfigFullPath -g $globalConfigFullPath -d $frameworkDefaultsFullPath -u $usersFileFullPath -p $buildDir

# Build up the command line arguments for the createWorkloadDefinitions.sh script
commndLineArgs="-s $scenarioConfigFullPath -g $globalConfigFullPath -d $frameworkDefaultsFullPath -p $buildDir"

if [ -n "$usersFile" ] && [ "$usersFile" != "none" ]; then
  commndLineArgs="$commndLineArgs -u $usersFileFullPath "
fi

echo "Command line arguments for loadConfiguration.py: $commndLineArgs"
python3 ${frameworkScriptsLocationFullPath}/python/loadConfiguration.py $commndLineArgs
echo "Source the generated variables..."
source "${buildDir}/setVariables.sh"

## Add calls to the framework scripts as needed to configure the environment for the validation scenario

## Begin framework scripts calls
#############################

echo -e "\nRunning createFolders.py ...\n"
python3 ${frameworkScriptsLocationFullPath}/python/createFolders.py -a $artifactsDir -t $frameworkScriptsLocationFullPath/python/templates/create-folders.sh.template -l $logLevel

echo -e "\nRunning createCasLibs.py ...\n"
python3 ${frameworkScriptsLocationFullPath}/python/createCasLibs.py -a $artifactsDir -t $frameworkScriptsLocationFullPath/python/templates/create-caslibs.sh.template -u $frameworkScriptsLocationFullPath/python/templates/load-cas-tables.sh.template -l $logLevel

echo -e "\nRunning createDataTransferScript.py ...\n"
python3 ${frameworkScriptsLocationFullPath}/python/createDataTransferScript.py -a $artifactsDir -t $frameworkScriptsLocationFullPath/python/templates/data-transfer.sh.template -l $logLevel

# Disabled for now
#echo -e "\nRunning createModelStudioImport.py ...\n"
#python3 ${frameworkScriptsLocationFullPath}/python/createModelStudioImport.py -p $buildDir -a $artifactsDir -r $scenarioBaseDir -t $frameworkScriptsLocationFullPath/python/templates/create-model-studio-import.sh.template -l $logLevel

echo -e "\nRunning createRunScenarioConfig.py ...\n"
python3 ${frameworkScriptsLocationFullPath}/python/createRunScenarioConfig.py -a $artifactsDir -l $logLevel

echo -e "\n\nCompleted creating the artifact setup scripts \n"

#############################
## End framewwork scripts calls

finishTime=$(date +%s)

# Calculate the total runtime
totalRuntime=$((finishTime - startTime))

# Convert total runtime to hours, minutes, and seconds
hours=$((totalRuntime / 3600))
minutes=$(( (totalRuntime % 3600) / 60 ))
seconds=$((totalRuntime % 60))

# echo ""
# echo "Completed running the scenario artifact build... $(date +%H:%M:%S)"
# echo "Total runtime: ${hours}h ${minutes}m ${seconds}s"
