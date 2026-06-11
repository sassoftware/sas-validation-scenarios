# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

userFile="$1"

if [[ -f "$userFile" ]]
then

   while IFS=":" read -r userid pw
   do
     # skip comments
     if [[ "$userid" != "#"* ]]
     then
        #
        # the line must contain a request to add a user or a group to be processed
        #
       username=$userid
       rm -r -f $username
       rm -r -f results
     fi
done < "$userFile"

 else

   echo "NOTE: No user file passed, Please pass in a user file."
fi
