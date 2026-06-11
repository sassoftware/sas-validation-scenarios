# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

userFile="$1"

dirname=`dirname "$0"`
thispath=`cd "$dirname" ; pwd `


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
       volume=$dirname\$username
       cd $username
       vol="$thispath/$username"
       echo $vol
       echo $PWD
       echo $username 
       nohup docker run -w /mnt/locust/ -v "$PWD":/mnt/locust playtest:latest -f /mnt/locust/scenario_name/testcase --host=https://hostname --iterations=1 --csv stats.csv  --headless &
       cd ..
     fi
done < "$userFile"

 else

   echo "NOTE: No user file passed, Please pass in a user file."
fi
