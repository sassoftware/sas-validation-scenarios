#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


dirname=`dirname "$0"`
thispath=`cd "$dirname" ; pwd `


userFile="$1"
newfile=run.sh
envfile=".env"

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
       password=$pw
       mkdir $username
       cd $username
       mkdir logs
       cd $thispath
       cp -R scenarios/scenario_name/ $username/
       chmod 777 *
       echo xvfb-run locust -f /mnt/locust/scenario_name/testcase --host=https://hostname --iterations=1 --csv stats.csv >> "$username/$newfile"
       echo username=$username >> "$username/$envfile" 
       echo password=$password >> "$username/$envfile"      
       chmod 777 $username/$newfile
     fi
done < "$userFile"

 else

   echo "NOTE: No user file passed, Please pass in a user file."
fi
