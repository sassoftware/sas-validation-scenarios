# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import yaml
import argparse
import os
import string
from string import Template

print()
print(f"Creating script to get the refresh token from Viya CLI")
print()

# Create an ArgumentParser object
parser = argparse.ArgumentParser(description="Argument parser")

# Add named arguments
parser.add_argument("-a", "--artifactPath", type=str, help="Artifacts path", required=True)

# Parse the arguments
args = parser.parse_args()

# Read the environment variable
frameworkResourcesLocation = os.getenv("frameworkResourcesLocation")
cli_profile = os.getenv("cliProfile")

print(f"Artifacts Path: {args.artifactPath}")

# Print the values of the variables for debugging purposes
print(f"Viya CLI Profile: {cli_profile}") 

if not cli_profile:
    print("Error: Variable viya-cli-profile is not set in the global-config file.")
    exit(1)

#Read the contents of ~/.sas/credentials.json
credentials_file_path = os.path.expanduser("~/.sas/credentials.json")
if not os.path.exists(credentials_file_path):
    print(f"Error: Credentials file not found at {credentials_file_path}.")
    exit(1)

with open(credentials_file_path, 'r') as file:
    credentials = json.load(file)
    if not credentials:
        print(f"Error: Credentials file is empty at {credentials_file_path}.")
        exit(1)


    
