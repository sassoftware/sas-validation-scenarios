# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import shutil
import yaml
import argparse
import os
import string
from string import Template
import logging

# Configure logging
logging.basicConfig(
  format="%(asctime)s - %(levelname)-5s - %(name)s:%(lineno)-3d - %(message)s ",
  datefmt="%Y-%m-%d %H:%M",
  level=logging.INFO
  )
logging.getLogger().name = os.path.basename(__file__)


# Create an ArgumentParser object
parser = argparse.ArgumentParser(description="Argument parser")

# Add named arguments
parser.add_argument("-a", "--artifactPath", type=str, help="Artifacts path", required=True)
parser.add_argument("-l", "--log_level", type=str, help="Output build path", required=False, default="INFO")

# Parse the arguments
args = parser.parse_args()

log_level=args.log_level.upper()
logging.getLogger().setLevel(log_level)
logging.info("Log Level set to: %s", log_level)

logging.info(f"Creating config map command ")

# Read the environment variable
framework_resources_location = os.getenv("frameworkScriptsLocationFullPath")
scenarios_base_location = os.getenv("scenariosLocationFullPath")
hostname = os.getenv("hostname")
custom_resource_spec = os.getenv("customResourceSpec")
global_config_full_path = os.getenv("globalConfigFullPath")
users_file_full_path = os.getenv("usersFileFullPath")
certs_file_full_path = os.getenv("trustedCerts")

logging.info(f"Artifacts Path: {args.artifactPath}")
logging.info(f"Scenarios Base Location: {scenarios_base_location}")
logging.info(f"Framework Resources Location: {framework_resources_location}")
logging.info(f"Hostname: {hostname}")
logging.info(f"Trusted Certs File: {certs_file_full_path}")

# Load the workload as a dictionary
custom_resource_spec_dict = json.loads(custom_resource_spec)
logging.info(f"Custom Resource Spec: {custom_resource_spec_dict}")

# Read the workload definitoin variables
namespace = custom_resource_spec_dict.get("namespace")
config_map_name = custom_resource_spec_dict.get("config-map-name")
common_library = custom_resource_spec_dict.get("common-library", [])
workloads = custom_resource_spec_dict.get("workloads", [])
custom_modules = custom_resource_spec_dict.get("custom-modules", [])

# Print the values of the variables for debugging purposes
logging.info(f"Workload definition variables:")
logging.info(f"namespace: {namespace}")
logging.info(f"config-map-name: {config_map_name}")
logging.info(f"workloads: {workloads}")
logging.info(f"custom_module: {custom_modules}")

path_to_task_resources = os.path.join(os.path.dirname(global_config_full_path), "scenarios")
logging.info(f"Path to task resources: {path_to_task_resources}")

common_lib = "python/common.py"
logging.info(f"Common library: {common_lib}")

with open(os.path.join(args.artifactPath, "deployTaskResourcesAsConfigMap.sh"), "w") as file:

  file.write("#!/bin/bash\n")
  file.write(f"#Execute this script to load the task resources as a Kubernetes Config Map\n\n")
  file.write(f"kubectl -n {namespace} create configmap {config_map_name} \\\n")

  # If the users file is provided, add it to the config map
  if users_file_full_path and users_file_full_path.lower() != "none":
    # Rename the users_file_full_path filename to users.yaml
    logging.debug(f"Users file provided: {users_file_full_path}")
    users_file_renamed = os.path.join(args.artifactPath, "users.csv")
    logging.info(f"Renamed users file: {users_file_renamed}")
    if os.path.isfile(users_file_renamed):
      file.write(f"  --from-file={users_file_renamed} \\\n")
    else:
      logging.error(f"ERROR: Users file not found: {users_file_renamed}")
      exit(1)
  else:
    logging.info(f"No users file provided")

  
  for workload in workloads:

    workload_name = workload.get("name")
    workload_task = workload.get("task")
    workload_path = workload.get("path")
    logging.debug(f"Workload name: {workload_name}")
    logging.debug(f"Workload task: {workload_task}")
    logging.debug(f"Workload path: {workload_path}")

    file.write(f"  --from-file={os.path.join(scenarios_base_location, workload_path, workload_task)} \\\n")

  # Define an array to hold the file paths of the custom modules
  custom_module_file_paths = set()

  for custom_module in custom_modules:

    custom_module_type = custom_module.get("type")
    custom_module_file = custom_module.get("file")
    logging.info(f"Custom module type: {custom_module_type}")
    logging.info(f"Custom module file: {custom_module_file}")

    #If the custom module is a cli-profile, fill the template
    if custom_module_type == "cli-profile":
      logging.info(f"Filling the cli-profile template: {custom_module_file}")

      with open(custom_module_file, "r") as cli_profile_template_file:
        templateFile = cli_profile_template_file.read()
        cli_profile_template = string.Template(templateFile)

        #Ensure there is not a trailing slash on the hostname
        if hostname.endswith("/"):
          hostname = hostname[:-1]

        cli_profile_filled = cli_profile_template.substitute(hostname=hostname)
        
        cli_profile = os.path.join(args.artifactPath, "config.json")
        logging.debug(f"Writing filled cli-profile to: {cli_profile}")

        #File name is the custom_module_file without the "template" suffix
        cli_profile_filename = os.path.basename(custom_module_file).replace(".template", "")
        cli_profile_full_path = os.path.join(args.artifactPath, cli_profile_filename)
        with open(cli_profile_full_path, "w") as cli_profile_filled_file:
          cli_profile_filled_file.write(cli_profile_filled)
          #Update the custom_module_file to point to the filled file
          # custom_module["file"] = cli_profile_full_path
          #Add the filled cli-profile path to the array
          custom_module_file_paths.add(cli_profile_full_path)

    elif custom_module_type == "trusted-certs":
      #If the custom module is a trusted-certs, use the trusted-certs path from the global config
      logging.info(f"Processing the trusted-certs file from the global config: {certs_file_full_path}")
      if os.path.isfile(certs_file_full_path):
        logging.debug(f"PEM file found: {certs_file_full_path}")
        #Copy the pem file to the artifact path
        shutil.copy(certs_file_full_path, os.path.join(args.artifactPath, "trustedcerts.pem"))
        # custom_module["file"] = certs_file_full_path
        # custom_module_file = certs_file_full_path
        #Add the filled cli-profile path to the array
        custom_module_file_paths.add(certs_file_full_path)
      else:
        logging.error(f"ERROR: PEM file not found: {certs_file_full_path}")
        exit(1)
    else:
      #For other custom module types, just add the file path to the array
      custom_module_file_paths.add(custom_module_file)    

    # #Ensure the custom module file exists
    # if not os.path.isfile(custom_module_file):
    #   logging.error(f"ERROR: Custom module file {custom_module_file} does not exist.")
    #   exit(1)      
    # logging.debug(f"Custom module file found: {custom_module_file}")
      
    # if custom_module is custom_modules[-1]:
    #   file.write(f"  --from-file={custom_module.get("file")} \n")
    # else:
    #   file.write(f"  --from-file={custom_module.get("file")} \\\n")

  logging.info(f"Custom module file paths (duplicates removed): {custom_module_file_paths}")  
  
  # Convert set to list for indexed iteration
  custom_module_file_paths_list = list(custom_module_file_paths)
  
  for i, custom_module_file_path in enumerate(custom_module_file_paths_list):
    if not os.path.isfile(custom_module_file_path):
      logging.error(f"ERROR: Custom module file {custom_module_file_path} does not exist.")
      exit(1)
    logging.debug(f"Custom module file found: {custom_module_file_path}")

    if i == len(custom_module_file_paths_list) - 1:
      file.write(f"  --from-file={custom_module_file_path} \n")  # No backslash for last item
    else:
      file.write(f"  --from-file={custom_module_file_path} \\\n")  # With backslash

  file.close

  #Make the script executable
  logging.info(f"Making the script executable.")
  os.chmod(os.path.join(args.artifactPath, "deployTaskResourcesAsConfigMap.sh"), 0o755)
