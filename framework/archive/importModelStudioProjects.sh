#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


# Redirect stdout and stderr to a log file with a timestamp
mkdir -p logs
timestamp=`date +%Y%m%d%H%M%S`
exec 3>&1 4>&2
trap 'exec 2>&4 1>&3' 0 1 2 3
exec 1>$global_log_path/importProjects_${timestamp}.log 2>&1

startTime=$(date +%s)
echo -e "Starting project imports... $(date +%H:%M:%S) \n"

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

echo "Importing projects..."

getUserToken() {
  local username=$1
  local password=$2

  echo "Getting token for user: $username"

  echo ">>>>>>>>>>>><<<<<<<<<<<<<<"
  echo "hostname: $hostname"
  echo "sasClientId: $sasClientId"
  echo "sasValidationSecret: $sasValidationSecret"
  echo "username: $username"
  echo "password: $password"
  echo "workingDir: $workingDir" 

  curl -ks --location "https://${hostname}/SASLogon/oauth/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=password&username=${username}&password=${password}" \
    -u "${sasClientId}:${sasValidationSecret}" \
    > "${workingDir}/__accessToken_"${username}".json"
   
}

token=""
getAdminToken() {
  echo "Getting admin token for sas admin: $sasAdminUser"

  # Get auth token for sas admin
  curl -ks --location "https://${hostname}/SASLogon/oauth/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=password&username=${sasAdminUser}&password=${sasAdminPasswd}" \
    -u "${sasClientId}:${sasValidationSecret}" \
    > "${workingDir}/__accessToken_"${sasAdminUser}".json"

  token=$(jq -r '.access_token' "${workingDir}/__accessToken_"${sasAdminUser}".json")
   
}


importProject() {
  local username=$1
  local password=$2
  local projectName=$3
  local projectLocation=$4

  echo "Importing project for user: $username, project: $projectName, location: $projectLocation"

  ## Import the project
  curl -k --location "https://${hostname}/analyticsGateway/archives/import?dataUri=%2FdataTables%2FdataSources%2Fcas~fs~${casServer}~fs~${casLib}%2Ftables%2F${casTable}" \
    -X POST \
    --header "Authorization: Bearer ${token}" \
    --header "Accept: application/vnd.sas.transfer.import.job+json" \
    --header "Accept-Encoding: gzip, deflate, br, zstd" \
    --header 'Accept-Language: en-US,en;q=0.9' \
    --header "Content-Type: application/octet-stream" \
    --data-binary @"${projectLocation}" \
     > "${workingDir}/__importResponse_${username}.json"

   ## Read the state rel from importResponse.json
   state_rel=$(jq -r '.links[] | select(.rel == "state") | .href' "${workingDir}/__importResponse_${username}.json")
   echo "state_rel=$state_rel"

   ## Get the state for the transfer job.  Once it's running we'll pop out and start the next transfer
   state=""

   maxRetries=10
   retries=0
   while [ "$state" != "running" ] && [ "$state" != "completed" ] && [ $retries -lt $maxRetries ]; do

     curl -k --location "https://${hostname}${state_rel}" \
     --header "Authorization: Bearer ${token}" \
     --header "Accept: application/json" \
      > "${workingDir}/__transferState.json"

     state=$(jq -r '.state' "${workingDir}/__transferState.json")
     echo "Current state: $state"
      if [ "$state" != "running" ] && [ "$state" != "completed" ]; then
        sleep 2
      fi
      retries=$((retries + 1))
      echo "Retries: $retries"

      #If maxRetries is reached, output an error message
      if [ $retries -eq $maxRetries ]; then
        echo "Error: Maximum retries reached. Project import for user: $username, project: $projectName, location: $projectLocation failed."
      fi

    done
}

convertProject() {
  local username=$1
  local projectName=$2
  local projectLocation=$3

  echo "Converting project for user: $username, project: $projectName, location: $projectLocation"
  ${importConverter} -source $projectLocation -target "./${workingDir}/${projectName}_${username}.zip"  \
  -user $username -renameTargetTableNames true
  echo "Converted project saved to: ${workingDir}/${projectName}_${username}.zip"

  echo "Importing converted project for user: $username, project: $projectName, location: ${workingDir}/${projectName}_${username}.zip"
  importProject "$username" "$password" "$projectName" "./${workingDir}/${projectName}_${username}.zip"
  echo "Converted project imported for user: $username, project: $projectName"
}

echo "Starting project import: `date`"

#Create the work directory if not there
mkdir -p $workingDir

# Get the admin token
getAdminToken

# Read "users" in the $configFile file and store it in an array
users=($(yq e '.validation-scenario.project-import.users[].username' "$configFile"))
passwords=($(yq e '.validation-scenario.project-import.users[].password' "$configFile"))

# Loop through the array of "users"
for i in "$!users[@]"; do
for i in "${!users[@]}"; do
  username=${users[$i]}
  password=${passwords[$i]}

  echo "Setting up project for use: $username"

  #Model Studo requires a user to have logged in at least once before they can import a project. We won't use the token.
  getUserToken "$username" "$password"

  convertProject "$username" "$projectName" "$projectLocation"

done
