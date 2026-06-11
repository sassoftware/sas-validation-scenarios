# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

###!DEV_TEST
from pathlib import Path
import sys, os
import asyncio
import logging
import time
import csv
import yaml
from playwright.async_api import async_playwright, expect

# Get absolute path to the target folder
common_path = os.path.abspath(os.path.join(__file__, '..', '..', '..', '..', 'framework', 'execution', 'common'))

# Add to Python import path
sys.path.insert(0, common_path)

# from events import *
from auth import *
from exception import *

###$!DEV_TEST

###!FRAMEWORK_TEST
# from events import *
# from auth import *
# from exception import *
# from locust_plugins.users.playwright import PlaywrightUser, pw, event, PageWithRetry
# import traceback
# import asyncio
# import logging
# from locust import runners
###$!FRAMEWORK_TEST

###!DEV_TEST
class AlertVerificationError(Exception):
        pass

class Test_Class:
    def __init__(self):

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
###$!DEV_TEST
    
###!FRAMEWORK_TEST
# class Test_Class(PlaywrightUser): 
#     logger = logging.getLogger(__name__)
#     multiplier = 1
###$!FRAMEWORK_TEST


###!DEV_CONVERT_PARAMETERS
############################################################################################################################
##################################### EDIT THIS PART OF THE TEST ###########################################################
############################################################################################################################
        
        ####################################################
        self.globalconfig_name = "global-config-simple.yaml"
        ####################################################

        ################## PARAMETERS ######################
        self.SLOW_MO = 50

        self.TIMEOUT_SHORT = 10000
        self.TIMEOUT_LONG = 60000
        ####################################################

############################################################################################################################
############################################################################################################################
############################################################################################################################
###$!DEV_CONVERT_PARAMETERS  
                
        ###!DEV_TEST
        # Load usernames and passwords from users.csv file
        csv_path = os.path.abspath(os.path.join(__file__, '..', '..', '..', 'users.csv'))
        self.usernames = []

        try:
            with open(csv_path, mode='r', newline='', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                for row in reader:
                    if len(row) >= 2:
                        self.usernames.append((row[0].strip(), row[1].strip()))
        except FileNotFoundError:
            self.logger.error(f"User CSV file not found at path: {csv_path}")
        except Exception as e:
            self.logger.error(f"Error reading user CSV: {e}")

        # Read hostname value from global-config.yaml file
        config_path = os.path.abspath(os.path.join(__file__, '..', '..', '..', self.globalconfig_name))
        self.base_url = None

        try:
            with open(config_path, 'r', encoding='utf-8') as ymlfile:
                config = yaml.safe_load(ymlfile)
                self.base_url = config.get("global-config", {}).get("hostname")
                if not self.base_url:
                    self.logger.warning(f"'hostname' not found in {config_path}")
        except FileNotFoundError:
            self.logger.error(f"YAML config file not found at path: {config_path}")
        except Exception as e:
            self.logger.error(f"Error reading YAML config: {e}")
        ###$!DEV_TEST

###!FRAMEWORK_TEST
#     @task
#     @pw
#        
#     async def test_new_modelstudio (self, page: PageWithRetry):
#         # If we need the browser and context
#         browser = self.browser
#         context = self.browser_context
#         page.set_default_timeout(timeout=self.TIMEOUT_LONG)
#         if len(usernames) == 0:
#             self.logger.info(f"No more users in the list, exiting as success")
#             exit(0)
#         else:
#             self.logger.info(f"User list: {usernames}")
        
#         user_ray = usernames.pop(random.randrange(len(usernames)))
#         user = user_ray[0]
#         password = user_ray[1]
###$!FRAMEWORK_TEST  


###!DEV_CONVERT_EVENTS
############################################################################################################################
##################################### EDIT THIS PART OF THE TEST ###########################################################
############################################################################################################################

    async def login(self, page, user, password):
        self.logger.info("01: Navigate to SAS Visual Investigator")
        try:  
            self.logger.info(f"Authenticating to SASLogon")
            await ldap_auth(page, user, password)
            self.logger.info(f"Authentication Successful")
        except:
            await exception_handling("Failed to Authenticate", user)
            raise
        
    async def logout(self, page):
        try:  
            self.logger.info(f"Starting to Logout")
            await page.get_by_role("link", name="Sign out").click()
            await expect(page.get_by_role("heading", name="You have signed out.")).to_be_visible()
            self.logger.info(f"Finished Logging out")
            self.logger.info(f"TESTS FINISHED")
        except:
            await exception_handling("Failed to Logout", self)
            raise

############################################################################################################################
############################################################################################################################
############################################################################################################################
###$!DEV_CONVERT_EVENTS

    ###!DEV_TEST
    async def run_test(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False, slow_mo=self.SLOW_MO, args=["--window-size=1920,1080"])

            if not self.usernames:
                self.logger.info("No users in the list, exiting")
                return

            if not self.base_url:
                self.logger.error("No base_url loaded from config; aborting test")
                return

            # Define the video directory path using pathlib
            folder_name = os.path.basename(os.path.dirname(os.path.abspath(__file__)))

            #video_dir = Path("validation-scenarios", "scenarios-development", folder_name, "videos")
            video_dir = Path("videos")

            for user, password in self.usernames:
                self.logger.info("-" * 80)
                self.logger.info(f"Starting test for user: {user}")

                # New session for each user
                context = await browser.new_context(
                    base_url = self.base_url,
                    ignore_https_errors=True,
                    record_video_dir=str(video_dir),
                    record_video_size={"width": 1280, "height": 720}
                )


                page = await context.new_page()
                page.set_default_timeout(timeout=self.TIMEOUT_LONG)

                try:
                    await self.login(page, user, password)
                    await self.logout(page)
                    
                except Exception as e:
                    self.logger.error(f"Test failed for user {user}: {e}")
                finally:
                    await context.close()

            await browser.close()


if __name__ == "__main__":
    runner = Test_Class()
    asyncio.run(runner.run_test())

###$!DEV_TEST
