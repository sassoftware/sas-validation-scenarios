#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


# Redirect stdout and stderr to a log file with a timestamp
mkdir -p logs
timestamp=`date +%Y%m%d%H%M%S`
exec 3>&1 4>&2
trap 'exec 2>&4 1>&3' 0 1 2 3
exec 1>$global_log_path/getTokenFromViyaCLI_${timestamp}.log 2>&1

startTime=$(date +%s)
echo -e "Getting auth token from Viya CLI... $(date +%H:%M:%S) \n"

# Check if the -p parameter is passed into the script
while getopts ":p:" opt; do
  case $opt in
    p)
      profileName=$OPTARG
      ;;
    \?)
      echo "Invalid option: -$OPTARG" >&2
      exit 1
      ;;
    :)
      echo "Option -$OPTARG requires a valid profile name (or Default if profiles not used)." >&2
      exit 1
      ;;
  esac
done

# Ensure the configFile variable is set
if [ -z "$profileName" ]; then
  echo "Error: -p parameter is required. Please provide a valid configuration file." >&2
  exit 1
fi

#Ensure the SAS Viya CLI is installed and available in the default PATH
if [ ! -f "$(command -v ~/.sas/credentials.json)" ]; then
  echo "Error: The SAS Viya CLI credentials file was not found in the expected path." >&2
  exit 1
fi

REFRESH_TOKEN=$(jq -r --arg profileName "$profileName" '.[$profileName]["refresh-token"]' ~/.sas/credentials.json)
if [ -z "$REFRESH_TOKEN" ]; then
  echo "Error: The refresh token for profile ${profileName} was not found in the SAS Viya CLI credentials file (~/.sas/credentials.json)." >&2
  exit 1
fi

#Write the refresh token to a file in the build directory
d
