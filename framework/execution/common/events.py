# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

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
import base64
import csv
import gzip
import io
import json
import sys
import threading


from scenario_utils import UsersManager

# Pods always run headless. Local runs set SAS_VALIDATION_HEADLESS=false to watch the browser.
PlaywrightUser.headless = os.environ.get("SAS_VALIDATION_HEADLESS", "true").strip().lower() not in (
    "0", "false", "no", "off"
)

# Load user credentials from Kubernetes secret
test_users = UsersManager()
user_list = test_users.get_user_list()

usernames = [] # This list will be sent to each user chunked by the number of users, initialize as empty array
usernames_lock = threading.Lock() # Protects usernames from concurrent pop() calls across simulated users

def setup_test_users(environment, msg, **kwargs):
    # Fired when the worker receives a message of type 'test_users'
    usernames.extend(map(lambda u: u, msg.data))
    environment.runner.send_message("acknowledge_users", f"Thanks for the {len(msg.data)} users!")
    #environment.runner.send_message("acknowledge_users", f"Here are the users I received: {msg.data}")

def on_acknowledge(msg, **kwargs):
    # Fired when the master receives a message of type 'acknowledge_users'
    print(msg.data)


@events.init.add_listener
def on_locust_init(environment, **_kwargs):
    global start_time, _environment
    _environment = environment
    start_time = datetime.now()
    print(f"Start of run: {start_time.strftime('%Y%m%d-%H:%M:%S')}")
    # set up test users for the workers & local runner
    if not isinstance(environment.runner, MasterRunner):
        environment.runner.register_message("test_users", setup_test_users)
    if not isinstance(environment.runner, WorkerRunner):
        environment.runner.register_message("acknowledge_users", on_acknowledge)

@events.test_start.add_listener
def on_test_start(environment, **_kwargs):
    # When the test is started, evenly divides list between
    # worker nodes to ensure unique data across threads
    if isinstance(environment.runner, MasterRunner):
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

    elif not isinstance(environment.runner, WorkerRunner):
        # LocalRunner: single process, no workers to message — use all users directly
        usernames.extend(map(lambda u: u, user_list))

    print(f"[DEBUG] on_test_start finished: usernames list has {len(usernames)} entries")

@events.quitting.add_listener
def _(environment, **kw):
    if environment.stats.total.fail_ratio > 0.01:
        environment.process_exit_code = 1
    else:
        environment.process_exit_code = 0

    global end_time
    end_time = datetime.now()
    print(f"End of run: {end_time.strftime('%Y%m%d-%H:%M:%S')}")
    # Calculate duration
    duration = end_time - start_time
    print(f"Duration of the Total test run: {str(duration)}")


# Results are published through the master's stdout (the pod log), so runWorkload.sh can read them
# with `kubectl logs` after the master has exited instead of copying files out of a running container.
# Each CSV is gzip+base64 encoded onto a single line: "SAS_VALIDATION_RESULT <name> <payload>".
RESULT_MARKER = "SAS_VALIDATION_RESULT"
_environment = None


def _encode_csv(render):
    buffer = io.StringIO()
    render(csv.writer(buffer))
    compressed = gzip.compress(buffer.getvalue().encode("utf-8"), mtime=0)
    return base64.b64encode(compressed).decode("ascii")


def build_result_lines(environment, exit_code, stats_csv=None):
    if stats_csv is None:
        from locust.stats import StatsCSV, PERCENTILES_TO_REPORT
        stats_csv = StatsCSV(environment, PERCENTILES_TO_REPORT)
    return [
        f"{RESULT_MARKER} stats {_encode_csv(stats_csv.requests_csv)}",
        f"{RESULT_MARKER} failures {_encode_csv(stats_csv.failures_csv)}",
        f"{RESULT_MARKER} exceptions {_encode_csv(stats_csv.exceptions_csv)}",
        f"{RESULT_MARKER} exit_code {exit_code}",
    ]


@events.quit.add_listener
def publish_results(exit_code, **_kwargs):
    # Fired last during shutdown, after the exit code is final and the summary is printed.
    if _environment is None or isinstance(_environment.runner, WorkerRunner):
        return
    try:
        lines = build_result_lines(_environment, exit_code)
    except Exception as exc:  # never block shutdown; the script reports missing results
        print(f"{RESULT_MARKER} publish_failed {type(exc).__name__}", flush=True)
        return
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()
