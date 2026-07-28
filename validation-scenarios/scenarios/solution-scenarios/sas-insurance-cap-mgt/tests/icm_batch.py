# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from events import *
from auth import *
from exception import *
from locust_plugins.users.playwright import PlaywrightUser, pw, event, PageWithRetry
import traceback
import asyncio
import logging
from locust import runners
from locust import task
import subprocess

class sasviyacli_batch(PlaywrightUser):

    logger = logging.getLogger(__name__)
    multiplier = 1
    TIMEOUT_SHORT = 20000
    TIMEOUT_LONG =  60000

    
    cadence = "2026.06"
    loopcount = "1"


    @task
    @pw
    async def icm_sasviyacli_batch(self, page: PageWithRetry):

        browser = self.browser
        context = self.browser_context

        page.set_default_timeout(timeout=self.TIMEOUT_LONG)
        if len(usernames) == 0:
            self.logger.info(f"No more users in the list, exiting as success")
            exit(0)


        user_ray = usernames.pop(random.randrange(len(usernames)))
        user = user_ray[0]
        password = user_ray[1]

        async with event(self, "01: Starting ICM sasviyacli batch tests"):
          print(f"User: {user} is STARTING icm_batch.sas batch tests now.")   
          subprocess.run('cp /lotest/src/trustedcerts.pem /home/locust', shell = True)
          subprocess.run('cp /lotest/src/icm_batch.sas /home/locust', shell = True)
          subprocess.run('chmod 777 /home/locust/icm_batch.sas', shell = True)
            
          subprocess.run('cp /lotest/src/config.json /root/.sas/', shell = True)
          subprocess.run('chmod 777 /root/.sas/config.json', shell = True)
          subprocess.run('cat /root/.sas/config.json', shell = True)
          subprocess.run('echo export SSL_CERT_FILE=/home/locust/trustedcerts.pem', shell = True)
          print(f"User: {user} is validating to sas viya cli")
          command = f"SSL_CERT_FILE=/home/locust/trustedcerts.pem /root/sas-viya --profile Default authenticate login -u {user} -p {password}"
          subprocess.run(command, shell=True)     
 
          subprocess.run('echo SUCCESSFUL', shell = True)
          print(f"User: {user} succesfully validated to sas viya cli")
                
          sysparm = f"{self.cadence}#{self.loopcount}"

          print(f"Using SYSPARM: {sysparm}")

          batch_cmd = (
                f'SSL_CERT_FILE=/home/locust/trustedcerts.pem '
                f'/root/sas-viya batch jobs submit-pgm '
                f'-c default '
                f'--job-name test_{user} '
                f'--wait-results '
                f'--rem-pgm-path icm_batch.sas '
                f'--job-file /home/locust/icm_batch.sas '
                f'--results-dir /tmp '
                f'--sas-option "-sysparm {sysparm}"'
          )

          print("\n===== BATCH COMMAND =====")
          print(batch_cmd)

          result = subprocess.run(
                batch_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
          )

          print("\n===== BATCH STDOUT =====")
          print(result.stdout)

          print("\n===== BATCH STDERR =====")
          print(result.stderr)

          print(f"\nReturn Code: {result.returncode}")

          if result.returncode != 0:
              print(f"Command exited with code: {result.returncode}")

          print(f"User: {user} has FINISHED running icm_batch.sas batch tests now.")


          

                

