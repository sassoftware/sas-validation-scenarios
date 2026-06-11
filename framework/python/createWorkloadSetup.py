# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import shutil
import yaml
import argparse
import os
from string import Template
import logging

# Debug support
DEBUG_MODE = os.getenv('DEBUG_CREATEWORKLOADSETUP', 'false').lower() == 'true'
if DEBUG_MODE:
    import debugpy
    debugpy.listen(5678)
    print("Waiting for debugger to attach on port 5678...")
    debugpy.wait_for_client()
    print("Debugger attached!")

# Configure logging
# logging.basicConfig(level=logging.INFO)
logging.basicConfig(
  format="%(asctime)s - %(levelname)-5s - %(name)s:%(lineno)-3d - %(message)s ",
  datefmt="%Y-%m-%d %H:%M",
  level=logging.INFO
)
logging.getLogger().name = os.path.basename(__file__)

# Create an ArgumentParser object
parser = argparse.ArgumentParser(description="Argument parser")

# Add named arguments
parser.add_argument("-g", "--global_config", type=str, help="Global Configuration yaml", required=True)
parser.add_argument("-w", "--workload_definitions", type=str, help="Workload definitions yaml", required=True)
# parser.add_argument("-s", "--scenario_config", type=str, help="Scenario Config yaml", required=True)
parser.add_argument("-u", "--users_file", type=str, help="Users file", required=False)
parser.add_argument("-l", "--log_level", type=str, help="Output build path", required=False, default="INFO")

# Parse the arguments
args = parser.parse_args()

log_level=args.log_level.upper()
logging.getLogger().setLevel(log_level)
logging.debug("Log Level set to: %s", log_level)

global_config_file= args.global_config
workload_definitions_file = args.workload_definitions
# scenario_config_file = args.scenario_config
users_file = args.users_file
logging.info(f"Global config file: {global_config_file}")
# logging.info(f"Scenario config file: {scenario_config_file}")

# If users file is not provided, set it to an empty string
if not users_file:
    users_file = ""
    logging.info("No users file provided.")
else:
    logging.info(f"Users file: {users_file}")

logging.info(f"Creating workload setup scripts from workload definitions yaml file: {workload_definitions_file}")

logging.info(f"Global config file: {global_config_file}")
logging.info(f"Workload definitions file: {workload_definitions_file}")

# Load the global config yaml
with open(global_config_file, 'r') as file1:
  global_config_properties = yaml.safe_load(file1)
  global_config_properties = global_config_properties.get("global-config", {})

  framework_path = global_config_properties.get("framework-base-location")
  if framework_path:
    framework_path = os.path.abspath(framework_path)
  else:
    logging.error(f"framework-path not found in the global config yaml file.")
    exit(1)

  scenario_path = global_config_properties.get("scenarios-base-location")
  if scenario_path:
    scenario_path = os.path.abspath(scenario_path)
  else:
    logging.error(f"scenario_path not found in the global config yaml file.")
    exit(1)

  generated_path = global_config_properties.get("generated-base-location")
  if generated_path:
    generated_path = os.path.abspath(generated_path)
  else:
    logging.error(f"generated_path not found in the global config yaml file.")
    exit(1)  

logging.debug(f"Framework path: {framework_path}")
logging.debug(f"Scenario path: {scenario_path}")
logging.debug(f"Generated path: {generated_path}")
generated_workloads_setup_path = generated_path + "/workload-setup"
logging.debug(f"Generated workloads setup path: {generated_workloads_setup_path}")

#Load the scenario config yaml
# with open(scenario_config_file, 'r') as file2: 
#   scenario_config = yaml.safe_load(file2)
#   scenario_config_properties = scenario_config.get("scenario-config", {})

#   scenario_name = scenario_config_properties.get("name")
#   if scenario_name:
#     logging.info(f"Scenario name: {scenario_name}")
#   else:
#     logging.error(f"Name not found in the scenario config yaml file.")
#     exit(1)

#Load the workload definitions yaml
with open(workload_definitions_file, 'r') as file2: 
  workload_definitions = yaml.safe_load(file2)
  workload_definitions = workload_definitions.get("workload-definitions", {})


generated_workloads_setup_full_path = os.path.join(generated_workloads_setup_path)
logging.debug(f"Generated workloads setup full path: {generated_workloads_setup_full_path}")

#Create the workload setup directory if it does not exist
if not os.path.exists(generated_workloads_setup_full_path):
  os.makedirs(generated_workloads_setup_full_path)
  logging.debug(f"Created directory: {generated_workloads_setup_full_path}")
else:
  logging.debug(f"Directory already exists: {generated_workloads_setup_full_path}")

#Create a map of workload path and scenario config path
workload_artifact_paths = {}

for workload_definition_spec in workload_definitions.get("workload-definition-specs", []):
  workload_description = workload_definition_spec.get("description")

  ## Iterate through each workload and create the workload setup scripts
  custom_resource_spec = workload_definition_spec.get("custom-resource-spec", {})
  for workload in custom_resource_spec.get("workloads", []):

    workload_name = workload.get("name")
    
    scenario_config = workload.get("scenario-config", {})
    # Read scenario base location from the OS environment variable $scenariosLocationFullPath
    scenario_base_location = os.getenv("scenariosLocationFullPath", None)
    scenario_config_path = os.path.join(scenario_base_location, scenario_config)
    logging.debug(f"Scenario config path for workload {workload_name}: {scenario_config_path}")

    with open(scenario_config_path, 'r') as file1:
      scenario_config_properties = yaml.safe_load(file1)
      scenario_config_properties = scenario_config_properties.get("scenario-config", {})

    resources_setup = scenario_config_properties.get("resources-setup", {})

    ## If resources setup is empty, skip the workload
    if not resources_setup:
      logging.info(f"No resources setup defined for workload: {workload_name}. Skipping...")
      continue

    workload_name = workload.get("name")
    logging.info(f"Creating workload setup for workload: {workload_name}")

    output_file_path = os.path.join(generated_workloads_setup_full_path, workload_name)
    logging.debug(f"Output file path for workload {workload_name}: {output_file_path}")
    # Create the directory if it doesn't exist
    try:
      os.makedirs(output_file_path, exist_ok=True)
      logging.debug(f"Successfully created directory: {output_file_path}")
    except Exception as e:
      logging.error(f"Error creating directory for workload {workload_name}: {e}")
      exit(1)

    # Copy the createSetupArtifacts.sh script fromn framework library
    create_script = os.path.join(framework_path, "bash", "createSetupArtifacts.sh")
    logging.debug(f"Does the path {create_script} exist? {os.path.exists(create_script)}")
    if os.path.exists(create_script):
      logging.debug(f"Copying createSetupArtifacts.sh script from {create_script} to {output_file_path}")
      shutil.copy(create_script, os.path.join(output_file_path, "createSetupArtifacts.sh"))
    else:
      logging.error(f"The script {create_script} does not exist.")
      exit(1)

    # Copy the scenrio config file to the workload setup directory
    
    shutil.copy(os.path.join(scenario_base_location, scenario_config), os.path.join(output_file_path, "scenario_config.yaml")) 
    workload_artifact_paths[output_file_path] = os.path.join(output_file_path, "scenario_config.yaml")

run_script_file = os.path.join(generated_workloads_setup_full_path, "runCreateSetupArtifacts.sh")
with open(run_script_file, 'w') as run_script:
  
  run_script.write("#!/usr/bin/env bash \n\n")
  run_script.write(f"## This script is generated by the framework and will execute the createSetupArtifacts.sh script.\n")
  run_script.write(f"##   The createSetupArtifacts.sh script is responsible for creating the resource setup scripts\n")
  run_script.write(f"##   in the ./artifacts directory that will complete the prereqs for a validation scenario.\n\n")

  run_script.write(f"export logLevel={args.log_level} \n\n")  
  run_script.write(f"export frameworkScriptsLocationFullPath={framework_path} \n")
  run_script.write(f"export scenariosLocationFullPath={scenario_path} \n\n")

  # Generate the "run" script that executes each "createSetupArtifacts.sh"
  for workload_artifact_path, scenario_cfg_path in workload_artifact_paths.items():
    logging.debug(f"Adding execution command for workload artifact path: {workload_artifact_path}")
    run_script.write(f"{os.path.join(workload_artifact_path, 'createSetupArtifacts.sh')} \\\n")
    run_script.write(f"  -g {global_config_file} \\\n")
    run_script.write(f"  -s {scenario_cfg_path} \\\n")
    run_script.write(f"  -b {workload_artifact_path} \\\n")
    if users_file:
      run_script.write(f"  -u {users_file} \\\n")
    run_script.write(f"  -l {args.log_level}")
    run_script.write(f"\n\n")
  
    # Add execute permissions to the run script
  os.chmod(run_script_file, 0o755)


logging.debug(f"Workload setup scripts created successfully in {generated_workloads_setup_path}.")
#logging.info(f"To create the setup artifacts for this scenario run: {run_script_file} ")

# Run the generated script
logging.debug(f"Run the generated script: {run_script_file}")
os.system(f"bash {run_script_file}")
