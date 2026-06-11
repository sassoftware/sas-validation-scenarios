# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import yaml
import argparse
import logging
import os
import string
from string import Template
from frameworkLib import Framework
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
parser.add_argument("-a", "--artifact_path", type=str, help="Artifacts path", required=True)
parser.add_argument("-r", "--scenario_path", type=str, help="Scenario base path", required=True)
parser.add_argument("-p", "--build_path", type=str, help="Output build path", required=True)
parser.add_argument("-l", "--log_level", type=str, help="Output build path", required=False, default="INFO")

# Parse the arguments
args = parser.parse_args()

log_level=args.log_level.upper()
logging.getLogger().setLevel(log_level)
logging.info("Log Level set to: %s", log_level)

logging.info(f"Creating the Model Studio import script")

# Read the environment variable
framework_resources_location = os.getenv("frameworkResourcesLocation")
hostname = os.getenv("hostname")
pem_file = os.getenv("pemFile")
cas = os.getenv("cas")
cas_server = os.getenv("casServer")
viya_cli_profile = os.getenv("viyaCliProfile")
ms_project_import = os.getenv("modelStudioProjectImport")
ms_global = os.getenv("modelStudio")

auth_type = os.getenv("authClientType")
if not auth_type:
    logging.error("Global property 'auth-type' is not set.")
    raise ValueError("Global property 'auth-type' is not set.")
auth_client_id = os.getenv("authClientId")
if not auth_client_id:
    logging.error("Global Property 'auth-client-id' is not set.")
    raise ValueError("Global Property 'auth-client-id' is not set.")
auth_client_secret = os.getenv("authClientSecret")
if not auth_client_secret:
    logging.error("Global property 'auth-client-secret' is not set.")
    raise ValueError("Global property 'auth-client-secret' is not set.")

logging.info(f"Scenario Base Path: {args.scenario_path}")
logging.info(f"Artifacts Path: {args.artifact_path}")
logging.info(f"Template: {args.template}")

# Load the ms_project_import and users properties as a dictionary
ms_projects_list = Framework.safe_json_loads(ms_project_import) 
logging.info(f"Model Studio Project Import: {ms_projects_list}")

#Get the first project in the list and assign it to ms_project
if ms_projects_list:
    ms_project = ms_projects_list[0]
    logging.info(f"Model Studio Project: {ms_project}")

ms_global_dict = json.loads(ms_global)
cas_dict = json.loads(cas)

# read the "users" property from the ms_global_dict
users_dict = ms_global_dict.get("users")

# Read the properties into variables
import_converter = ms_global_dict.get("import-converter")

ms_project = ms_projects_list[0] if ms_projects_list else None
logging.info(f"Model Studio Project: {ms_project}")

project_name = ms_project.get("project-name") if ms_project else None
project_table = ms_project.get("project-data-source") if ms_project else None
project_zip_location = ms_project.get("project-zip-location") if ms_project else None
project_caslib = ms_project.get("project-caslib") if ms_project else None

# Print the values of the variables for debugging purposes
logging.info(f"Model Studio Import variables:")
logging.info(f"  import_converter: {import_converter}")
logging.info(f"  project_name: {project_name}")  
logging.info(f"  project_zip_location: {project_zip_location}")
logging.info(f"  project_table: {project_table}")
logging.info(f"  project_caslib: {project_caslib}")
logging.info(f"  cas_server: {cas_server}")

# Grab the username and password from the users dictionary
user_list = " ".join(user.get("username") for user in users_dict if "username" in user)
password_list = " ".join(user.get("password") for user in users_dict if "password" in user)

project_zip_full_location = os.path.normpath(os.path.join(args.scenario_path, project_zip_location)) if project_zip_location else None
logging.info(f"Project zip full location: {project_zip_full_location}")   

#Read the template file
with open(args.template, 'r', encoding='utf-8') as file:
  template_file = file.read()

  if not ms_project:
    logging.info("No Model Studio project configured.")
    run_import_template = "#!/usr/bin/env bash\n\n ## No Model Studio project imports configured."
  else:
    ms_import_template = string.Template(template_file)
    run_import_template = ms_import_template.substitute(user_list=user_list, password_list=password_list, build_path=args.build_path, 
        hostname=hostname, pem_file=pem_file, viya_cli_profile=viya_cli_profile,
        import_converter=import_converter, project_name=project_name, project_zip_location=project_zip_full_location, cas_server=cas_server, 
        project_caslib=project_caslib, project_table=project_table, auth_client_id=auth_client_id, auth_client_secret=auth_client_secret)
    
    file.close

# Ensure the artifact path exists and is writable
if not os.path.exists(args.artifact_path):
    logging.error(f"The directory '{args.artifact_path}' does not exist.")
    raise FileNotFoundError(f"The directory '{args.artifact_path}' does not exist.")
if not os.access(args.artifact_path, os.W_OK):
    logging.error(f"The directory '{args.artifact_path}' is not writable.")
    raise PermissionError(f"The directory '{args.artifact_path}' is not writable.")

with open(os.path.join(args.artifact_path, "importModelStudioProject.sh"), "w") as file:
  file.write(run_import_template)
  file.close

# Make the script executable
os.chmod(os.path.join(args.artifact_path, "importModelStudioProject.sh"), 0o755)
