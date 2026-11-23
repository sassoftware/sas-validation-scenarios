# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import base64
import json
import csv
import os
from locust_plugins.csvreader import CSVReader
from kubernetes import client, config
from kubernetes.client.rest import ApiException

SERVICE_ACCOUNT_NAMESPACE_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
DEFAULT_NAMESPACE = "testing"
# Users file mounted from the config map in the Locust pods.
POD_USERS_FILE = "/lotest/src/users.csv"
# Users file for runs outside Kubernetes (set by the generated runWorkloadLocal.sh).
USERS_FILE_ENV = "SAS_VALIDATION_USERS_FILE"

class UsersManager:
    """Manages retrieval and decoding of Kubernetes secrets."""
    
    def __init__(self):
        # The Kubernetes client is created only when the users come from the secret, so local
        # runs that read a users file never need in-cluster configuration.
        self.v1 = None

    def _core_api(self):
        if self.v1 is None:
            config.load_incluster_config()
            self.v1 = client.CoreV1Api()
        return self.v1

    def get_users_from_csv(self, csv_file_path: str) -> list:
        try:
          with open(csv_file_path, 'r', newline='', encoding='utf-8') as csvfile:
            csv_reader = csv.reader(csvfile)
            user_list = list(csv_reader)
            return user_list
        except FileNotFoundError:
          print(f"Error: File not found at {csv_file_path}")
          return []
        except Exception as e:
          print(f"An error occurred: {e}")
          return []

    def get_users_from_k8s_secret(self, secret_name: str, namespace: str, secret_key: str) -> list:
        try:
          secret = self._core_api().read_namespaced_secret(name=secret_name, namespace=namespace)
          # Decode the secret (secrets are base64 encoded)
          decoded_key = base64.b64decode(secret.data[secret_key]).decode('utf-8')
          user_dict = json.loads(decoded_key)
          user_list = [[username, password] for username, password in user_dict.items()]
          
          return user_list
        except ApiException as e:
            print(f"Exception when retrieving secret: {e}")
            return []
    
    def get_namespace(self) -> str:
        """Namespace this pod runs in (POD_NAMESPACE, then service account namespace file)."""
        env_namespace = os.environ.get("POD_NAMESPACE")
        if env_namespace:
            return env_namespace.strip()
        try:
            with open(SERVICE_ACCOUNT_NAMESPACE_FILE, 'r', encoding='utf-8') as f:
                pod_namespace = f.read().strip()
                if pod_namespace:
                    return pod_namespace
        except OSError:
            pass
        return DEFAULT_NAMESPACE

    def get_user_list(self, secret_name: str = "validation-scenarios", 
                     namespace: str = None, 
                     secret_key: str = "users-file-dict") -> list:
        
        # A local run names its users file explicitly and never falls back to the k8s secret.
        local_users_file = os.environ.get(USERS_FILE_ENV, "").strip()
        if local_users_file:
          print(f"Using the users file from {USERS_FILE_ENV}: {local_users_file}")
          return self.get_users_from_csv(local_users_file)

        if not namespace:
          namespace = self.get_namespace()
        
        # Check if the CSV file exists, if it does return that as the user list. If it was not passed in as an argument, then get it from the k8s Secrets
        csv_file_path = POD_USERS_FILE
        if os.path.exists(csv_file_path):
          print(f"CSV file is available at {csv_file_path}. Using that as the user list.")
          return self.get_users_from_csv(csv_file_path)
        else:
          print(f"CSV file doesn't exist at {csv_file_path}. Getting user list from k8s secret instead.")
          return self.get_users_from_k8s_secret(secret_name, namespace, secret_key)
        



        
