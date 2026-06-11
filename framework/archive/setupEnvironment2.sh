#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


# Check if a file is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <yaml-file>"
  exit 1
fi

# Check if yq is installed
if ! command -v yq &> /dev/null; then
  echo "yq could not be found, please install it first."
  exit 1
fi

# Create a temporary file to store yq output
temp_file=$(mktemp)

# Read the YAML file and set environment variables
yq eval '.[]' "$1" > "$temp_file"

while IFS= read -r line; do
  # Skip comments
  if [[ "$line" =~ ^[[:space:]]*# ]]; then
    continue
  fi

  key=$(echo "$line" | yq eval 'keys | .[0]' -)
  value=$(echo "$line" | yq eval '.[].value' -)

  # Convert key to camel case
  key=$(echo "$key" | awk -F'_' '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) tolower(substr($i,2))}1' OFS='')
  key=$(echo "$key" | awk -F'-' '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) tolower(substr($i,2))}1' OFS='')
  key=$(echo "$key" | awk '{print tolower(substr($0,1,1)) substr($0,2)}')

  echo "Exporting $key=$value"
  export "$key"="$value"
  
done < "$temp_file"

# Remove the temporary file
rm "$temp_file"

# Print all environment variables for verification
# env
