#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


# Redirect stdout and stderr to a log file with a timestamp
mkdir -p logs
timestamp=`date +%Y%m%d%H%M%S`
exec 3>&1 4>&2
trap 'exec 2>&4 1>&3' 0 1 2 3
exec 1>$global_log_path/setupCAS_${timestamp}.log 2>&1

startTime=$(date +%s)
echo -e "Starting configuration of the server... $(date +%H:%M:%S) \n"

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

echo "Configuring the CAS server..."

#Add the root folder to the CAS allowlist
allowlistPaths=($(yq e '.validation-scenario.cas.allowlist-paths[].path' "$configFile"))
for i in "${!allowlistPaths[@]}"; do
  allowlistPath=${allowlistPaths[$i]}
  
  echo "Adding path ${allowlistPath} to the CAS allowlist"
  sas-viya --profile ${cliProfile} -k cas servers paths-list add-paths --server ${casServer} --path ${allowlistPath}

done

#Read the "create-libs" parameters in the $configFile file and store each in arrays
casLibNames=($(yq e '.validation-scenario.cas.create-libs[].name' "$configFile"))
casLibServers=($(yq e '.validation-scenario.cas.create-libs[].server' "$configFile"))
casLibPaths=($(yq e '.validation-scenario.cas.create-libs[].path' "$configFile"))
casLibNfsPaths=($(yq e '.validation-scenario.cas.create-libs[].nfs-path' "$configFile"))

#Read the sas-viya profile from the $configFile file
cliProfile=$(yq e '.validation-scenario.viya-cli-profile' "$configFile")

# Loop through the array of "create-libs" and create CASLibs on the CAS server
echo "Creating CASLibs on the CAS server"

for i in "${!casLibNames[@]}"; do

  casLibName=${casLibNames[$i]}
  casLibServer=${casLibServers[$i]}
  casLibPath=${casLibPaths[$i]}
  casLibNfsPath=${casLibNfsPaths[$i]}

    echo "Creating CASLib ${casLibName} for in path: ${casLibPath}"
    sas-viya --profile ${cliProfile} -k cas caslibs create path --server ${casLibServer} --name ${casLibName} --path ${casLibPath}

    echo "Setting permissions for CASLib: ${casLibName}"
    sas-viya --profile ${cliProfile} -k cas caslibs add-control --server ${casLibServer} --caslib ${casLibName} --group '*' --grant ReadInfo
    sas-viya --profile ${cliProfile} -k cas caslibs add-control --server ${casLibServer} --caslib ${casLibName} --group '*' --grant Select
    sas-viya --profile ${cliProfile} -k cas caslibs add-control --server ${casLibServer} --caslib ${casLibName} --group '*' --grant LimitedPromote
    sas-viya --profile ${cliProfile} -k cas caslibs add-control --server ${casLibServer} --caslib ${casLibName} --group '*' --grant Promote
    sas-viya --profile ${cliProfile} -k cas caslibs add-control --server ${casLibServer} --caslib ${casLibName} --group '*' --grant CreateTable
    sas-viya --profile ${cliProfile} -k cas caslibs add-control --server ${casLibServer} --caslib ${casLibName} --group '*' --grant DropTable
    sas-viya --profile ${cliProfile} -k cas caslibs add-control --server ${casLibServer} --caslib ${casLibName} --group '*' --grant DeleteSource
    sas-viya --profile ${cliProfile} -k cas caslibs add-control --server ${casLibServer} --caslib ${casLibName} --group '*' --grant Insert
    sas-viya --profile ${cliProfile} -k cas caslibs add-control --server ${casLibServer} --caslib ${casLibName} --group '*' --grant Update
    sas-viya --profile ${cliProfile} -k cas caslibs add-control --server ${casLibServer} --caslib ${casLibName} --group '*' --grant Delete
    sas-viya --profile ${cliProfile} -k cas caslibs add-control --server ${casLibServer} --caslib ${casLibName} --group '*' --grant AlterTable
    sas-viya --profile ${cliProfile} -k cas caslibs add-control --server ${casLibServer} --caslib ${casLibName} --group '*' --grant AlterCaslib
    sas-viya --profile ${cliProfile} -k cas caslibs add-control --server ${casLibServer} --caslib ${casLibName} --group '*' --grant ManageAccess
  
  echo "CASLib ${casLibName} created successfully."

done
