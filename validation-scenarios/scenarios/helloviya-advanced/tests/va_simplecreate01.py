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

class va_simplecreate01(PlaywrightUser):

    logger = logging.getLogger(__name__)
    multiplier = 1
    TIMEOUT_SHORT = 20000
    TIMEOUT_LONG =  60000

    @task
    @pw
    async def test_va_simplecreate01 (self, page: PageWithRetry):

      browser = self.browser
      context = self.browser_context
      page.set_default_timeout(timeout=self.TIMEOUT_LONG)
      if len(usernames) == 0:
          self.logger.info(f"No more users in the list, exiting as success")
          exit(0)
        
      user_ray = usernames.pop(random.randrange(len(usernames)))
      user = user_ray[0]
      password = user_ray[1]


      async with event(self, "01: Starting New simpleReport tests"):
        try:  
          self.logger.info(f"Authenticating to SASLogon")
          await ldap_auth(page, user, password)
          self.logger.info(f"Authentication Successful")
        except:
          await exception_handling("Failed to Authenticate", user)
          raise

      async with event(self, "02: Navigating to SAS Visual Analytics"):
          self.logger.info(f"Navigating to SAS Visual Analytics")
          await page.goto("/SASVisualAnalytics" , timeout=60000)
          timestamp = random.randint(1000, 9999)

      async with event(self, "03: Create New Report And Add Data"):
        try:
          self.logger.info(f"Start: Creating New Report and Adding Data")
          time.sleep(5)
          await expect(page.get_by_text("Explore and Visualize", exact=True)).to_be_visible(timeout=30000)
          #await expect(page.locator('[aria-label="SAS Content"]')).to_be_visible()
          await page.get_by_test_id("newReportFromHome").click()
          await expect(page.get_by_test_id("dataPane")).to_be_visible()
          await page.get_by_text("Select to add data").click()
          await expect(page.get_by_text("Name")).to_be_visible()
          await page.locator('[placeholder="Search all data"]').fill("CLASS")
          self.logger.info(f"Searching for CLASS data")
          await page.get_by_label("Start search").click( )
          await page.wait_for_timeout(3_000)
          await page.get_by_test_id("row-0-checkbox").click()
          await page.get_by_role("button", name="Add", exact=True).click()
          await expect(page.get_by_text("Editing")).to_be_visible()
          await expect(page.get_by_text("Report 1")).to_be_visible()
          await expect(page.get_by_test_id("appLayout-data-tabItem").locator("use")).to_be_visible()
          self.logger.info(f"Finished Creating New Report and Adding Data")
        except:
            await exception_handling("Failed to Create New Report and Adding Data", user)
            raise

      async with event(self, "04: Saving the New report"):
        try:
          self.logger.info(f"Start: Saving MyVA_Report Report")
          await page.get_by_test_id("appMenuButton-button").click(  )
          await page.get_by_test_id("appMenu-saveAs-text").click( )
          await page.get_by_label("Folder tree").get_by_text("My Folder").dblclick()
          await page.get_by_label("Name:", exact=True).click(  )
          # create file name
          timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
          filename = f"MyVA_Report_{timestamp}"
          await page.get_by_label("Name:", exact=True).fill(filename)
          await page.get_by_role("button", name="Save", exact=True).click( )
          await expect(page.get_by_text("Saving")).to_be_hidden(  )
          await expect(page.get_by_test_id("appMenuButton-button")).to_be_visible( )
          self.logger.info(f"Finished Saving MyVA_Report Report")
        except:
          await exception_handling("Failed to Save MyVA_Report Report", user)
          raise

      async with event(self, "05: Closing New VA Report"):
        try:
          self.logger.info(f"Start: Closing New VA Report")
          await page.get_by_test_id("appMenuButton-button").click( )
          await page.get_by_test_id("appMenu-closeReport-text").click(  )
          self.logger.info(f"Finished Closing New VA Report")
        except:
          await exception_handling("Failed to Close New VA Report", user)
          raise     

      async with event(self, "06: Logging Out"):
        try: 
          self.logger.info(f"Start: Logging Out of VA")  
          await page.get_by_test_id("VAAppRootBanner-options").click()
          await page.get_by_test_id("VAAppRootBanner-signout-text").click()
          await expect(page.get_by_role("heading", name="You have signed out.")).to_be_visible()
          self.logger.info(f"Finished Logging Out of VA")
          self.logger.info(f"TESTS FINISHED")
        except:
          await exception_handling("Failed to Log Out of VA", user)
          raise  



