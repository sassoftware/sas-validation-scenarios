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
       sudo mkdir results
       sudo chmod 777 results
       #cp -R $username/logs/responsetime.csv results/"$username"_rt.csv 
       #cp -R $username/nohup.out results/"$username"_output.log
       cp -R $username/stats.csv_stats.csv results/"$username"_stats.csv
     fi
done < "$userFile"

 else

   echo "NOTE: No user file passed, Please pass in a user file."
fi

cat results/*.csv > results/combined.csv
