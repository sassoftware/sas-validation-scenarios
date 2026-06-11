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

class logonoff(PlaywrightUser):

    logger = logging.getLogger(__name__)
    multiplier = 1
    TIMEOUT_SHORT = 20000
    TIMEOUT_LONG =  60000

    @task
    @pw
    async def test_logonoff (self, page: PageWithRetry):

        browser = self.browser
        context = self.browser_context
        page.set_default_timeout(timeout=self.TIMEOUT_LONG)
        if len(usernames) == 0:
            self.logger.info(f"No more users in the list, exiting as success")
            exit(0)
        
        user_ray = usernames.pop(random.randrange(len(usernames)))
        user = user_ray[0]
        password = user_ray[1]

        async with event(self, "01: Navigating to /SASLogon URL"):
          try:
            self.logger.info(f"Navigating to /SASLogon url")
            await page.goto("/SASLogon/home")
            await expect(page.get_by_label("SAS logo")).to_be_visible()
            await expect(page.get_by_label("User ID:")).to_be_visible()
          except:
            await exception_handling("Unable to access /SASLogon url", user)
            raise
         
        async with event(self, "02: Authenticating to /SASLogon "):
          try:  
            self.logger.info(f"Authenticating to SASLogon")
            await ldap_auth(page, user, password)
            self.logger.info(f"Authentication Successful")
          except:
            await exception_handling("Failed to Authenticate", user)
            raise
 
        async with event(self, "03: Adding 5sec sleep time to capture logs"):
          self.logger.info(f"This test is very quick and finishes in less that a second.")
          self.logger.info(f"In a multiuser setup the tests finishes before the logs get written.")
          self.logger.info(f"Adding a sleep of 5 sec to get around this issue.")
          time.sleep(5)

        async with event(self, "04: Logging out"):
          try:  
            self.logger.info(f"Starting to Logout")
            await page.get_by_role("link", name="Sign out").click()
            await expect(page.get_by_role("heading", name="You have signed out.")).to_be_visible()
            self.logger.info(f"Finished Logging out")
            self.logger.info(f"TESTS FINISHED")
          except:
            await exception_handling("Failed to Logout", self)
            raise



