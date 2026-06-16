# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
# Header verification comment inserted

from events import *
from auth import *
from exception import *
from locust_plugins.users.playwright import PlaywrightUser, pw, event, PageWithRetry
import traceback
import asyncio
import logging
from locust import runners
import subprocess

class sasviyacli_batch(PlaywrightUser):

    logger = logging.getLogger(__name__)
    multiplier = 1
    TIMEOUT_SHORT = 20000
    TIMEOUT_LONG =  60000

    @task
    @pw
    async def test_sasviyacli_batch(self, page: PageWithRetry):

        browser = self.browser
        context = self.browser_context

        page.set_default_timeout(timeout=self.TIMEOUT_LONG)
        if len(usernames) == 0:
            self.logger.info(f"No more users in the list, exiting as success")
            exit(0)


        user_ray = usernames.pop(random.randrange(len(usernames)))
        user = user_ray[0]
        password = user_ray[1]

        async with event(self, "01: Starting New sasviyacli batch tests"):
          print(f"User: {user} is STARTING test.sas batch tests now.")   
          subprocess.run('cp /lotest/src/trustedcerts.pem /home/locust', shell = True)
          subprocess.run('cp /lotest/src/test.sas /home/locust', shell = True)
          subprocess.run('chmod 777 /home/locust/test.sas', shell = True)
            
          subprocess.run('cp /lotest/src/config.json /root/.sas/', shell = True)
          subprocess.run('chmod 777 /root/.sas/config.json', shell = True)
          subprocess.run('cat /root/.sas/config.json', shell = True)
          subprocess.run('echo export SSL_CERT_FILE=/home/locust/trustedcerts.pem', shell = True)
          print(f"User: {user} is validating to sas viya cli")
          command = f"SSL_CERT_FILE=/home/locust/trustedcerts.pem /root/sas-viya --profile Default authenticate login -u {user} -p {user}"
          subprocess.run(command, shell=True)     
 
          subprocess.run('echo SUCCESSFUL', shell = True)
          print(f"User: {user} succesfully validated to sas viya cli")
          result = subprocess.run('SSL_CERT_FILE=/home/locust/trustedcerts.pem /root/sas-viya batch jobs submit-pgm -c default --job-name test --wait-results --rem-pgm-path test.sas --job-file test.sas --results-dir /tmp', shell=True)
          print(f"Command output: {result.stdout}")
          if result.returncode != 0:
             print(f"Command exited with code: {result.returncode}")
          print(f"User: {user} has FINISHED running test.sas batch tests now.")

                

