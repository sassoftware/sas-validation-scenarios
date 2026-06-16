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

class createcompute(PlaywrightUser):

    logger = logging.getLogger(__name__)
    multiplier = 1
    TIMEOUT_SHORT = 20000
    TIMEOUT_LONG =  60000

    @task
    @pw
    async def test_createcompute(self, page: PageWithRetry):

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

        async with event(self, "03: Navigating to SAS Studio"):
            self.logger.info(f"Navigating to SAS Studio")
            await page.goto("/SASStudio/" , timeout=60000)
            timestamp = random.randint(1000, 9999)
           
        async with event(self, "04: Creating SAS Studio compute Context"):
          try:  
            self.logger.info(f"Start: Creating Studio Compute Context")
            await expect(page.get_by_test_id("appHeaderToolbar-studioActiveServerObjectMarker").locator("svg")).not_to_be_visible(timeout=60000)
            await expect(page.get_by_test_id("appHeaderToolbar-studioActiveServerButton")).to_be_visible(timeout=60000) 
            time.sleep(3) 
            self.logger.info(f"Closing the Start Page Tab")
            await page.get_by_test_id("tab-0").get_by_text("Start Page").click()
            await page.locator(".sas-icon.sas_components-SVG-SVG_svg.sas_components-SVG-SVG_icon.sas_components-Icon-Icon_icon > .CloseTab").click()
            self.logger.info(f"Opening the New SAS Program Tab")
            await page.get_by_test_id("appHeaderToolbar-new-button").click()
            await page.get_by_test_id("appHeaderToolbar-sascode-text").click()   
            await page.get_by_test_id("tab-group-bar-_root_").get_by_text("SAS Program.sas").click()
            await page.locator(".view-line").first.click()
            self.logger.info(f"Waiting for runButton to be enabled")
            await expect(page.get_by_test_id("programViewPane-toolbar-runButton")).to_be_enabled(timeout=60000)
            self.logger.info(f"Finished Creating Studio Compute Context")
          except:
            await exception_handling("Failed to create compute context", user)
            raise

        async with event(self, "05: Adding 5 second sleep time to capture logs"):
          self.logger.info(f"This test is very quick and finishes fast.")
          self.logger.info(f"In a multiuser setup the tests finishes before the logs get written.")
          self.logger.info(f"Adding a sleep of 5 sec to get around this issue.")
          time.sleep(5)

        async with event(self, "06: Signing Out"):
          try:  
            self.logger.info(f"Start: Signing Out from SAS Studio")
            await page.locator(".sas_components-Banner-Banner_avatar-container").click()
            await page.get_by_text("Sign out").click()
            try:
               await page.get_by_role("button", name="Discard and exit").click(timeout=6000)
            except PlaywrightTimeoutError:
               print("Discard and Exit dialog.") 
               pass           
            await expect(page.get_by_role("heading", name="You have signed out.")).to_be_visible(timeout=60000)
            self.logger.info(f"Successfully Signed Out")
          except:
            await exception_handling(f"Failed to Sign Out", user)
            raise




