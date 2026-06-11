# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
import json
from typing import Any, Dict, Optional

# Create a named logger for this module
logger = logging.getLogger(__name__)
class Framework:
    @staticmethod
    def safe_json_loads(val):
        """
        Safely load a JSON string as a dictionary. Returns an empty dict if input is None, 'None', or invalid JSON.
        """
        if not val or val == "None":
            return {}
        try:
            loaded = json.loads(val)
            return loaded if isinstance(loaded, dict) else {}
        except Exception as e:
            logging.warning(f"Could not parse JSON for value: {val}. Error: {e}")
            return {}
    def __init__(self, name, version):
        self.name = name
        self.version = version

    def get_name(self):
        return self.name

    def get_version(self):
        return self.version
    
    @staticmethod
    def get_value_with_priority(
        key: str,
        overrides: Optional[Dict[str, Any]],
        definition: Optional[Dict[str, Any]],
        defaults: Optional[Dict[str, Any]]
    ) -> Any:
        """
        Helper function to determine the value of a key based on priority:
        1. Overrides
        2. Workload definition
        3. Framework defaults
        """
        logging.debug(f"Checking for {key} in workload overrides, workload definition, and framework defaults.")
        overrides = overrides or {}
        definition = definition or {}
        defaults = defaults or {}

        logging.debug(f"Overrides: {overrides.get(key)}")
        logging.debug(f"Definition: {definition.get(key)}")
        logging.debug(f"Defaults: {defaults.get(key)}")
        
        if overrides.get(key) is not None:
            logging.debug(f"Using {key} from workload overrides: {overrides.get(key)}")
            return overrides.get(key)
        elif definition.get(key) is not None:
            logging.debug(f"Using {key} from workload definition: {definition.get(key)}")
            return definition.get(key)
        else:
            logging.debug(f"Using {key} from framework defaults: {defaults.get(key)}")
            return defaults.get(key)
