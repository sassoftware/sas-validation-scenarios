# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

#--------------------------------------------------#
# Index (search for the following strings to jump to key points in this module):
#   class EnhancedPlaywrightUser
#       def __init__
#       def __setattr__
#       def printMyInfo
#       def getMyItemFromListParam
#       def context
#       def nowdttm
#       def print
#       def uniqueuserstr
#       def pageAndContextAreHealthy
#       def pwtraceStart
#       def pwtraceStop
#       def interIterationDelay
#   def perf
#   async def txn
#--------------------------------------------------#
# https://stackoverflow.com/questions/39740632/python-type-hinting-without-cyclic-imports
from __future__ import annotations  # must be first line in file
from typing import TYPE_CHECKING    # always False at runtime so the import won't be evaluated (and cause a cyclic import), but type-checking tools will evaluate the contents of that block
if TYPE_CHECKING:
    from locust.env import Environment
    from locust_plugins.users.playwright import PageWithRetry
#--------------------------------------------------#
DEBUGGING = True
def _debugprintepu(x):
    """ standardized format for printing output messages within this module, can add context as needed. """
    if DEBUGGING:
        print(f"COMMON_EPU.PY\t\t{x}")
#--------------------------------------------------#
import threading, uuid, pprint, random, os, time, re, asyncio, inspect, secrets
from playwright.async_api import Locator, Frame
from locust_plugins.users.playwright import PlaywrightUser
from playwright.async_api._generated import Page
from locust.runners import Runner, LocalRunner, WorkerRunner, MasterRunner

# This module defines a locust event listener method that will -> "Fired when a request in completed." <- to write the individual transaction response time to the WorkerRunner log
#import common_getrawresults

# This module contains some event listener methods that need to be defined globally so I import that here, also used in @perf decorator to get_vuserid
#import common_vuserid

### Not needed at this time but may need later:
# from common_inspect import get_parent_file_name, get_parent_method_name, getfnstack, getfullinspectstack
# import inspect
# from playwright.async_api import expect

#--------------------------------------------------#
# Extend PlaywrightUser class with member variables & methods we find useful in our testing
class EnhancedPlaywrightUser(PlaywrightUser):
    abstract = True
    """ set this explicitly here because it does not seem to be inherited as expected from PlaywrightUser """

    # Global member variables that you can modify in any instance of this class you create, for example to disable PWTRACE collection once a test is solid.
    PWTRACE:bool = True
    """ (boolean) True or False do you want to create playwright trace files; one per failure and one for the most recent successful iteration """
    TXNTIMEOUT:float = 30000
    """ TXNTIMEOUT in ms (30000 -> 30 seconds), default 5000 -> 5s is too short """
    INTERACTION_TIMEOUT:float = 30000
    """ Time in milliseconds to wait for the vuser to interact with a locator.
    For example: page.get_by_role("button", name="Log In").click( timeout=INTERACTION_TIMEOUT )
    Default 60s (60000ms) is too long when we use test-assertions to end transaction timers.
    https://playwright.dev/docs/locators """
    INTER_ITERATION_DELAY_AVG:float = 2
    """ Average delay in seconds between iterations """
    INTER_ITERATION_DELAY_FUZ:float = 0.5
    """ INTER_ITERATION_DELAY will be range from (1-FUZ)*AVG to (1+FUZ)*AVG """
    ABORT_ITERATION_WHEN_TXN_FAILS:bool = True
    """
    By default (False) the PlaywrightUser locust User class will continue running a task after a txn/event has failed.
    Set this to True to cause the vuser who has failed a txn to stop running a task, drop into except block, and proceed to the next iteration.
    """
    END_OF_TEST_PAUSE_SEC:float = 1
    """
    await asyncio.sleep(END_OF_TEST_PAUSE_SEC) in on_stop at end of test. (only useful for mode = k8spods)
    Useful for giving time to download final pwtrace file at end of test before pod exits,
    or giving a buffer at end of test (prior to job termination hard stop) where pod remains up
    for debug purposes.
    """
    RESULTSTEMPDIR:str = "/tmp/py-pw-loc-temp/"
    """ 
    Directory accessible in the shell where the locust command is running. For example:
    - localcontainers: local wsl ubuntu filesystem 
    - k8spods: in the container
    - k8sjob: in the container
    """


    # (varying) Contextual metadata, changes during test execution
    currenttask:str|None                = None
    """ Dynamic string holding the name of the locust task currently being executed by this vuser. """
    iteration:int                       = -1
    """ Dynamic int holding the iteration number (e.g. 0, 1, 2, ...) currently being executed by this vuser. """
    currenttxn:str|None                 = None
    """ Dynamic string holding the name of the locust task currently being executed by this vuser. """
    iteration_start_timestamp:str       = str(int(time.time()*1000000))
    """ Dynamic string (e.g. '1717691234123456') holding the current iteration start time in microseconds (millionths of a second) since 1Jan1970 (i.e. the 'Unix epoch'). Mainly for internal use like OTEL header, filename substr, etc. """

    # (static) Contexutal metadata, set once at the start (in __init__ constructor for the locust User class)
    my_runner_client_id:str|None        = None
    """ "client_id" string of the the locust worker process where this vuser thread is running. Used internally as a 'return mailing address' when sending messages to the MasterRunner process. """
    vuser_uuid:str                      = str(uuid.uuid4())
    """ Static uuid string assigned to each vuser (aka virtual user, aka locust user). Has a one to one relationship with user.startuporderid """
    currentscript:str|None              = None
    """ Static string (e.g. "script01.py") holding the name of the script (aka module) where the locust User class (of this vuser) is defined. """
    currentclass:str|None               = None
    """ Static string (e.g. "Script01Persona") holding the name of the locust User class assigned to this virtual user (aka locust user, aka vuser) """
    startuporderid:int|None             = None
    """ Static sequence integer (e.g. 0, 1, 2, 3, ...) assigned to each Locust User (aka vuser) in the order in which they request a vuserid from the MasterRunner|LocalRunner. """
    vuserid:int                         = -99
    """ Static sequence integer (e.g. 0, 1, 2, ...) assigned to each Locust User (aka vuser) that is unique within their assigned locust User class. Default value -99 represents 'undefined vuserid' """
    myrandomseed:int|None               = None
    """ Static seed for pseudorandom number generator with default=user.vuserid (i.e. seed = 0, 1, 2, ...) so it is unique within a Locust User class """

    # Convience member variables & other internal variables
    BASEURL:str                         = ""
    """ Convenience member variable to hold the BASEURL in use by this vuser, making it easier to compartmentalize your script into methods (for readability and for maintainability) by passing in only the 'user' object as an arg. """
    locBaseFrame:Frame|Page|None        = None
    """ Convenience member variable used in common_viya module """
    locAppMenu:Locator|None             = None
    """ Convenience member variable used in common_viya module """
    locAppOptions:Locator|None          = None
    """ Convenience member variable used in common_viya module """
    iterationAllTxnPassed:bool|None     = None
    """ Internal boolean used when creating pwtrace file (e.g. successful-iteration, failed txn, or failed iteration where txn failed but ABORT_ITERATION_WHEN_TXN_FAILS=False ) """
    uniqueLogonUsername:str|None        = None
    """ Convenience member variable to hold the logon userid currently in use by this vuser, making it easier to compartmentalize your script into methods (for readability and for maintainability) by passing in only the 'user' object as an arg. """

    # internal variables
    perf_on_start_completed = False
    """ If there is an exception in the @perf decorator (for on_start) or if exception in on_start() method, then this will remain False.
    Becomes True once the wrapper HEADER has completed and on_start() has completed, then can get set back to False if there is an exception in the FOOTER.
    Then this var is used in @perf decorator (for 'tasks') to short circuit (fail fast) by raising an exception,
    instead of trying to run tasks with improperly initialized vuser.
    
    This is because I do not know how to have a PlaywrightUser permanently exit (e.g. if there are not enough elements in the LOGONUSERIDS array for its vuserid).
    Thus far, attempts at having a vuser exit or stop itself have resulted with the LocustRunner/LocustMaster process re-starting the user apparently because
    the --run-time or --iterations have not yet been reached, as if it assumes the user exited or crashed accidentally. 
    """

    #--------------------------------------------------#
    #--------------------------------------------------#
    #--------------------------------------------------#
    def __init__(self, parent):
        _debugprintepu(f"__init__ > TOP")
        _debugprintepu(f"__init__ > pid({os.getpid()})\ttid({threading.get_ident()})")

        _debugprintepu(f"__init__ > 'self.__dict__'='{self.__dict__}'") # self.environment does not exist yet, so lets see what does
        _debugprintepu(f"__init__ > 'type(parent)'='{type(parent)}'")

        # Ensure RESULTSTEMPDIR exists
        if not os.path.exists(self.RESULTSTEMPDIR):
            os.makedirs(self.RESULTSTEMPDIR, exist_ok=True)

        parentenv:Environment = parent # worker process / main thread
        if DEBUGGING:
            _debugprintepu(f"parentenv.__dict__:")
            pprint.pprint(parentenv.__dict__)

        parentrunner:LocalRunner|WorkerRunner = parentenv.runner
        if not isinstance(parentenv.runner, LocalRunner) and not isinstance(parentenv.runner, WorkerRunner):
            print(f"\nWARNING: Unexpected situation -> 'type(self.environment.runner)'='{type(parentenv.runner)}' is not in (LocalRunner, WorkerRunner)\n")

        self.my_runner_client_id = parentrunner.client_id

        self.printMyInfo("__init__")
        _debugprintepu(f"__init__ > BOT 1")

        # NOTE: The parent constructor copies this instance into "multiplier=1" sub-users (same pid different threads)
        #   so I run the following line AFTER setting all the variables common across the "multiplier=?" locust users.
        super().__init__(parent)
        _debugprintepu(f"__init__ > BOT 2")


    #--------------------------------------------------#
    #--------------------------------------------------#
    #--------------------------------------------------#
    def __setattr__(self, name, value):
        # Disallow modification of specific attributes once they have been set to an initial default value
        lockedValueList = ('multiplier') # optionally lock this from being set
        lockedValueList = ()
        if name in lockedValueList and value is not None:
            # _debugprintepu(f"__setattr__ > preventing setting locked attribute name({name}) to value({value})")
            raise AttributeError(f"Cannot modify locked attribute '{name}' (value={value})")
        else:
            # Allow attribute creation & modification
            # _debugprintepu(f"__setattr__ > setting name({name}) to value({value})")
            super().__setattr__(name, value)


    #--------------------------------------------------#
    #--------------------------------------------------#
    #--------------------------------------------------#
    def printMyInfo(self, printprefix:str):
        print(f"{printprefix} > #----~----~----~----~----~----~----~----~----~----~----~----~----~----~----~")
        print(f"{printprefix} >                                                                             ")
        print(f"{printprefix} >                                self({self})                                 ")
        print(f"{printprefix} >                            id(self)({id(self)})                             ")
        print(f"{printprefix} >                                 pid({os.getpid()})                          ")
        print(f"{printprefix} >                                 tid({threading.get_ident()})                ")
        print(f"{printprefix} >                         thread name({threading.current_thread().name})      ")
        print(f"{printprefix} >                          self.tasks({getattr(self, 'tasks', None)})         ")
        try:
            print(f"{printprefix} >                    self.environment({self.environment})                     ")
            print(f"{printprefix} >           self.environment.__dict__({self.environment.__dict__})            ")
        except:
            print(f"{printprefix} >                    self.environment(... attribute does not exist ...)   ")
        print(f"{printprefix} >                                                                             ")
        print(f"{printprefix} >                        self.PWTRACE({self.PWTRACE})                         ")
        print(f"{printprefix} >                     self.TXNTIMEOUT({self.TXNTIMEOUT})                      ")
        print(f"{printprefix} >            self.INTERACTION_TIMEOUT({self.INTERACTION_TIMEOUT})             ")
        print(f"{printprefix} >      self.INTER_ITERATION_DELAY_AVG({self.INTER_ITERATION_DELAY_AVG})       ")
        print(f"{printprefix} >      self.INTER_ITERATION_DELAY_FUZ({self.INTER_ITERATION_DELAY_FUZ})       ")
        print(f"{printprefix} > self.ABORT_ITERATION_WHEN_TXN_FAILS({self.ABORT_ITERATION_WHEN_TXN_FAILS})  ")
        print(f"{printprefix} >          self.END_OF_TEST_PAUSE_SEC({self.END_OF_TEST_PAUSE_SEC})           ")
        print(f"{printprefix} >                 self.RESULTSTEMPDIR({self.RESULTSTEMPDIR})                  ")
        print(f"{printprefix} >                                                                             ")
        print(f"{printprefix} >            self.my_runner_client_id({self.my_runner_client_id})             ")
        print(f"{printprefix} >                     self.vuser_uuid({self.vuser_uuid})                      ")
        print(f"{printprefix} >                                                                             ")
        print(f"{printprefix} >                  self.currentscript({self.currentscript})                   ")
        print(f"{printprefix} >                   self.currentclass({self.currentclass})                    ")
        print(f"{printprefix} >                 self.startuporderid({self.startuporderid})                  ")
        print(f"{printprefix} >                        self.vuserid({self.vuserid})                         ")
        print(f"{printprefix} >                   self.myrandomseed({self.myrandomseed})                    ")
        print(f"{printprefix} >            self.uniqueLogonUsername({self.uniqueLogonUsername})             ")
        print(f"{printprefix} >                                                                             ")
        print(f"{printprefix} >                      self.iteration({self.iteration})                       ")
        print(f"{printprefix} >      self.iteration_start_timestamp({self.iteration_start_timestamp})       ")
        print(f"{printprefix} >                    self.currenttask({self.currenttask})                     ")
        print(f"{printprefix} >                     self.currenttxn({self.currenttxn})                      ")
        print(f"{printprefix} >                                                                             ")
        # print(f"{printprefix} >             parent.runner.client_id({parent.runner.client_id})              ") # this is consistent value printed from __init__ or from a task
        # print(f"{printprefix} >                     self.idontexist({self.idontexist})                      ") # e.g. AttributeError: 'ViyaViewer' object has no attribute 'idontexist'
        print(f"{printprefix} >                                                                             ")
        print(f"{printprefix} > #----~----~----~----~----~----~----~----~----~----~----~----~----~----~----~")


    #--------------------------------------------------#
    #--------------------------------------------------#
    #--------------------------------------------------#
    def getMyItemFromListParam(self, listparameter:tuple|list, vuserid:int=-99, randomize=False):
        """
        Safe & concise helper method to get "this vuser's" item from a list variable defined in the script's parameter file.
        - Safe because validation & error handling: e.g. if not enough items are in the list, then I will raise an IndexException with message clarifying that you need more items in the list parameter to support more vusers.<br>
        - Concise because it is one line in your script to get/set a parameter with all the validation & error handling in the method instead of in the script (improves script readability and maintainability by encapsulating redundant code).<br>

        <br>

        :param self: Since this is a member method of a class (in this case the EnhancedPlaywrightUser class), the first parameter is automatically reserved for Self@EnhancedPlaywrightUser, which is "passed in" like arg1.getMyItemFromListParam(arg2,arg3) instead of as an actual arg within the parenthesis.
        :param listparameter: A list of strings, ints, lists of strings, etc... potentially defined in *parameters*.py, or in the script itself.
        :param vuserid: Lookup index into the listparameter list. Default value is self.vuserid (which is distinct across locust users assigned to a given locust User class (aka persona)). Also, self.startup
        :return listparameter[vuserid] | exception:

        <br>

        Example 1: Use lookup index "self.<b><u>startuporderid</u></b>" to ensure each locust User (regardless of their 'locust User class') gets a unique logon id:

            LOGONUSERIDS = [ "rdtest0000", "rdtest0001", "rdtest0002", "rdtest0003", "rdtest0004", ]
            # ...
            myUniqueLogonId = self.getMyItemFromListParam(LOGONUSERIDS, self.startuporderid)

        <br>

        Example 2: Use lookup index "self.<b><u>vuserid</u></b>" to ensure users get their unique logon id from a particular list of ids pre-configured with persona based roles/permissions:

            LOGONUSERIDS_CasualAdmin         = [ "rdtest0000" ] # can support up to 1 locust User running this persona
            LOGONUSERIDS_CasualDataScientist = [ "rdtest0100", "rdtest0101", "rdtest0102", ] # supports up to 3 locust users
            LOGONUSERIDS_CasualAnalyst       = [ "rdtest0200", "rdtest0201", "rdtest0202", "rdtest0203", "rdtest0204", ] # supports up to 5 locust users

            class CasualAdmin(EnhancedPlaywrightUser):
                @pw
                @perf
                async def on_start(self:EnhancedPlaywrightUser, page: Page):
                    self.uniqueLogonUsername = self.getMyItemFromListParam(LOGONUSERIDS_CasualAdmin, self.vuserid)
            # ...
            class CasualDataScientist(EnhancedPlaywrightUser):
                @pw
                @perf
                async def on_start(self:EnhancedPlaywrightUser, page: Page):
                    self.uniqueLogonUsername = self.getMyItemFromListParam(LOGONUSERIDS_CasualDataScientist, self.vuserid)
            # ...
            class CasualAnalyst(EnhancedPlaywrightUser):
                @pw
                @perf
                async def on_start(self:EnhancedPlaywrightUser, page: Page):
                    self.uniqueLogonUsername = self.getMyItemFromListParam(LOGONUSERIDS_CasualAnalyst, self.vuserid)
            # ...

        """
        _debugprintepu(f"getMyItemFromListParam > TOP")
        if vuserid == -99:
            vuserid = self.vuserid  # Default to self.vuserid if no value is provided
        try:
            _debugprintepu(f"getMyItemFromListParam( self={self}, listparameter={listparameter}, vuserid={vuserid} )")
            _debugprintepu(f"getMyItemFromListParam > BOT")
            if randomize:
                return secrets.choice(listparameter)
            return listparameter[vuserid]
        except TypeError as eee:
            mymsg = f"TypeError: 'vuserid'='{vuserid}' not suitable as list lookup (e.g. listparameter[{vuserid}])."
        except IndexError as eee:
            mymsg = f"IndexError: Not enough values in list 'len(listparameter)'='{len(listparameter)}' for vuser with 'vuserid'='{vuserid}' to get their own distinct value."
        except Exception as eee:
            mymsg = f"Exception: 'type(eee).__name__'='{type(eee).__name__}' occurred, eee={eee}"
        self.print(f"getMyItemFromListParam > {mymsg}")
        _debugprintepu(f"getMyItemFromListParam > BOT")
        raise Exception (mymsg)

    #--------------------------------------------------#
    #--------------------------------------------------#
    #--------------------------------------------------#
    def context(self) -> dict:
        """
        Member method of PlaywrightUser sub-class used in the 'txn' (aka 'event') method to get contextual metadata attached to each txn timing.<br>
        Used when getting raw results (aka individual txn response times) in 'request' event listener method to write to log txn time along with useful context info.<br>
        """
        mycontext = super().context() # get the parent context first
        mycontext["startuporderid"]       = self.startuporderid
        mycontext["vuser_uuid"]           = self.vuser_uuid
        mycontext["my_runner_client_id"]  = self.my_runner_client_id
        mycontext["currentscript"]        = self.currentscript
        mycontext["currentclass"]         = self.currentclass
        mycontext["vuserid"]              = self.vuserid
        mycontext["iteration"]            = self.iteration
        mycontext["currenttask"]          = self.currenttask
        mycontext["currenttxn"]           = self.currenttxn
        mycontext["RESULTSTEMPDIR"]       = self.RESULTSTEMPDIR
        return mycontext

    #--------------------------------------------------#
    #--------------------------------------------------#
    #--------------------------------------------------#
    def nowdttm(self) -> str:
        """ Consistently formatted datetime/timestamp string like "2024-10-15_161150.311" for log messages and file names like pwtrace*.zip """
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d_%H%M%S.%f")[:-3]  # 2024-10-15_161150.311

    #--------------------------------------------------#
    #--------------------------------------------------#
    #--------------------------------------------------#
    def print(self, value: str = ""): # formerly "pprint", now self.print(f"hello world with self context")
        """ Use this member method to print log messages with line prefixed by standardized contextual info, improving readability of logs
        and usable by status.sh script to get & print a listing of what each vuser is currently doing. Use this method as follows in any
        task or on_start/on_stop method:

            self.print(f"hello")
        """
        print(f"print_with_perf_context TOP")
        print(f"{self.nowdttm()}\t{self.uniqueuserstr()}\t{value}")
        print(f"print_with_perf_context BOT")

    #--------------------------------------------------#
    #--------------------------------------------------#
    #--------------------------------------------------#
    def uniqueuserstr(self) -> str:
        """
        f"{STARTUPID}.{VUSERUUID}.{WORKERID}.{USERCLASS}.{VUSERID}._.{ITERATION}.{TASK}.{TXN}"\n
        * STARTUPID = 0,1,2,... generated by the MasterRunner for a vuser (aka virtual user) when they request a 'vuserid'; indicates order in which vuserids were requested
        * VUSERUUID = uuid generated by a vuser during 'on_start > userinit()' to help the MasterRunner keep track of vuserids; unique for each vuser
        * WORKERID = client_id of the WorkerRunner a vuser is running on
        * USERCLASS = locust User class (aka script) assigned to the vuser
        * VUSERID = 0,1,2,... unique id within a given USERCLASS; can be used by a vuser to obtain a unique logon userid from a list (aka array) defined in the script's parameter file
        * ITERATION = 0,1,2,... number of times a vuser has completed one full iteration of its USERCLASS
        * TASK = the current task (within a USERCLASS) being run; at the start of each "iteration" the vuser randomly selects a task (from its USERCLASS) to run
        * TXN = name of the current transaction (aka "action", aka "locust event") that a vuser is running
        """
        # All of these EnhancedPlaywrightUser member variables are declared with default value of None, so I can simplify to return the string directly instead of using a series of try/except blocks to confirm variables are defined

        # static for the test run duration
        STARTUPID   = str(self.startuporderid)
        WORKERID    = str(self.my_runner_client_id)
        SCRIPT      = str(self.currentscript)
        USERCLASS   = str(self.currentclass)
        VUSERUUID   = str(self.vuser_uuid)
        VUSERID     = str(f"vuser_{self.vuserid}")
        # can change
        ITERATION   = str(f"iter_{self.iteration}")
        TASK        = str(self.currenttask)
        TXN         = str(self.currenttxn)
        # output options
        # NOTE: this is parsed from worker logs in status.sh to get live status of each vuser                               # syncpoint001
        # CONCISECONTEXT  = f"{USERCLASS}.{VUSERID}._.{ITERATION}.{TASK}.{TXN}"                                             # syncpoint001
        # FULLCONTEXT     = f"{STARTUPID}.{WORKERID}.{SCRIPT}.{USERCLASS}.{VUSERUUID}.{VUSERID}._.{ITERATION}.{TASK}.{TXN}" # syncpoint001
        FULLCONTEXT     = f"{STARTUPID}.{VUSERUUID}.{WORKERID}.{USERCLASS}.{VUSERID}._.{ITERATION}.{TASK}.{TXN}"            # syncpoint001
        return FULLCONTEXT
    # Last line of class EnhancedPlaywrightUser

    #--------------------------------------------------#
    #--------------------------------------------------#
    #--------------------------------------------------#
    def pageAndContextAreHealthy(self, debugprefix:str="") -> bool:
        goodtogo = True
        if hasattr(self,"page") and self.page is not None:
            _debugprintepu(f"{debugprefix} INFO: Page exists and is not None...")
            # Page
            if self.page.is_closed():
                goodtogo = False
                _debugprintepu(f"{debugprefix} WARNING: Unable to stop tracing because > Page has been closed (self.page.is_closed() == True)")
            else:
                _debugprintepu(f"{debugprefix} INFO: Page is not closed, diving deeper to look at self.page.context")
                if hasattr(self.page,"context") and self.page.context is not None:
                    _debugprintepu(f"{debugprefix} INFO: Context exists and is not None...")
                    # Context
                    if hasattr(self.page.context,"_impl_obj") and hasattr(self.page.context._impl_obj,"_disposed"):
                        if self.page.context._impl_obj._disposed:
                            goodtogo = False
                            _debugprintepu(f"{debugprefix} WARNING: Unable to stop tracing because > Context has been closed (self.page.context._impl_obj._disposed == True)")
                        else:
                            _debugprintepu(f"{debugprefix} INFO: Context looks good (self.page.context._impl_obj._disposed is not True)")
                    else:
                        _debugprintepu(f"{debugprefix} INFO: Context looks good (self.page.context._impl_obj._disposed not defined)")
                else:
                    goodtogo = False
                    _debugprintepu(f"{debugprefix} WARNING: Unable to stop tracing because > self.page.context attribute doesnt exist or equals None")
        else:
            goodtogo = False
            _debugprintepu(f"{debugprefix} WARNING: Unable to stop tracing because > self.page attribute doesnt exist or equals None")
        return goodtogo



    #--------------------------------------------------#
    #--------------------------------------------------#
    #--------------------------------------------------#
    async def pwtraceStart(self):
        debugprefix = f"pwtraceStart(self={self}) >"
        _debugprintepu(f"{debugprefix} TOP")
        try:
            if self.PWTRACE:
                _debugprintepu(f"{debugprefix} Entering self.page.context.tracing.start")
                await self.page.context.tracing.start(screenshots=True, snapshots=True, sources=True)
                _debugprintepu(f"{debugprefix} Exiting  self.page.context.tracing.start")
        except Exception as eee:
            _debugprintepu(f"{debugprefix} IGNORING Exception eee({eee})")
        _debugprintepu(f"{debugprefix} BOT")

    #--------------------------------------------------#
    #--------------------------------------------------#
    #--------------------------------------------------#
    async def pwtraceStop(self):
        debugprefix = f"pwtraceStop(self={self}) >"
        _debugprintepu(f"{debugprefix} TOP")
        try:
            if self.PWTRACE:

                # Part 1: get a pwtracefilename (one per "successful-iteration", & one per failed txn/iteration)
                _debugprintepu(f"{debugprefix} self.PWTRACE == True")
                if self.iterationAllTxnPassed:
                    pwtracefilename = f"{self.RESULTSTEMPDIR}pwtrace.successful-iteration.{self.currentclass}.{self.currenttask}.zip"
                else:
                    # NOTE: if self.currenttxn = None in the pwtrace file name it may be due to ABORT_ITERATION_WHEN_TXN_FAILS = False, and at least one failed txn during the iteration
                    pwtracefilename = f"{self.RESULTSTEMPDIR}pwtrace.s{self.startuporderid}.{self.currentclass}.{self.currenttask}.{self.currenttxn}.v{self.vuserid}.i{self.iteration}.zip"
                temptracefname=f"{self.RESULTSTEMPDIR}write_temp_trace_{self.vuser_uuid}.zip"
                _debugprintepu(f"{debugprefix} temptracefname({temptracefname}) & pwtracefilename({pwtracefilename})")

                # Part 2: If page & context are still available, then stop tracing and write pwtrace file out
                if self.pageAndContextAreHealthy(debugprefix=f"{debugprefix} "):
                    with threading.Lock(): # makes this set of lines "atomic" so that once started they(i.e. LocustWorker) will not be interrupted/killed by the LocustRunner or LocustMaster like when stopping the locust test.
                        _debugprintepu(f"{debugprefix} await self.page.context.tracing.stop( path={temptracefname} )")
                        await self.page.context.tracing.stop( path=temptracefname )
                        if os.path.exists(pwtracefilename):
                            _debugprintepu(f"{debugprefix} os.remove({pwtracefilename})")
                            os.remove(pwtracefilename)
                        _debugprintepu(f"{debugprefix} os.rename({temptracefname}, {pwtracefilename})")
                        os.rename(temptracefname, pwtracefilename)
                        _debugprintepu(f"{debugprefix} DONE creating pwtracefile({pwtracefilename})")

                _debugprintepu(f"{debugprefix} done with 'pwtracefile stop' section")
                self.currenttxn = None
            else:
                _debugprintepu(f"{debugprefix} self.PWTRACE == False")
        except Exception as eee:
            _debugprintepu(f"{debugprefix} IGNORING Exception eee({eee}) ")
        _debugprintepu(f"{debugprefix} BOT")

    #--------------------------------------------------#
    #--------------------------------------------------#
    #--------------------------------------------------#
    async def interIterationDelay(self):
        debugprefix = f"interIterationDelay(self={self}) >"
        _debugprintepu(f"{debugprefix} TOP")
        try:
            # Only run inter-iteration delay if self has the required attributes
            if hasattr(self, "INTER_ITERATION_DELAY_AVG") and hasattr(self, "INTER_ITERATION_DELAY_FUZ"):
                async with txn(self, "NAV999-InterIterationDelay"):
                    thinkTime_s = random.uniform( (1-self.INTER_ITERATION_DELAY_FUZ)*self.INTER_ITERATION_DELAY_AVG, (1+self.INTER_ITERATION_DELAY_FUZ)*self.INTER_ITERATION_DELAY_AVG )
                    self.print(f"self.INTER_ITERATION_DELAY_AVG({self.INTER_ITERATION_DELAY_AVG}), self.INTER_ITERATION_DELAY_FUZ({self.INTER_ITERATION_DELAY_FUZ}), thinkTime_s({thinkTime_s})")
                    await asyncio.sleep( thinkTime_s ) # I DO want this idle time included in the timer, so I use this instead of await self.page.wait_for_timeout( thinkTime_s*1000 )
        except Exception as eee:
            _debugprintepu(f"{debugprefix} IGNORING Exception eee({eee}) ")
        _debugprintepu(f"{debugprefix} BOT")








#--------------------------------------------------#
#--------------------------------------------------#
#--------------------------------------------------#
def perf(func):
    """
    Decorator (aka "wrapper") for locust-playwright-python "on_start" and "Task" methods to facilitate "pre" and "post" operations for the wrapped method:
    - For "on_start()" it handles one time vuser (aka "Locust User") initilization that cant be handled in the EnhancedPlaywrightUser __init__ constructor such as: requesting a vuserid from the leader (LocalRunner or MasterRunner) if not already obtained via --vuserid cmd line arg.
    - For "@task" methods it handles "taskinit" context refresh such as increment the self.iteration counter, set self.iteration_start_timestamp, update self.currenttask, and reset some self.* variables.
    - For "@task" methods it handles the try/except/finally code required for raising exceptions to locust for inclusion in the results, also handles pwtrace file creation (start in pre, stop in post/finally).
    
    NOTE: Decorator order matters; here is a valid syntax example:

        @pw
        @perf
        async def on_start(self:EnhancedPlaywrightUser, page: Page):
            self.printMyInfo("on_start")
            self.uniqueLogonUsername = self.getMyItemFromListParam(example_parameters.LOGONUSERIDS)

        @task
        @pw
        @perf
        async def SfdPriorityAlertTriagePersona( self:EnhancedPlaywrightUser, page:PageWithRetry ):
            async with txn(self, "NAV001-OpenLoginPage"):
                await ViyaOpenLoginPage(self, BASEURL)
            # ...
    """
    modulename = inspect.stack()[1][1].split("/")[-1]   # /home/zahelm/gitrepos/pypwloc/TEMPLATE_v3/example_locust_user_classes.py
    userclass  = inspect.stack()[1][3]
    wrappedFunctionName = func.__name__ # i.e. on_start or the 'task method name', requires @perf to be the inner most wrapper method
    
    prefix = f"perfdecorator({modulename},{userclass},{wrappedFunctionName}) >"
    _debugprintepu(f"{prefix} TOP (of perf method)")


    async def on_stop_perf_wrapper(self:EnhancedPlaywrightUser, *args, **kwargs):
        print("VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV")
        _debugprintepu(f"{prefix} HEADER > nothing to do... yet...")
        _debugprintepu(f"{prefix}   CORE > Entering {getattr(func, '__name__', '???')}")
        result = await func(self, *args, **kwargs)  # <-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-= decorator-core
        _debugprintepu(f"{prefix}   CORE > Exiting  {getattr(func, '__name__', '???')}")
        _debugprintepu(f"{prefix} FOOTER > nothing to do... yet...")
        print("^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^")
        return result                               # <-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-= decorator-core


    async def on_start_perf_wrapper(self:EnhancedPlaywrightUser, *args, **kwargs):
        print("VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV")
        try:
            self.perf_on_start_completed = False
            _debugprintepu(f"{prefix} HEADER > TOP")
            _debugprintepu(f"{prefix} HEADER > get_vuserid")
            #await common_vuserid.get_vuserid(self)
            _debugprintepu(f"{prefix} HEADER > random.seed( self.myrandomseed = self.vuserid )")
            self.myrandomseed = self.vuserid
            random.seed( self.myrandomseed )
            _debugprintepu(f"{prefix} HEADER > BOT")
        except Exception as eee:
            self.perf_on_start_completed = False
            _debugprintepu(f"{prefix} HEADER > IGNORING Exception eee({eee})")

        _debugprintepu(f"{prefix}   CORE > Entering {getattr(func, '__name__', '???')}")
        result = await func(self, *args, **kwargs)  # <-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-= decorator-core
        self.perf_on_start_completed = True
        _debugprintepu(f"{prefix}   CORE > Exiting  {getattr(func, '__name__', '???')}")

        try:
            _debugprintepu(f"{prefix} FOOTER > nothing to do... yet...")
        except Exception as eee:
            self.perf_on_start_completed = False
            _debugprintepu(f"{prefix} FOOTER > IGNORING Exception eee({eee})")
        print("^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^")
        return result                               # <-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-= decorator-core


    async def task_perf_wrapper(self:EnhancedPlaywrightUser, *args, **kwargs):
        print("VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV")
        _debugprintepu(f"{prefix} HEADER > TOP")
        try:
            if not self.perf_on_start_completed:
                # NOTE: This "short circuit / fail fast" code path is required because I do not know how to have a PlaywrightUser permanently exit (e.g. if there are not enough elements in the LOGONUSERIDS array for its vuserid). Thus far, attempts at having a vuser exit or stop itself have resulted with the LocustRunner/LocustMaster process re-starting the user apparently because the --run-time or --iterations have not yet been reached, as if it assumes the user exited or crashed accidentally.
                msg = f"ERROR: self.perf_on_start_completed=False, which means my internal state is not fully formed, and I will abstain from running tasks. Context:"
                msg = f"{msg} startuporderid({getattr(self,'startuporderid',None)})"
                msg = f"{msg} currentclass({getattr(self,'currentclass',None)})"
                msg = f"{msg} vuserid({getattr(self,'vuserid',None)})"
                msg = f"{msg} currenttask({getattr(func,'__name__',None)})"
                print(msg)
                await self.page.wait_for_timeout(5000) # Avoid rapidly firing this short circuit (fail fast) code path
                raise Exception(msg)
            self.iteration_start_timestamp = str(int(time.time()*1000000))
            self.iteration += 1                 # increment by 1 at the start of task, __init__ value is 0 so first iteration is 1
            self.iterationAllTxnPassed = True   # Assume all is well until proven otherwise
            self.currenttask   = wrappedFunctionName
            self.currenttxn    = None
            # Avoid contamination from previous iteration by resetting self.loc* back to None
            self.locBaseFrame  = None 
            self.locAppMenu    = None
            self.locAppOptions = None
            _debugprintepu(f"{prefix} HEADER > self.currenttask({self.currenttask})")
            _debugprintepu(f"{prefix} HEADER > self.pwtraceStart() > entering")
            await self.pwtraceStart()
            _debugprintepu(f"{prefix} HEADER > self.pwtraceStart() > done")
        except Exception as eee:
            self.iterationAllTxnPassed = False
            _debugprintepu(f"{prefix} HEADER > IGNORING Exception eee({eee})")
        _debugprintepu(f"{prefix} HEADER > BOT")

        core_func_completed_successfully = False
        func_exception_msg = ""
        try:
            _debugprintepu(f"{prefix}   CORE > Entering {getattr(func, '__name__', '???')}")
            result = await func(self, *args, **kwargs)  # <-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-= decorator-core
            _debugprintepu(f"{prefix}   CORE > Exiting  {getattr(func, '__name__', '???')}")
            core_func_completed_successfully = True
        except Exception as eee:
            # hold on to exception until I have attempted the 'pseudo-finally' code
            core_func_completed_successfully = False
            func_exception_msg = eee
            
        _debugprintepu(f"{prefix} FOOTER > TOP")
        try: # 'pseudo-finally'
            _debugprintepu(f"{prefix} FOOTER > Entering self.pwtraceStop()")
            await self.pwtraceStop()
            _debugprintepu(f"{prefix} FOOTER > Exiting  self.pwtraceStop()")
        except Exception as eee:
            func_exception_msg = f"{func_exception_msg}\n{eee}"
            _debugprintepu(f"{prefix} FOOTER > Exception... I have added the msg to func_exception_msg({func_exception_msg})")
        try: # 'pseudo-finally'
            _debugprintepu(f"{prefix} FOOTER > Entering self.interIterationDelay()")
            await self.interIterationDelay()
            _debugprintepu(f"{prefix} FOOTER > Exiting  self.interIterationDelay()")
        except Exception as eee:
            func_exception_msg = f"{func_exception_msg}\n{eee}"
            _debugprintepu(f"{prefix} FOOTER > Exception... I have added the msg to func_exception_msg({func_exception_msg})")
        _debugprintepu(f"{prefix} FOOTER > BOT")

        if func_exception_msg != "":
            # Print the exception messages to log. Two cases possible:
            # 1. core ran fine but one or more 'pseudo-finally' blocks raised an Exception, I will want to see these print() to the log, especially since the txn will not fail since I wont be raising Exception from this wrapper.
            # 2. core returned an Exception, in which case the next conditional will raise that exception to the caller, essentially failing the txn, still useful to see the exception msg in the log at the point which it happened.
            print(f"\nERROR: Exceptions encountered in task_perf_wrapper():\n{func_exception_msg}\n")
        if not core_func_completed_successfully:
            # Now its time to raise the exception if the decorator-core func call returned an Exception
            raise Exception(func_exception_msg)

        print("^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^")
        return result                               # <-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-= decorator-core


    _debugprintepu(f"{prefix} BOT (of perf method... return one of 3 wrapper methods based on wrappedFunctionName({wrappedFunctionName}) being on_start, on_stop, or anything else")
    if wrappedFunctionName == "on_start":
        return on_start_perf_wrapper
    elif wrappedFunctionName == "on_stop":
        return on_stop_perf_wrapper
    else:
        return task_perf_wrapper
    # Last line of "def perf"












#--------------------------------------------------#
#--------------------------------------------------#
#--------------------------------------------------#
# Override "event" method with "txn" method:
#   from locust_plugins.users.playwright import event
#   from locust_plugins.users.playwright import PlaywrightUser
#   from locust.user import User
# Goal is to make some modifications:
# 1. rename to "txn" (i.e "transaction") which is the traditional term used in peformance testing, so script reads like -> async with txn(self, "02-SignIn"):
# 2. exclude failed txn response times from locust summary (which I have reverted now that getrawresults module separates passed from failed txn timings)
# 3. set User/self.currenttxn EPU member var which is used for context(); For example, if a txn fails then I can create a pwtrace file name containing txn name for faster debugging
# 4. rename screenshot png file created by locust on error (disabled for now because ss are typically blank and pwtrace file provides superior info for debugging)
#--------------------------------------------------#
from contextlib import asynccontextmanager
from locust.exception import CatchResponseError
@asynccontextmanager
async def txn( self:EnhancedPlaywrightUser|PlaywrightUser, name="unnamed", request_type="event" ):
    start_time = time.time()
    
    if isinstance(self, EnhancedPlaywrightUser):
        self.currenttxn = name  # <-- auto capture transaction name here for use later as needed (e.g. log messages, trace or screenshot file name)
        self.print(f"txn > TOP")
        # OTEL Header (see https://gitlab.sas.com/sasbbw/playwright-otel)
        await self.page.set_extra_http_headers({
            'step'          : str(self.currenttxn),                             # keys likely should not be changed, but the values could be changed, like for "user" you could use "logonid" instead of "vuserid"
            'user'          : str(f"vuser{self.vuserid}"),                      # all these values must strings
            'script'        : str(f"{self.currentclass}_{self.currenttask}"),   # locust User class + task name is the best identifier here since currentscript might contain multiple User classes which in turn contain 1 or more tasks
            'timestamp'     : str(self.iteration_start_timestamp), 
            'steptimestamp' : str(int(start_time*1000000)), 
        })

    start_perf_counter = time.perf_counter()
    try:
        yield
        self.environment.events.request.fire(
            request_type=request_type,
            name=name,
            start_time=start_time,
            response_time=(time.perf_counter() - start_perf_counter) * 1000,
            response_length=0,
            context={**self.context()},
            url=self.page.url if self.page else None,
            exception=None,
        )
    except Exception as eee:
        if isinstance(self, EnhancedPlaywrightUser):
            self.print(f"txn > failed")
            self.print(f"txn > {type(eee).__name__}: {eee}")
            self.iterationAllTxnPassed = False
        try:
            error = CatchResponseError(re.sub("=======*", "", str(eee)).replace("\n", "").replace(" logs ", " ")[:500])
        except:
            error = eee  # never mind
        if not self.error_screenshot_made:
            self.error_screenshot_made = True  # dont spam screenshots...
            if self.page:  # in ScriptUser runs we have no reference to the page so...
                # await self.page.screenshot( path=f"{self.RESULTSTEMPDIR}screenshot.{self.uniqueuserstr()}.png", full_page=False )
                #NOTE: I am disabling screenshots here since often they are blank or just cause issues
                pass
        self.environment.events.request.fire(
            request_type=request_type,
            name=name,
            start_time=start_time,
            response_time=(time.perf_counter() - start_perf_counter) * 1000, # with "common_getrawresults.py" I can exclude response time of failed txns from main summary but still show how long each took to fail
            # response_time=None, # This will exclude the failed txn response time from the locust summary
            response_length=0,
            url=self.page.url if self.page else None,
            context={**self.context()},
            exception=error,
        )
        if isinstance(self, EnhancedPlaywrightUser):
            if self.ABORT_ITERATION_WHEN_TXN_FAILS:
                # self.currenttxn = None  # txn done because it failed, but I want to retain the currenttxn name so I can put it in the pwtrace file name, I will set it to None after that (in the finally block)
                raise
    await asyncio.sleep(0.1)
    if isinstance(self, EnhancedPlaywrightUser):
        self.print(f"txn > BOT")
        self.currenttxn = None  # txn done, unset this variable
        self.print(f"")         # print another blank msg just to get the pprint context for the status script to show txn=None so you can watch when vusers are in between txns
    # Last line of async def txn



#--------------------------------------------------#
#--------------------------------------------------#
#--------------------------------------------------#

