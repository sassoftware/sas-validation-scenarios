# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# from locust import run_single_user, task, User
import random
from playwright._impl._errors import TargetClosedError
from locust.runners import MasterRunner, WorkerRunner
import logging
from locust import task, events, HttpUser, TaskSet, between
import inspect
import os
import re
import time
import asyncio 
from locust.exception import StopUser
from locust_plugins.users.playwright import PageWithRetry, PlaywrightUser, PlaywrightScriptUser, pw, event
from os import environ
from datetime import datetime
from random import randrange
from locust import run_single_user, task
from playwright.async_api import Page, expect, async_playwright, TimeoutError as PlaywrightTimeoutError
from locust_plugins.csvreader import CSVReader
from dotenv import load_dotenv, dotenv_values 



PlaywrightUser.headless = True # set to False to see the browser in action

user_list = [
   ["user1", "pw1"],
   ["user2", "pw2"],
   ["user3", "pw3"],
   ["user4", "pw4"], 
   ["user5", "pw5"]

]


#USERS_PASSWORD = "$(user_emails)"

usernames = [] # This list will be sent to each user chunked by the number of users, initialize as empty array

def setup_test_users(environment, msg, **kwargs):
    # Fired when the worker receives a message of type 'test_users'
    usernames.extend(map(lambda u: u, msg.data))
    environment.runner.send_message("acknowledge_users", f"Thanks for the {len(msg.data)} users!")
    environment.runner.send_message("acknowledge_users", f"Here are the users I received: {msg.data}")

def on_acknowledge(msg, **kwargs):
    # Fired when the master receives a message of type 'acknowledge_users'
    print(msg.data)


@events.init.add_listener
def on_locust_init(environment, **_kwargs):
    if not isinstance(environment.runner, MasterRunner):
        environment.runner.register_message("test_users", setup_test_users)
    if not isinstance(environment.runner, WorkerRunner):
        environment.runner.register_message("acknowledge_users", on_acknowledge)


@events.test_start.add_listener
def on_test_start(environment, **_kwargs):
    # When the test is started, evenly divides list between
    # worker nodes to ensure unique data across threads
    if not isinstance(environment.runner, WorkerRunner):
        users = user_list

        worker_count = environment.runner.worker_count
        chunk_size = int(len(users) / worker_count)

        for i, worker in enumerate(environment.runner.clients):
            start_index = i * chunk_size

            if i + 1 < worker_count:
                end_index = start_index + chunk_size
            else:
                end_index = len(users)

            data = users[start_index:end_index]
            environment.runner.send_message("test_users", data, worker)

