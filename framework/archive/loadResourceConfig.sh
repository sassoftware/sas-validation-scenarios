#!/usr/bin/env bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


## WIP. THIS SCRIPT IS NOT FULLY IMPLEMENTED.

CONFIG_FILE="./resource-config.yaml"

# Check if the -p parameter is passed into the script
while getopts ":p:" opt; do
  case $opt in
    p)
      resourceConfigFile=$OPTARG
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

# Ensure the resourceConfigFile variable is set
if [ -z "$resourceConfigFile" ]; then
  echo "Error: -p parameter is required. Please provide a valid configuration file." >&2
  exit 1
fi


resourceConfigFileFullPath=$(realpath $resourceConfigFile)
echo "Using config file: $resourceConfigFile"
echo "Full path to config file: $resourceConfigFileFullPath"
echo "Global log path: $global_log_path"


# Read the root properties
validation_scenario_description=$(yq e '.validation-scenario.description' $resourceConfigFile)
nfs_root_folder=$(yq e '.validation-scenario.nfs.root-folder' $resourceConfigFile)
cas_data_location=$(yq e '.validation-scenario.cas.data-location' $resourceConfigFile)
cas_source_data_table=$(yq e '.validation-scenario.cas.source-data-table' $resourceConfigFile)
model_studio_project_name=$(yq e '.validation-scenario.model-studio-project-import.project-name' $resourceConfigFile)
model_studio_project_zip_location=$(yq e '.validation-scenario.model-studio-project-import.project-zip-location' $resourceConfigFile)
model_studio_import_converter=$(yq e '.validation-scenario.model-studio-project-import.import-converter' $resourceConfigFile)
model_studio_validation_reset_script=$(yq e '.validation-scenario.model-studio-project-import.validation-reset-script' $resourceConfigFile)

# Read the NFS folders
nfs_folders=$(yq e '.validation-scenario.nfs.folders[].name' $resourceConfigFile)

# Read the CAS allowlist paths
cas_allowlist_paths=$(yq e '.validation-scenario.cas.allowlist-paths[].path' $resourceConfigFile)

# Read the CAS create-libs
cas_create_libs=$(yq e '.validation-scenario.cas.create-libs[].name' $resourceConfigFile)
cas_create_libs_servers=$(yq e '.validation-scenario.cas.create-libs[].server' $resourceConfigFile)
cas_create_libs_paths=$(yq e '.validation-scenario.cas.create-libs[].path' $resourceConfigFile)

# Export variables
export validation_scenario_description
export nfs_root_folder
export cas_data_location
export cas_source_data_table
export model_studio_project_name
export model_studio_project_zip_location
export model_studio_import_converter
export model_studio_validation_reset_script

# Export arrays
export nfs_folders
export cas_allowlist_paths
export cas_create_libs
export cas_create_libs_servers
export cas_create_libs_paths

# Print variables for verification
echo "validation_scenario_description=$validation_scenario_description"
echo "nfs_root_folder=$nfs_root_folder"
echo "cas_data_location=$cas_data_location"
echo "cas_source_data_table=$cas_source_data_table"
echo "model_studio_project_name=$model_studio_project_name"
echo "model_studio_project_zip_location=$model_studio_project_zip_location"
echo "model_studio_import_converter=$model_studio_import_converter"
echo "model_studio_validation_reset_script=$model_studio_validation_reset_script"

echo "nfs_folders=$nfs_folders"
echo "cas_allowlist_paths=$cas_allowlist_paths"
echo "cas_create_libs=$cas_create_libs"
echo "cas_create_libs_servers=$cas_create_libs_servers"
echo "cas_create_libs_paths=$cas_create_libs_paths"
