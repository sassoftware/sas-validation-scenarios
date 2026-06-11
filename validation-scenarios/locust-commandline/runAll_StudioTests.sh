#!/bin/bash
# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


#  Convenience wrapper script to just create jobs, not the other tasks of run.sh

scriptStartTimestamp=`date +%Y%m%d%H%M%S%N`

dirname=`dirname "$0"`
thispath=`cd "$dirname" ; pwd `

viyaurl="$1"

if [[ "$viyaurl" = "" ]]
then
   echo "ERROR: the viyaurl  must be passed."
   exit 127
fi

locust -H $viyaurl -u 1 --processes 1 --iteration=1 -f scenarios/st_runsleep01.py --only-summary --csv results/st_runsleep01 --headless
locust -H $viyaurl -u 1 --processes 1 --iteration=1 -f scenarios/st_runsleep02.py --only-summary --csv results/st_runsleep02 --headless
locust -H $viyaurl -u 1 --processes 1 --iteration=1 -f scenarios/st_queryflow.py --only-summary --csv results/st_queryflow --headless
locust -H $viyaurl -u 1 --processes 1 --iteration=1 -f scenarios/st_analystoptimizeflow.py --only-summary --csv results/st_analystoptimizeflow --headless
locust -H $viyaurl -u 1 --processes 1 --iteration=1 -f scenarios/st_40nodesflow.py --only-summary --csv results/st_40nodesflow --headless

