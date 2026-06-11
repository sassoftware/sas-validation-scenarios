# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import traceback
from locust_plugins.users.playwright import PlaywrightUser

# Handles the exception for each of the events in the main locustfile
async def exception_handling(message: str, user):
    # Print out the message you want when an exception occurred
    print(message)
    # Print out the user account
    print(f"username: {user} encountered the following error: {message}")
    # Print out the exception stack
    print(traceback.format_exc())
    # Save the trace file if enabled
     
