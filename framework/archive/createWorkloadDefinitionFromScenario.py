# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import shutil
import yaml
import argparse
import os
import subprocess
import string
import time
from yaspin import yaspin
from string import Template
from frameworkLib import Framework

## This script is experimential, is not fully implemented and may be changed in future releases
class TestCase:
    def __init__(self, name, path, task):
        self.name = name
        self.path = path
        self.task = task

    def __repr__(self):
        return f"TestCase(name={self.name}, path={self.path}, task={self.task})"

def create_wrkld_def_yaml(workloads):

  workloads_dictionary = []
  for workload in workloads:

     # User the values from the override yaml if present
    # users = workload_overrides.get("users") if workload_overrides.get("users") is not None and isinstance(workload_overrides.get("users"), int) else workload_definition_users
    # spawn_rate = workload_overrides.get("spawn-rate") if workload_overrides.get("spawn-rate") else  workload_definition_spawn_rate 
    # iterations = workload_overrides.get("iterations") if workload_overrides.get("iterations") else workload_definition_iterations
    # worker_replicas = workload_overrides.get("worker-replicas") if workload_overrides.get("worker-replicas") else workload_definition_worker_replicas
    # csv = workload_overrides.get("csv") if workload_overrides.get("csv") else workload_definition_csv

    users = Framework.get_value_with_priority("users", workload_overrides, workload, workload_definition_defaults.get("workload-definition", {}))
    spawn_rate = Framework.get_value_with_priority("spawn-rate", workload_overrides, workload, workload_definition_defaults.get("workload-definition", {}))
    worker_replicas = Framework.get_value_with_priority("worker-replicas", workload_overrides, workload, workload_definition_defaults.get("workload-definition", {}))
    csv = Framework.get_value_with_priority("csv", workload_overrides, workload, workload_definition_defaults.get("workload-definition", {})) 
    iterations = Framework.get_value_with_priority("iterations", workload_overrides, workload, workload_definition_defaults.get("workload-definition", {}))
    run_time = Framework.get_value_with_priority("run-time", workload_overrides, workload, workload_definition_defaults.get("workload-definition", {}))


    workloads_data = {
      "name": workload.get("name"),
      "path": workload.get("path"),
      "task": workload.get("task"),
      "users": users,
      "spawn-rate": spawn_rate,
      "iterations": iterations,
      "runtime": run_time,
      "worker-replicas": worker_replicas,
      "csv": csv
    }

    workloads_dictionary.append(workloads_data)

  custom_modules_dictionary = []
  # for custom_module in custom_modules:

  custom_module_data = {
    "name": workload_definition_custom_modules_name,
    "path": workload_definition_custom_modules_path,
    "task": workload_definition_custom_modules_task,
  }

  custom_modules_dictionary.append(custom_module_data)  

  # Use the values from the override yaml if present
  namespace = workload_overrides.get("namespace") if workload_overrides.get("namespace") else workload_definition_namespace  

  data = {
    "workload-definitions": {
      "workload-definition-specs": [{
        "name": workload_definition_name,
        "description": workload_definition_description,
        "custom-resource-spec": {
          "namespace": namespace,
          "config-map-name": workload_definition_config_map_name,
          "k8s-operator": workload_definition_k8s_operator,
          "workloads": workloads_dictionary,
          "custom-modules": custom_modules_dictionary
        }
    }]
    }
  }
  
  return data

def create_workloads(test_cases):
  print(f"Found {len(test_cases)} Python test case files:")

  workloads = []
  for testCase in test_cases:
    print(f" - {testCase}")
  
    ## Read the template file
    with open(template_path + "/wrkld-def-2.yaml.template", 'r') as file:
      templateFile = file.read()

      workload_data = {
        "name":testCase.name,
        "path": testCase.path,
        "task": testCase.task,
        "users": workload_definition_users,
        "spawn-rate": workload_definition_spawn_rate,
        "iterations": workload_definition_iterations,
        "worker-replicas": workload_definition_worker_replicas,
        "csv": workload_definition_csv
      }

      workloads.append(workload_data)
  
  return workloads

def execGenerateWorkloads():

  # Define the path to the generate_workloads_script
  generate_workloads_script = os.path.join(script_base_path, "generateWorkloadExecution.sh")

  print(f"\n===========================================")
  print(f"Executing script to create workload definitions: {generate_workloads_script}")

  # Define the arguments to pass to the script
  global_config_arg = global_config_file
  workload_definitions_arg = os.path.join(script_base_path, build_full_path, f"{scenario_name}-wrkld-def.yaml")
  
  # Build the command to execute the script
  command = [
      generate_workloads_script,
      "-g", global_config_arg,
      "-w", workload_definitions_arg
  ]
  
  # Execute the script
  try:
    print(f"Executing: {command}")      
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    print(f"Output from generateWorkloadExecution.py:\n{result.stdout}")
  except subprocess.CalledProcessError as e:
    print(f"Error while running generateWorkloadExecution.py:\n{e.stderr}")

def execGenerateArtifacts():

  # Define the path to the generate_workloads_script
  exec_base_path = generated_base_path + "/workload-execution/" + scenario_name
  generate_workload_artifacts = os.path.join(exec_base_path, "runCreateWorkloadArtifacts.sh")

  print(f"Executing script to create workload artifacts: {generate_workload_artifacts}")

  # Build the command to execute the script
  command = [
      generate_workload_artifacts
  ]

  # Execute the script
  try:
    print(f"Executing: {command}\n")
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    print(f"Output from runCreateWorkloadArtifacts.sh:\n{result.stdout}")
  except subprocess.CalledProcessError as e:
    print(f"Error while running runCreateWorkloadArtifacts.sh:\n{e.stderr}")

def execDeployTaskResourcesAsConfigMap():
  # Define the path to the generate_workloads_script
  exec_base_path = generated_base_path + "/workload-execution/" + scenario_name + "/artifacts"
  exec_script = os.path.join(exec_base_path, "deployTaskResourcesAsConfigMap.sh")

  print(f"===========================================")
  print(f"Executing script to deploy config map: {exec_script}")

  # Build the command to execute the script
  command = [
      exec_script
  ]
  
  # Execute the script
  try:
      print(f"Executing: {command}")
      result = subprocess.run(command, capture_output=True, text=True, check=True)
      print(f"Output from runCreateWorkloadArtifacts.sh:\n{result.stdout}")
  except subprocess.CalledProcessError as e:
      print(f"ERROR: Error creating the config map. Note: This script . \n") 
      print(f"{e.stderr}")

def execRunWorkload():
  # Define the path to the run workload script
  exec_base_path = generated_base_path + "/workload-execution/" + scenario_name + "/artifacts"
  exec_script = os.path.join(exec_base_path, "runWorkload.sh")

  print(f"===========================================")
  print(f"Executing script to run the workload: {exec_script}\n")

  # Build the command to execute the script
  command = [
      exec_script
  ]
  
  # Execute the script
  try:
      
      spinner = yaspin()
      spinner.text = "Running workload..."
      spinner.color = "yellow"
      spinner.start()
      result = subprocess.run(command, capture_output=True, text=True, check=True)
      spinner.stop()
      print(f"Output from runWorkload.sh:\n{result.stdout}")

  except subprocess.CalledProcessError as e:
      print(f"Error while running runWorkload.sh:\n{e.stderr}")      


# Create an ArgumentParser object
parser = argparse.ArgumentParser(description="Argument parser")

# Add named arguments
parser.add_argument("-g", "--global_config", type=str, help="Global Configuration yaml", required=True)
parser.add_argument("-s", "--scenarios_full_path", type=str, help="Full Path to Scenarios", required=True)
parser.add_argument("-n", "--scenario_name", type=str, help="Full Path to Scenario", required=True)
parser.add_argument("-p", "--build_path", type=str, help="Output build path", required=True)
parser.add_argument("-o", "--workload_overrides", type=str, help="Workload overrides yaml", required=False)

# Parse the arguments
args = parser.parse_args()

global_config_file= args.global_config
scenarios_full_path = args.scenarios_full_path
scenario_name = args.scenario_name
workload_overrides_file = args.workload_overrides

script_base_path = os.getenv("scriptBasePath")
generated_base_path = os.getenv("generatedBaseDir")
build_full_path = os.path.abspath(args.build_path)
print(f"=== createWorkloadSCenario.py ====")
print(f"Script base path: {script_base_path}")
print(f"Build path: {build_full_path}")

print(f"Global config file: {global_config_file}")
print(f"Scenario full path: {scenarios_full_path}")
print(f"Scenario name: {scenario_name}")
print(f"Workload overrides file: {workload_overrides_file}")

print()
print(f"Creating a workload definition from scenario: ")
print()

# Load the global config yaml
with open(global_config_file, 'r') as file1:
  global_config_properties = yaml.safe_load(file1)
  global_config_properties = global_config_properties.get("global-config", {})

framework_path = global_config_properties.get("framework-base-location")
if framework_path:
  framework_path = os.path.abspath(framework_path)
else:
  print(f"Error: framework-path not found in the global config yaml file.")
  exit(1)

template_path = framework_path + "/python/templates"

#Load the framework defaults yaml
with open(os.path.join(framework_path, "framework-defaults.yaml"), 'r') as file1:
  framework_defaults = yaml.safe_load(file1)
  framework_defaults = framework_defaults.get("framework-defaults", {})
  workload_definition_defaults = framework_defaults.get("workload-definition", {})
  print(f"Framework defaults: {workload_definition_defaults}")

#Load the workload overrides yaml if present
if workload_overrides_file:
  with open(workload_overrides_file, 'r') as file3:
    workload_overrides = yaml.safe_load(file3)
    workload_overrides = workload_overrides.get("workload-overrides", {})
else:
  workload_overrides = {}  

workload_definition_custom_modules_name = workload_definition_defaults.get("custom-modules-name")
workload_definition_custom_modules_path = workload_definition_defaults.get("custom-modules-path")
workload_definition_custom_modules_task = workload_definition_defaults.get("custom-modules-task")

workload_definition_name = scenario_name
workload_definition_description = workload_definition_defaults.get("description")
workload_definition_namespace = workload_definition_defaults.get("namespace")
workload_definition_k8s_operator = workload_definition_defaults.get("k8s-operator")
workload_definition_csv = workload_definition_defaults.get("csv")
workload_definition_users = workload_definition_defaults.get("users")
workload_definition_spawn_rate = workload_definition_defaults.get("spawn-rate")
workload_definition_iterations = workload_definition_defaults.get("iterations")
workload_definition_worker_replicas = workload_definition_defaults.get("worker-replicas")

workload_definition_config_map_name = scenario_name + "-config-map"
  
# Get the list of test cases from the scenario  
# Search for files with a *.py extension in the scenario_full_path
test_cases = []
for root, dirs, files in os.walk(os.path.join(scenarios_full_path, scenario_name)):
  for file in files:
    if file.endswith(".py"):
      relative_path = os.path.relpath(root, scenarios_full_path)
      testCase = TestCase(
        name=os.path.splitext(os.path.basename(file))[0],
        path=relative_path,
        task=file
      )
      test_cases.append(testCase)
      print(f"Found test case: {testCase}")

workloads_data = create_workloads(test_cases)
wrkld_def = create_wrkld_def_yaml(workloads_data)

output_file_path = os.path.join(args.build_path, f"{scenario_name}-wrkld-def.yaml")
with open(output_file_path, 'w') as output_file:
  # You can now use workload_doc (e.g., save it to a file or print it)
  output_file.write(yaml.dump(wrkld_def, sort_keys=False, default_flow_style=False))  

print(f"Workload definition YAML file created successfully at: {output_file_path}")

execGenerateWorkloads()
execGenerateArtifacts()
execDeployTaskResourcesAsConfigMap()
execRunWorkload()

  

# total_workloads = len(workload_definitions.get("workload-definition-specs", []))
# print(f"\nWorkload definitions created successfully in {generated_workloads_execution_path}. Total workloads created: {total_workloads}.")
