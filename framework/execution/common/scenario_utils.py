# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import base64
import json
import csv
import os
from locust_plugins.csvreader import CSVReader
from kubernetes import client, config
from kubernetes.client.rest import ApiException

class UsersManager:
    """Manages retrieval and decoding of Kubernetes secrets."""
    
    def __init__(self):
        """Initialize Kubernetes client with in-cluster config."""
        config.load_incluster_config()
        self.v1 = client.CoreV1Api()

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
          secret = self.v1.read_namespaced_secret(name=secret_name, namespace=namespace)
          # Decode the secret (secrets are base64 encoded)
          decoded_key = base64.b64decode(secret.data[secret_key]).decode('utf-8')
          user_dict = json.loads(decoded_key)
          user_list = [[username, password] for username, password in user_dict.items()]
          
          return user_list
        except ApiException as e:
            print(f"Exception when retrieving secret: {e}")
            return []
    
    def get_user_list(self, secret_name: str = "validation-scenarios", 
                     namespace: str = "testing", 
                     secret_key: str = "users-file-dict") -> list:
        
        # Check if the CSV file exists, if it does return that as the user list. If it was not passed in as an argument, then get it from the k8s Secrets
        csv_file_path = '/lotest/src/users.csv'
        if os.path.exists(csv_file_path):
          print(f"CSV file is available at {csv_file_path}. Using that as the user list.")
          return self.get_users_from_csv(csv_file_path)
        else:
          print(f"CSV file doesn't exist at {csv_file_path}. Getting user list from k8s secret instead.")
          return self.get_users_from_k8s_secret(secret_name, namespace, secret_key)
        



        
