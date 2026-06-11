# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import shutil
import yaml
import argparse
import os
import json
import string
from string import Template
import logging

# Debug support
DEBUG_MODE = os.getenv('DEBUG_CREATEWORKLOADDEFINITIONS', 'false').lower() == 'true'
if DEBUG_MODE:
    import debugpy
    debugpy.listen(5678)
    print("Waiting for debugger to attach on port 5678...")
    debugpy.wait_for_client()
    print("Debugger attached!")

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
parser.add_argument("-g", "--global_config", type=str, help="Global Configuration yaml", required=True)
parser.add_argument("-w", "--workload_definitions", type=str, help="Workload definitions yaml", required=True)
parser.add_argument("-o", "--workload_overrides", type=str, help="Workload overrides yaml", required=False)
parser.add_argument("-l", "--log_level", type=str, help="Output build path", required=False, default="INFO")
parser.add_argument("-u", "--users_file", type=str, help="Users file", required=False, default="none")

# Parse the arguments
args = parser.parse_args()

log_level=args.log_level.upper()
logging.getLogger().setLevel(log_level)
logging.info("Log Level set to: %s", log_level)

global_config_file= args.global_config
workload_definitions_file = args.workload_definitions
workload_overrides_file = args.workload_overrides
users_file = args.users_file

logging.info(f"Creating workload definitions from workload definitions yaml file: {workload_definitions_file}")

logging.info(f"Global config file: {global_config_file}")
logging.info(f"Workload definitions file: {workload_definitions_file}")
logging.info(f"Workload overrides file: {workload_overrides_file}")

if users_file and users_file != "none":
  logging.info(f"Users file: {users_file}")
else:
  logging.warning(f"No users file specified. Assuming the users are loaded to k8s Secrets")

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

  scenarios_base_path = global_config_properties.get("scenarios-base-location")
  if scenarios_base_path:
    scenarios_base_path = os.path.abspath(scenarios_base_path)
  else:
    logging.error(f"scenarios_base_path not found in the global config yaml file.")
    exit(1)

  generated_path = global_config_properties.get("generated-base-location")
  if generated_path:
    generated_path = os.path.abspath(generated_path)
  else:
    logging.error(f"generated_path not found in the global config yaml file.")
    exit(1)  

logging.debug(f"Framework path: {framework_path}")
logging.debug(f"Scenarios base path: {scenarios_base_path}")
logging.debug(f"Generated path: {generated_path}")
generated_workloads_execution_path = generated_path + "/workload-execution"
generated_workloads_setup_path = generated_path + "/workload-setup"
logging.debug(f"Generated workloads execution path: {generated_workloads_execution_path}")
logging.debug(f"Generated workloads setup path: {generated_workloads_setup_path}")

#Load the framework defaults yaml
framework_defaults_full_path = os.getenv("frameworkDefaultsFullPath") 
with open(framework_defaults_full_path, 'r') as file4:
  framework_defaults = yaml.safe_load(file4)
  workload_definition_defaults = framework_defaults.get("framework-defaults", {})

#Load the workload definitions yaml
with open(workload_definitions_file, 'r') as file2: 
  workload_definitions = yaml.safe_load(file2)
  workload_definitions = workload_definitions.get("workload-definitions", {})

#Load the workload overrides yaml if present
if workload_overrides_file:
  with open(workload_overrides_file, 'r') as file3:
    workload_overrides = yaml.safe_load(file3)
    workload_overrides = workload_overrides.get("workload-overrides", {})
else:
  workload_overrides = {}

def get_value_with_priority(key, overrides, definition, defaults):
    """
    Helper function to determine the value of a key based on priority:
    1. Overrides
    2. Workload definition
    3. Framework defaults
    """
    logging.debug(f"Checking for {key} in workload overrides, workload definition, and framework defaults.")
    logging.debug(f"Overrides: {overrides.get(key)}")
    logging.debug(f"Definition: {definition.get(key)}")
    logging.debug(f"Defaults: {defaults.get(key)}")
    
    # Check the priority of the key
    if overrides.get(key) is not None:
        logging.debug(f"Using {key} from workload overrides: {overrides.get(key)}")
        return overrides.get(key)
    elif definition.get(key) is not None:
        logging.debug(f"Using {key} from workload definition: {definition.get(key)}")
        return definition.get(key)
    else:
        logging.debug(f"Using {key} from framework defaults: {defaults.get(key)}")
        return defaults.get(key)

def create_data_map_yaml(workload_definition_spec):


  custom_resource_spec = workload_definition_spec.get("custom-resource-spec", {}) 
  workloads = custom_resource_spec.get("workloads", {})
  custom_modules = custom_resource_spec.get("custom-modules", {})

  timout = get_value_with_priority("timeout", workload_overrides, custom_resource_spec, workload_definition_defaults.get("workload-definition", {}))

  scenario_config_full_path = None
  scenario_base_path = None
  dependencies = []
  workloads_dictionary = []
  for workload in workloads:

    # Use the values from the override or defaults yaml if present
    users = get_value_with_priority("users", workload_overrides, workload, workload_definition_defaults.get("workload-definition", {}))
    spawn_rate = get_value_with_priority("spawn-rate", workload_overrides, workload, workload_definition_defaults.get("workload-definition", {}))
    worker_replicas = get_value_with_priority("worker-replicas", workload_overrides, workload, workload_definition_defaults.get("workload-definition", {}))
    csv = get_value_with_priority("csv", workload_overrides, workload, workload_definition_defaults.get("workload-definition", {})) 
    iterations = get_value_with_priority("iterations", workload_overrides, workload, workload_definition_defaults.get("workload-definition", {}))
    run_time = get_value_with_priority("run-time", workload_overrides, workload, workload_definition_defaults.get("workload-definition", {}))

    if not workload.get("scenario-config"):
      logging.error(f"ERROR: Property scenario-config is required in the workload definition.")
      exit(1)

    scenario_config_full_path = os.path.join(scenarios_base_path, workload.get("scenario-config"))

    if not os.path.isfile(scenario_config_full_path):
      logging.error(f"ERROR: The scenario config file {scenario_config_full_path} does not exist.")
      exit(1)
      
    logging.debug(f"Scenario config full path: {scenario_config_full_path}")
    scenario_base_path = os.path.dirname(scenario_config_full_path)
    logging.debug(f"Scenario base path: {scenario_base_path}")

    workloads_data = {
      "name": workload.get("name"),
      "scenario-config": workload.get("scenario-config"),
      "path": workload.get("path"),
      "task": workload.get("task"),
      "csv": csv,
      "users": users,
      "spawn-rate": spawn_rate,
      "iterations": iterations,
      "run-time": run_time,
      "worker-replicas": worker_replicas
    }

    workloads_dictionary.append(workloads_data)

    # We need to open the scenario-config.yaml file to get the dependencies array from the workload definition
    scenario_config_file = os.path.join(scenarios_base_path, workload.get("scenario-config"))
    logging.debug(f"Opening scenario config file to get dependencies: {scenario_config_file}")

    with open(scenario_config_file, 'r') as file5: 
      scenario_config = yaml.safe_load(file5)
      scenario_config_properties = scenario_config.get("scenario-config", {})
      dependencies.extend(scenario_config_properties.get("dependencies", []))
      logging.debug(f"Dependencies found in the scenario config file {scenario_config_file}: {dependencies}")


  custom_modules_dictionary = []
  
  for dependency in dependencies:

    dependency_type = dependency.get("type")
    logging.debug(f"Dependency type: {dependency_type}")
    dependency_path = dependency.get("path")
    logging.debug(f"Dependency path: {dependency_path}")  
    dependency_file = dependency.get("file")
    logging.debug(f"Dependency file: {dependency_file}")

    # If the custom_module_path starts with "framework" remove it
    if dependency_path.startswith("framework"):
      dependency_path = dependency_path.replace("framework/", "")

    dependency_full_path = ''

    ##Check for the existence of the named dependency
    if dependency_type == "common":
      logging.debug(f"Checking for common library at: {os.path.join(framework_path, dependency_path, dependency_file)}")
      if os.path.isfile(os.path.join(framework_path, dependency_path, dependency_file)):
        logging.debug(f"Common library found at: {os.path.join(framework_path, dependency_path, dependency_file)}")
        dependency_full_path = os.path.join(framework_path, dependency_path, dependency_file)
      else:
        logging.error(f"ERROR: Common library not found at: {os.path.join(framework_path, dependency_path, dependency_file)}")
        exit(1)
    elif dependency_type == "resource":
      logging.debug(f"Checking for resource module at: {os.path.join(scenario_base_path, dependency_path, dependency_file)}")
      if os.path.isfile(os.path.join(scenario_base_path, dependency_path, dependency_file)):
        logging.debug(f"Resource module found at: {os.path.join(scenario_base_path, dependency_path, dependency_file)}")
        dependency_full_path = os.path.join(scenario_base_path, dependency_path, dependency_file)
      else:
        logging.error(f"ERROR: Resource module not found at: {os.path.join(scenario_base_path, dependency_path, dependency_file)}")
        exit(1)
    elif dependency_type == "cli-profile":    
      logging.debug(f"Checking for cli-profile module at: {os.path.join(framework_path, dependency_path, dependency_file)}")
      if os.path.isfile(os.path.join(framework_path, dependency_path, dependency_file)):
        logging.debug(f"cli-profile module found at: {os.path.join(framework_path, dependency_path, dependency_file)}")
        dependency_full_path = os.path.join(framework_path, dependency_path, dependency_file)
      else:
        logging.error(f"ERROR: cli-profile module not found at: {os.path.join(framework_path, dependency_path, dependency_file)}")
        exit(1)

    custom_module_data = {
      "type": dependency.get("type"),
      "file": dependency_full_path,
    }

    custom_modules_dictionary.append(custom_module_data)  

  # Use the values from the override yaml if present
  namespace = workload_overrides.get("namespace") if workload_overrides.get("namespace") else custom_resource_spec.get("namespace")  

  data = {
    "workload-definition": {
      "name": workload.get("name"),
      "description": workload.get("description"),
      "custom-resource-spec": {
        "namespace": namespace,
        "config-map-name": custom_resource_spec.get("config-map-name"),
        "k8s-operator": "locust-k8s-operator.yaml",
        "timeout": timout,
        "workloads": workloads_dictionary,
        "custom-modules": custom_modules_dictionary
      }
    }
  }

  return data

#Create a list to store the "createWorkloadArtifacts.sh" scripts
workload_artifacts_scripts = []

for workload_definition_spec in workload_definitions.get("workload-definition-specs", []):
  workload_name = workload_definition_spec.get("name")
  workload_description = workload_definition_spec.get("description")
  logging.info(f"Creating workload definition for workload: {workload_name}")

  output_file_path = os.path.join(generated_workloads_execution_path,workload_name, workload_name + ".yaml")
  temp_file_path = os.path.join(generated_workloads_setup_path,workload_name, "not-implemented-yet" + ".todo")

  # Create the directory if it doesn't exist
  try:
    os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
    logging.info(f"Successfully created directory for workload: {workload_name}")
  except Exception as e:
    logging.error(f"Error creating directory for workload {workload_name}: {e}")
    exit(1)

  # os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)
  # with open(temp_file_path, 'w') as todo_yaml:
  #   todo_yaml.write(f"Feature is not implemented yet.\n")

  with open(output_file_path, 'w') as generated_workload_yaml:
    data = create_data_map_yaml(workload_definition_spec)
    generated_workload_yaml.write(yaml.dump(data, sort_keys=False, default_flow_style=False))

  # Copy the createWorkloadArtifacts.sh script fromn framework library
  create_script = os.path.join(framework_path, "bash", "createWorkloadArtifacts.sh")
  if os.path.exists(create_script):
    shutil.copy(create_script, os.path.join(generated_workloads_execution_path, workload_name))
  else:
    logging.error(f"The script {create_script} does not exist.")
    exit(1)

  run_script_file = os.path.join(generated_workloads_execution_path,workload_name, "runCreateWorkloadArtifacts.sh")
  workload_artifacts_scripts.append(run_script_file)
  with open(run_script_file, 'w') as run_script:
    run_script.write("#!/usr/bin/env bash \n\n")
    run_script.write(f"## This script is generated by the framework and will execute the createWorkloadArtifacts.sh script.\n")
    run_script.write(f"##   The createWorkloadArtifacts.sh script is responsible for creating the workload artifacts\n")
    run_script.write(f"##   in the ./artifacts directory that will run the Playwright/Locust validation scenarios.\n\n")

    run_script.write(f"export logLevel={args.log_level} \n")  
    run_script.write(f"export frameworkScriptsLocationFullPath={framework_path} \n")
    run_script.write(f"export scenariosLocationFullPath={scenarios_base_path} \n\n")

    run_script.write(f"{os.path.join(generated_workloads_execution_path, workload_name, 'createWorkloadArtifacts.sh')} \\\n")
    run_script.write(f"  -w {os.path.join(generated_workloads_execution_path, workload_name, workload_name + '.yaml')} \\\n")
    run_script.write(f"  -g {global_config_file} \\\n")                    
    run_script.write(f"  -d {framework_defaults_full_path} \\\n")

    if users_file and users_file != "none":
      run_script.write(f"  -u {users_file} \\\n")
      
    run_script.write(f"  -l {log_level} \n")        

  # Add execute permissions to the run script
  os.chmod(run_script_file, 0o755)
  # Add execute permissions to the createWorkloadArtifacts.sh script
  os.chmod(create_script, 0o755)

# Generate the "run all" script that executes each "createWorkloadArtifacts.sh" using the list of scripts created above
run_all_script_file = os.path.join(generated_workloads_execution_path, "runAllCreateWorkloadArtifacts.sh")
with open(run_all_script_file, 'w') as run_all_script:
  run_all_script.write("#!/usr/bin/env bash \n\n")
  run_all_script.write(f"## This script is generated by the framework and will execute all the createWorkloadArtifacts.sh scripts.\n")
  run_all_script.write(f"##   The createWorkloadArtifacts.sh script is responsible for creating the workload artifacts\n")
  run_all_script.write(f"##   in the ./artifacts directory that will run the Playwright/Locust validation scenarios.\n\n")

  # run_all_script.write(f"export frameworkScriptsLocationFullPath={framework_path} \n")
  # run_all_script.write(f"export scenariosLocationFullPath={scenario_path} \n\n")
  for workload_artifacts_script in set(workload_artifacts_scripts):
    run_all_script.write(f"echo \"Executing {workload_artifacts_script}\"\n") 
    run_all_script.write(f"{workload_artifacts_script} \n")

  # Add execute permissions to the run all script
  os.chmod(run_all_script_file, 0o755)

total_workloads = len(workload_definitions.get("workload-definition-specs", []))
logging.info(f"Workload definitions created successfully in {generated_workloads_execution_path}. Total workloads created: {total_workloads}.")


