#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


# Redirect stdout and stderr to a log file with a timestamp
mkdir -p logs
timestamp=`date +%Y%m%d%H%M%S`
exec 3>&1 4>&2
trap 'exec 2>&4 1>&3' 0 1 2 3
exec 1>$global_log_path/resetModelStudioProjects_${timestamp}.log 2>&1

startTime=$(date +%s)
echo -e "Starting project reset... $(date +%H:%M:%S) \n"

# Check if the -p parameter is passed into the script
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

# ensure the configFile variable points to a valid file
if [ ! -f "$configFile" ]; then
  echo "Error: The specified configuration file does not exist." 
  exit 1
fi

configFileFullPath=$(realpath $configFile)
echo "Using config file: $configFile"
echo "Full path to config file: $configFileFullPath"

# Read properties from the specified config file into the current shell 
commonScriptsLocation=$(yq e '.validation-scenario.common-scripts-location' "$configFile")
source ${commonScriptsLocation}/setupEnvironment.sh -p $configFileFullPath

echo "Resetting CAS Table: ${casTable}"

sas-viya --profile ${cliProfile} -k batch jobs submit-pgm --pgm-path ${validationResetScript} --context default --watch-output --wait-no-results
