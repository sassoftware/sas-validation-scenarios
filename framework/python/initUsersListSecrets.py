# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import argparse
import os
import logging
import string
import base64
import csv
import json
from cryptography.fernet import Fernet
from kubernetes import client, config
from kubernetes.client.rest import ApiException

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
parser.add_argument("-f", "--usersFile", type=str, help="Users CSV file", required=True)
parser.add_argument("-n", "--namespace", type=str, help="K8s namespace", required=True)
parser.add_argument("-l", "--logLevel", type=str, help="Log level", required=False, default="INFO")

# Parse the arguments
args = parser.parse_args()

log_level=args.logLevel.upper()
logging.getLogger().setLevel(log_level)
logging.info("Log Level set to: %s", log_level)

logging.info(f"Encrypting users file and storing in k8s Secrets")

# Load kubeconfig from default location
config.load_kube_config(config_file=os.environ.get('KUBECONFIG'))

# Create API clients
coreV1Api = client.CoreV1Api()
rbacV1Api = client.RbacAuthorizationV1Api()

# Ensure that the namespace exists
namespace = args.namespace
try:
    coreV1Api.read_namespace(name=namespace)
    logging.info(f"Namespace '{namespace}' found.")
except ApiException as e:
    if e.status == 404:
        logging.error(f"Namespace '{namespace}' does not exist.")
        raise Exception(f"Namespace '{namespace}' does not exist.") # Exit if the namespace does not exist
    else:
        logging.error(f"Error checking for namespace '{namespace}': {e}")
        raise # Exit on other errors

#Store the location of the users file
users_file_location = args.usersFile
logging.info(f"Users File: {users_file_location}")

#Read the csv file
with open(users_file_location, 'rb') as file:
    users_file = file.read()

# Create a Kubernetes Secret to store the users
secret_name = "validation-scenarios"

# Iterate though the users file and store usernames and passwords in a dictionary
user_dict = {}
with open(users_file_location, 'r', newline='', encoding='utf-8') as csvfile:
    csv_reader = csv.reader(csvfile)
    for row in csv_reader:
        if len(row) >= 2:
            username = row[0]
            password = row[1]
            user_dict[username] = password
        else:
            logging.warning(f"Skipping invalid row in CSV: {row}")  
logging.info(f"Total users read from CSV: {len(user_dict)}")

service_account_name = "default"
role_name = f"validation-scenarios-secrets-reader"
role_binding_name = f"validation-scenarios-secrets-reader-binding"

# Create the secret body
secret_body = client.V1Secret(
    api_version="v1",
    kind="Secret",
    metadata=client.V1ObjectMeta(
        name=secret_name,
        namespace=namespace
    ),
    data={
        "users-file-dict": base64.b64encode(json.dumps(user_dict).encode('utf-8')).decode('utf-8')
    }
)

# Create or update the Secret
try:
    coreV1Api.create_namespaced_secret(namespace, secret_body)
    logging.info(f"Created secret: {secret_name}")
except ApiException as e:
    if e.status == 409:
        logging.info(f"Secret {secret_name} already exists, updating it")
        coreV1Api.replace_namespaced_secret(secret_name, namespace, secret_body)
        logging.info(f"Updated secret: {secret_name}")
    else:
        logging.error(f"Failed to create secret: {e}")
        raise

# Create Role for secret access
role_body = client.V1Role(
    api_version="rbac.authorization.k8s.io/v1",
    kind="Role",
    metadata=client.V1ObjectMeta(
        name=role_name,
        namespace=namespace
    ),
    rules=[
        client.V1PolicyRule(
            api_groups=[""],
            resources=["secrets"],
            verbs=["get"],
            resource_names=[secret_name]
        )
    ]
)

# Create or update the Role
try:
    rbacV1Api.create_namespaced_role(namespace, role_body)
    logging.info(f"Created role: {role_name}")
except ApiException as e:
    if e.status == 409:
        logging.info(f"Role {role_name} already exists, updating it")
        rbacV1Api.replace_namespaced_role(role_name, namespace, role_body)
        logging.info(f"Updated role: {role_name}")
    else:
        logging.error(f"Failed to create role: {e}")
        raise

# Create RoleBinding - using dictionary structure instead of V1Subject
role_binding_body = client.V1RoleBinding(
    api_version="rbac.authorization.k8s.io/v1",
    kind="RoleBinding",
    metadata=client.V1ObjectMeta(
        name=role_binding_name,
        namespace=namespace
    ),
    subjects=[
        {
            "kind": "ServiceAccount",
            "name": service_account_name,
            "namespace": namespace
        }
    ],
    role_ref={
        "kind": "Role",
        "name": role_name,
        "apiGroup": "rbac.authorization.k8s.io"
    }
)

# Create or update the RoleBinding
try:
    rbacV1Api.create_namespaced_role_binding(namespace, role_binding_body)
    logging.info(f"Created role binding: {role_binding_name}")
except ApiException as e:
    if e.status == 409:
        logging.info(f"RoleBinding {role_binding_name} already exists, updating it")
        rbacV1Api.replace_namespaced_role_binding(role_binding_name, namespace, role_binding_body)
        logging.info(f"Updated role binding: {role_binding_name}")
    else:
        logging.error(f"Failed to create role binding: {e}")
        raise

logging.info(f"Granted '{service_account_name}' service account access to secret '{secret_name}'")

# Verify by reading the secret back
try:
    secret = coreV1Api.read_namespaced_secret(secret_name, namespace)
    encoded_user_dict = secret.data['users-file-dict']
    decoded_user_dict = base64.b64decode(encoded_user_dict).decode('utf-8')
    user_dict_from_secret = json.loads(decoded_user_dict)
    
    if user_dict_from_secret == user_dict:
        logging.info("Successfully read and verified users from k8s secret.")
        logging.info(f"Total users in the k8s secret: {len(user_dict_from_secret)}")
    else:
        logging.error("Mismatch between original users and users read from k8s secret.")
except ApiException as e:
    logging.error(f"Failed to read secret: {e}")
    raise

