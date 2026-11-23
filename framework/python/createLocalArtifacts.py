# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Create the artifacts that run a workload with Locust on this machine instead of Kubernetes.

The task files and their dependencies are staged flat in <workload>/local/src, the same layout the
config map gives the Locust pods in /lotest/src, and runWorkloadLocal.sh runs Locust from there.
"""

import argparse
import json
import logging
import os
import shlex
import shutil
import string
import sys

logging.basicConfig(
  format="%(asctime)s - %(levelname)-5s - %(name)s:%(lineno)-3d - %(message)s ",
  datefmt="%Y-%m-%d %H:%M",
  level=logging.INFO
  )
logging.getLogger().name = os.path.basename(__file__)

RUN_SCRIPT_NAME = "runWorkloadLocal.sh"
USERS_FILE_NAME = "users.csv"
HEADED_USERS_WARNING_THRESHOLD = 3


def fail(message):
  logging.error(f"ERROR: {message}")
  sys.exit(1)


def load_json_env(name, default=None):
  value = os.getenv(name)
  if value is None or value.strip() in ("", "null"):
    return default
  try:
    return json.loads(value)
  except json.JSONDecodeError as error:
    fail(f"Environment variable {name} is not valid JSON: {error}")


def is_set(value):
  return bool(value) and str(value).lower() not in ("none", "null")


def positive_int(value, field, workload_name):
  try:
    number = int(value)
  except (TypeError, ValueError):
    fail(f"Workload {workload_name}: '{field}' must be a whole number, got {value!r}")
  if number < 1:
    fail(f"Workload {workload_name}: '{field}' must be at least 1, got {number}")
  return number


def stage_sources(src_dir, resources_dir, scenarios_base, spec, hostname, trusted_certs):
  """Copy every file the config map would hold into src_dir; returns {file name: source}."""
  if os.path.isdir(src_dir):
    shutil.rmtree(src_dir)
  os.makedirs(src_dir)

  staged = {}

  def stage(source, name=None, content=None):
    name = name or os.path.basename(source)
    previous = staged.get(name)
    if previous is not None:
      if os.path.realpath(previous) == os.path.realpath(source):
        return
      fail(f"{source} and {previous} have the same file name {name}; file names must be unique in local/src.")
    destination = os.path.join(src_dir, name)
    if content is not None:
      with open(destination, "w", encoding="utf-8") as handle:
        handle.write(content)
    else:
      if not os.path.isfile(source):
        fail(f"File does not exist: {source}")
      shutil.copy2(source, destination)
    staged[name] = source
    logging.debug(f"Staged {source} as {destination}")

  users_file = os.path.join(resources_dir, USERS_FILE_NAME)
  if not os.path.isfile(users_file):
    fail("A users file is required to run locally. Pass --users-file or set 'sas-validation.execution.users-file'.")
  stage(users_file, USERS_FILE_NAME)

  for workload in spec.get("workloads", []):
    stage(os.path.join(scenarios_base, workload.get("path"), workload.get("task")))

  for module in spec.get("custom-modules", []):
    module_type = module.get("type")
    module_file = module.get("file")
    if module_type in ("config-json", "cli-profile"):
      if not is_set(hostname):
        fail("A scenario declares a config-json dependency, but no hostname is configured. "
             "Set 'sas-validation.execution.hostname' in sas-validation.yaml.")
      with open(module_file, "r", encoding="utf-8") as handle:
        content = string.Template(handle.read()).safe_substitute(hostname=hostname.rstrip("/"))
      stage(module_file, "config.json", content=content)
    elif module_type == "trusted-certs":
      if not is_set(trusted_certs):
        fail("A scenario declares a trusted-certs dependency, but no trusted certificates file is configured. "
             "Set 'sas-validation.execution.trusted-certs' in sas-validation.yaml.")
      stage(trusted_certs, "trustedcerts.pem")
    else:
      stage(module_file)

  return staged


def workload_settings(workload, processes_override):
  name = workload.get("name")
  users = positive_int(workload.get("users"), "users", name)
  processes = positive_int(processes_override, "processes", name) if processes_override is not None else users
  return {
    "name": name,
    "task": workload.get("task"),
    "users": users,
    "spawn_rate": workload.get("spawn-rate"),
    "iterations": workload.get("iterations"),
    "run_time": workload.get("run-time"),
    "processes": processes,
  }


def main():
  parser = argparse.ArgumentParser(description="Create the local (non-Kubernetes) workload artifacts")
  parser.add_argument("-t", "--template", required=True, help="Per-workload run script template")
  parser.add_argument("-ht", "--headerTemplate", required=True, help="Run script header template")
  parser.add_argument("-r", "--resourcesPath", required=True, help="Resources path (holds users.csv)")
  parser.add_argument("-o", "--outputPath", required=True, help="Workload directory for local/, runWorkloadLocal.sh, execution-logs and results")
  parser.add_argument("-l", "--logLevel", default="INFO", help="Log level")
  args = parser.parse_args()

  logging.getLogger().setLevel(args.logLevel.upper())
  logging.info("Creating the local workload artifacts")

  scenarios_base = os.getenv("scenariosLocationFullPath")
  hostname = os.getenv("hostname")
  trusted_certs = os.getenv("trustedCerts")
  spec = load_json_env("customResourceSpec", {})
  local_execution = load_json_env("localExecution", {}) or {}
  headed = bool(local_execution.get("headed", False))
  processes_override = local_execution.get("processes")

  if not is_set(hostname):
    fail("No hostname is configured. Set 'sas-validation.execution.hostname' in sas-validation.yaml.")
  if not scenarios_base:
    fail("scenariosLocationFullPath is not set.")

  output_path = os.path.abspath(args.outputPath)
  src_dir = os.path.join(output_path, "local", "src")
  logs_dir = os.path.join(output_path, "execution-logs")
  results_dir = os.path.join(output_path, "results")
  supervisor = os.path.join(output_path, "local", "process-supervisor.py")

  staged = stage_sources(src_dir, args.resourcesPath, scenarios_base, spec, hostname, trusted_certs)
  shutil.copyfile(
    os.path.join(os.path.dirname(__file__), "scenario_package", "local_processes.py"),
    supervisor,
  )
  logging.info(f"Staged {len(staged)} file(s) in {src_dir}")

  with open(args.headerTemplate, "r", encoding="utf-8") as handle:
    header_template = string.Template(handle.read())
  with open(args.template, "r", encoding="utf-8") as handle:
    workload_template = string.Template(handle.read())

  timeout = spec.get("timeout") or "1h"
  workloads = [workload_settings(workload, processes_override) for workload in spec.get("workloads", [])]
  script_path = os.path.join(output_path, RUN_SCRIPT_NAME)
  quote = shlex.quote

  with open(script_path, "w", encoding="utf-8") as script:
    script.write("#!/bin/bash\n")
    script.write("# Execute this script to run the workload with Locust on this machine (no Kubernetes).\n")
    script.write("# Set SAS_VALIDATION_HEADLESS=false to watch the browser, or true to hide it.\n\n")
    script.write(header_template.substitute(
      logs_dir=quote(logs_dir),
      logs_base_dir=quote(output_path),
      results_dir=quote(results_dir),
      src_dir=quote(src_dir),
      users_file=quote(os.path.join(src_dir, USERS_FILE_NAME)),
      headless_default="false" if headed else "true",
      python=quote(sys.executable),
      supervisor=quote(supervisor),
    ))
    script.write("\n\n")
    script.write(f"ALL_WORKLOADS=({' '.join(quote(str(w['name'])) for w in workloads)})\n")
    script.write("run_precheck\n")

    for workload in workloads:
      if headed and workload["users"] > HEADED_USERS_WARNING_THRESHOLD:
        logging.warning(
          f"Workload {workload['name']} opens {workload['users']} browser windows in headed mode; "
          f"use headless mode for more than {HEADED_USERS_WARNING_THRESHOLD} users."
        )
      name = workload["name"]
      script.write(f"\n########## {name} - Start #############\n")
      script.write(workload_template.substitute(
        name=name,
        task=quote(workload["task"]),
        hostname=quote(hostname.rstrip("/")),
        users=workload["users"],
        spawn_rate=quote(str(workload["spawn_rate"])),
        iterations=quote(str(workload["iterations"])),
        run_time=quote(str(workload["run_time"])),
        processes=workload["processes"],
        timeout=timeout,
        src_dir=quote(src_dir),
        logs_dir=quote(logs_dir),
        stats_location=quote(os.path.join(results_dir, f"{workload['users']}-{name}.csv")),
        failures_location=quote(os.path.join(logs_dir, f"{workload['users']}-{name}-failures.csv")),
        exceptions_location=quote(os.path.join(logs_dir, f"{workload['users']}-{name}-exceptions.csv")),
        workload_log=quote(os.path.join(logs_dir, f"{name}-locust.log")),
        error_log=quote(os.path.join(logs_dir, f"{name}_error.log")),
      ))
      script.write(f"\n########## {name} - End   #############\n")

    script.write("\n\n##########  Summary   #############\n")
    script.write("if print_summary; then\n  exit 0\nfi\nexit 1\n")

  os.chmod(script_path, 0o755)
  logging.info(f"Created {script_path}")


if __name__ == "__main__":
  main()
