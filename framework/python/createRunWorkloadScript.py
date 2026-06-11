# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
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
parser.add_argument("-t", "--template", type=str, help="Custom Resource template file", required=True)
parser.add_argument("-ht", "--headerTemplate", type=str, help="Custom Resource log header template file", required=True)
parser.add_argument("-a", "--artifactPath", type=str, help="Artifacts path", required=True)
parser.add_argument("-l", "--logLevel", type=str, help="Output build path", required=False, default="INFO")

# Parse the arguments
args = parser.parse_args()

logLevel=args.logLevel.upper()
logging.getLogger().setLevel(logLevel)
logging.info("Log Level set to: %s", logLevel)

logging.info(f"Creating script to run the workload")

# Read the environment variable
framework_resources_location = os.getenv("frameworkResourcesLocation")
hostname = os.getenv("hostname")
custom_resource_spec = os.getenv("customResourceSpec")
framework_defaults = os.getenv("frameworkDefaults")

logging.info(f"Artifacts Path: {args.artifactPath}")
logging.info(f"Template: {args.template}")
logging.info(f"Log Header Template: {args.headerTemplate}")

#Load the framework defaults as a dictionary
framework_defaults_dict = json.loads(framework_defaults)
workload_definition_defaults = framework_defaults_dict.get("workload-definition", {})

# Load the workload as a dictionary
custom_resource_spec_dict = json.loads(custom_resource_spec)
logging.debug(f"Custom Resource Spec: {custom_resource_spec_dict}")

# Read the workload definition variables
namespace = custom_resource_spec_dict.get("namespace")
config_map_name = custom_resource_spec_dict.get("config-map-name")
timeout = custom_resource_spec_dict.get("timeout")
workloads = custom_resource_spec_dict.get("workloads", [])

# Print the values of the variables for debugging purposes
logging.debug(f"Workload definition variables:")
logging.debug(f"namespace: {namespace}")
logging.debug(f"config_map_name: {config_map_name}")
logging.debug(f"workloads: {workloads}")
logging.debug("")

# Read the base template file
with open(args.template, 'r') as file:
  template_file = file.read()

# Read the log header template file
with open(args.headerTemplate, 'r') as file:
  logs_header_template_file = file.read()

run_workload_template = string.Template(template_file)
run_workload_log_header_template = string.Template(logs_header_template_file)

with open(os.path.join(args.artifactPath, "runWorkload.sh" ), "w") as file:

  file.write("#!/bin/bash\n")
  file.write(f"#Execute this script to run the workload\n\n")

  logs_base_location = args.artifactPath
  logs_dir = os.path.join(args.artifactPath, "execution-logs")
  logging.info(f"Logs directory: {logs_dir}")
  logging.debug(f"Logs base location: {logs_base_location}")

  file.write(f"\n##########  Logging ########## \n")

  results_dir = os.path.join(args.artifactPath, "results")
  run_workload_log_header_doc = run_workload_log_header_template.substitute(logs_dir=logs_dir, logs_base_dir=logs_base_location, results_dir=results_dir)
  file.write(run_workload_log_header_doc)
  file.write(f"\n\n")

  config_map_cmd = os.path.join(args.artifactPath, "deployTaskResourcesAsConfigMap.sh")
  file.write(f"##########  Deploy the config map ########## \n")
  file.write(f"{config_map_cmd} \n")

  for workload in workloads:
    workload_name = workload.get("name")
    workload_task = workload.get("task")
    workload_path = workload.get("path")
    workload_users = workload.get("users")
  
    logging.debug(f"Creating Custom Resource for Workload name: {workload_name}, task: {workload_task}")
    logging.debug(f"Workload path:  {workload_path}")
    logging.debug(f"Workload users: {workload_users}")

    ## TODO if you name it 1-csv the file gets saved as stats.csv_1-stats.csv 
    ## something like that. You need to look inside your mster pod shell to see how its is getting named. When you say --csv stats.csv it will name it as stats.csv_stats.csv

    k8s_cr = os.path.join(args.artifactPath,"k8s-cr-" + workload_name + ".yaml")
    stats_location = os.path.join(args.artifactPath, "results", f"$users-{workload_name}.csv")
    failures_location = os.path.join(args.artifactPath, "execution-logs", f"$users-{workload_name}-failures.csv")
    exceptions_location = os.path.join(args.artifactPath, "execution-logs", f"$users-{workload_name}-exceptions.csv")
    run_workload_doc = run_workload_template.substitute(namespace=namespace, k8s_cr=k8s_cr, stats_location=stats_location, failures_location=failures_location, exceptions_location=exceptions_location, name=workload_name, config_map_name=config_map_name, workload_task=workload_task, 
                                                        workload_path=workload_path, timeout=timeout, hostname=hostname, frameworkResourcesLocation=framework_resources_location, logs_dir=logs_dir)

    file.write(f"\n########## {workload_name} - Start #############\n")
    file.write(run_workload_doc)
    file.write(f"\n########## {workload_name} - End   #############\n")

  file.write(f"\n\n##########  Cleanup   #############\n")
  file.write(f" kubectl -n {namespace} delete configmap {config_map_name} ")
  file.close

  #Make the script executable
  os.chmod(os.path.join(args.artifactPath, "runWorkload.sh"), 0o755)
