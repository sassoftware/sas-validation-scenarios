# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import yaml
import argparse
import os
import string
from string import Template

print()
print(f"Creating custom resources")
print()

# Create an ArgumentParser object
parser = argparse.ArgumentParser(description="Argument parser")

# Add named arguments
parser.add_argument("-t", "--template", type=str, help="Custom Resource template file", required=True)
parser.add_argument("-a", "--artifactPath", type=str, help="Artifacts path", required=True)

# Parse the arguments
args = parser.parse_args()

# Read the environment variable
frameworkResourcesLocation = os.getenv("frameworkScriptsLocationFullPath")
hostname = os.getenv("hostname")
custom_resource_spec = os.getenv("customResourceSpec")

print(f"Artifacts Path: {args.artifactPath}")

# Load the workload as a dictionary
custom_resource_spec_dict = json.loads(custom_resource_spec)

# Read the workload definitoin variables
users = custom_resource_spec_dict.get("users")
k8s_operator = custom_resource_spec_dict.get("k8s-operator")
namespace = custom_resource_spec_dict.get("namespace")
spawn_rate = custom_resource_spec_dict.get("spawn-rate")
iterations = custom_resource_spec_dict.get("iterations")
csv = custom_resource_spec_dict.get("csv")
# worker_replicas = custom_resource_spec_dict.get("worker-replicas")
config_map_name = custom_resource_spec_dict.get("config-map-name")
k8s_operator_name = custom_resource_spec_dict.get("k8s-operator")
# custom_resources = custom_resource_spec_dict.get("custom-resources-spec")
workloads = custom_resource_spec_dict.get("workloads")

# Print the values of the variables for debugging purposes
# print(f"Workload definition variables:")
# print(f"hostname: {hostname}")
# print(f"k8s_operator: {k8s_operator}")
# print(f"namespace: {namespace}")
# print(f"config_map: {config_map_name}")
# print(f"workloads: {workloads}")
# print()

# Read the template file
with open(args.template, 'r') as file:
  templateFile = file.read()

k8s_cr_template = string.Template(templateFile)

for workload in workloads:
  # print(f"Creating Custom Resource for Workload: {workload}")
  workload_name = workload.get("name")
  workload_task = workload.get("task")
  workload_users = workload.get("users")
  workload_spawn_rate = workload.get("spawn-rate")
  workload_iterations = workload.get("iterations")
  workload_csv = workload.get("csv")
  workload_run_time = workload.get("run-time")
  workload_worker_replicas = workload.get("worker-replicas")
  
  print(f"Creating Custom Resource for Workload name: {workload_name}, task: {workload_task}")

  k8s_cr_doc = k8s_cr_template.substitute(name=workload_name, task=workload_task, hostname=hostname, k8s_operator=k8s_operator_name, namespace=namespace, users=workload_users, spawn_rate=workload_spawn_rate, 
                                          iterations=workload_iterations, csv=workload_csv, worker_replicas=workload_worker_replicas, config_map_name=config_map_name, run_time=workload_run_time)
  print(f"file name is {args.artifactPath}/k8s-cr-{workload_name}.yaml")
  with open(os.path.join(args.artifactPath, "k8s-cr-" + workload_name + ".yaml"), "w") as file:
    file.write(k8s_cr_doc)
