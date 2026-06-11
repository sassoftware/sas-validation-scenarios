# SAS Validation Scenarios: Resource Setup Guide

🚧 **This page is a work in progress** 🚧

## Table of Contents
1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [OAuth Client Setup](#oauth-client-setup)
4. [Global Configuration](#global-configuration)
5. [Generate and Run Scripts](#generate-and-run-scripts)

## Overview
Many validation scenarios in this repository require extensive SAS Viya configuration before they can be executed. For example, the `vf-segmentation-wrkld-def` scenario requires:

- Creating multiple CAS libraries (CASLibs)
- Modifying the "allow list" in CAS
- Creating several folders on the NFS mount
- Transferring data files to the environment  
- Converting and importing Model Studio projects

This automated resource setup process streamlines the creation and configuration of these prerequisite resources in your Viya environment, eliminating manual setup tasks and ensuring consistent deployments.

## Prerequisites
Before proceeding with the resource setup, ensure you have completed all the initial setup steps outlined in the main guide:

**[SAS Validation Scenarios README](../../README.md)**

## OAuth Client Setup
To enable REST API authentication and token retrieval, you must create an OAuth client by following the steps in this article:

**[Obtaining an access token for a service account](http://aat.glpages.sas.com/sas-valueforge-program/en/sections/generic/implementation-guides/oauth/20250306/runtimes/#obtaining-an-access-token-for-a-service-account)**

### Important Instructions

⚠️ **Follow the instructions up to the step called "Authenticate to the Viya environment as the service account using the CLI":**

```bash
sas-viya auth loginCode
```

**What to do:**

1. Obtain the authorization code when prompted
2. Provide it to the CLI as instructed
3. **Stop here** - you do not need to proceed beyond this step for the validation scenarios


## Global Configuration

Your Global Config requires several additional properties for resource setup. 

### Step 1: Configure Your Global Config File

Use the provided advanced template and update it with your environment details.

ℹ️ **Current Support:** This resource setup process currently supports Model Studio scenarios only. Additional scenario types may be added in future releases.

### 💡 Best Practice: Organize Your Configuration Files

Create a dedicated `configs` folder to store your modified configuration files and "user.csv" files within the `validation-scenarios` directory. This approach offers several benefits:

- **Organization**: Keeps all your custom configurations in one place
- **Git-friendly**: The `configs` folder is automatically ignored by Git when created under `validation-scenarios`
- **Easy maintenance**: Simplifies backup and version control of your configurations

```bash
cd ./validation-scenarios
mkdir configs
```

**Usage example:** Copy and modify your template files in this folder:
```bash
cp global-config-model-studio-advanced.yaml.template configs/my-global-config.yaml
```

## Generate and Run Scripts

### Step 2: Generate Resource Setup Scripts

Run the following command, substituting the appropriate paths for your system:

```bash
./generateWorkloads.sh \
-g ./configs/my-global-config.yaml \
-w ./workload-definitions/vf-segmentation-wrkld-def.yaml \
-u ./configs/10-users.csv \
-r ./scenarios/model-studio/vf-segmentation/resource-config.yaml \
-l DEBUG
```

**Parameters explained:**
- `-g`: Path to your global configuration file
- `-w`: Workload definition file
- `-u`: User CSV file
- `-r`: Resource configuration file
- `-l`: Log level (DEBUG for detailed output)


### Step 3: Deploy Resources to Viya Environment

Finally, run the generated script to create the necessary artifacts in your Viya environment:

```bash
./generated/workload-setup/vf-segmentation/artifacts/runScenarioConfig.sh
```

**Expected outcome:** This will create the required resources and configurations in your Viya environment for running the validation scenarios.
