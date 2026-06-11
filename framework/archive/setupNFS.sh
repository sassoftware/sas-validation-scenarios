#!/usr/bin/env bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


# Redirect stdout and stderr to a log file with a timestamp
if [ -z "$scenarioBaseDir" ]; then
  echo "Error: Environment variable scenarioBaseDir is not set."
  exit 1
fi

mkdir -p $scenarioBaseDir/logs
timestamp=`date +%Y%m%d%H%M%S`
exec 3>&1 4>&2
trap 'exec 2>&4 1>&3' 0 1 2 3
exec 1>$scenarioBaseDir/logs/setupNFS_${timestamp}.log 2>&1

startTime=$(date +%s)
echo -e "Starting configuration of the server... $(date +%H:%M:%S) \n"

echo "Creating directories on the NFS server..."

# Validate required environment variables

# Extract and validate required properties from the 'nfs' environment variable
server=$(echo "$nfs" | jq -r '.server')
user=$(echo "$nfs" | jq -r '.user')
rootFolder=$(echo "$nfs" | jq -r '."root-folder"')
folders=$(echo "$nfs" | jq -r '.folders')

# Check if any required property is missing
if [ -z "$server" ] || [ -z "$user" ] || [ -z "$rootFolder" ] || [ -z "$folders" ]; then
  echo "Error: Missing required properties in the 'nfs' environment variable."
  echo "Ensure 'server', 'user', 'root-folder', and 'folders' are properly set."
  exit 1
fi

# Verify additional required environment variables
echo "Verifying required environment variables are set..."
required_vars=("pemFile")
for var in "${required_vars[@]}"; do
  if [ -z "${!var}" ]; then
    echo "Error: Environment variable $var is not set."
    exit 1
  fi
done

echo "Key file path: $pemFile"
echo "Server: $server"
echo "User: $user"
echo "Root folder: $rootFolder"

# # Concatenate the entries in the folders array into a space-separated string
dirNames=($(echo "$folders" | jq -r '.[].name'))
dirNamesString=$(IFS=' ' ; echo "${dirNames[*]}")
echo "Creating directories: $dirNamesString"

# # Create directories on the NFS server
ssh -i $pemFile $user@$server "cd ${rootFolder}; mkdir -p ${dirNamesString}; chmod 777 ${dirNamesString}"
echo "Directories created successfully."
ssh -i $pemFile $user@$server "cd ${rootFolder}; ls -lat "

# # Read "data-files" in the $configFile file and store it in an array.
# # dataFileNames=($(yq e '.validation-scenario.nfs.data-files[].name' "$configFile"))
# # dataFileSourceFolders=($(yq e '.validation-scenario.nfs.data-files[].source-folder' "$configFile"))
# # dataFileDestFolders=($(yq e '.validation-scenario.nfs.data-files[].dest-folder' "$configFile"))


# # Loop through the array of "data-files" and copy each file to the NFS server
# for i in "${!dataFileNames[@]}"; do

#   dataFileName=${dataFileNames[$i]}\
#   dataFileSourceFolder=${dataFileSourceFolders[$i]}
#   dataFileDestFolder=${dataFileDestFolders[$i]}

#   echo "Copying ${dataFileSourceFolder}/${dataFileName} to folder: ${rootFolder}/${dataFileDestFolder}/${dataFileName} "
#   # scp -i ${pemFile} ${dataFileSourceFolder}/${dataFileName} ${user}@${server}:${rootFolder}/${dataFileDestFolder}/${dataFileName}
#   echo "Setting 777 permissions for ${rootFolder}/${dataFileDestFolder}/${dataFileName}"
#   # ssh -i ${pemFile} ${user}@${server} "chmod 777 ${rootFolder}/${dataFileDestFolder}/${dataFileName}"
#   echo "File ${dataFileName} copied successfully."

# done
