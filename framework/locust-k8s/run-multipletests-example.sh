# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

kubectl -n testing apply -f sasstudio-cr.yaml
LOCUSTRESOURCELIST=$( kubectl -n testing get locusttests.locust.io,pod 2>/dev/null );
echo "kubectl -n testing get locusttests.locust.io,pod"; echo "$LOCUSTRESOURCELIST"
kubectl wait --for=condition=complete job/sas-studio-test-worker --timeout=1h -n testing
sleep 10s
MMM1=$(kubectl -n testing get pods | grep master | awk '{print $1}')
kubectl cp -n testing testing/$MMM1:/home/locust/stats.csv_stats.csv logs/sasstudio.csv
kubectl -n testing delete -f sasstudio-cr.yaml
sleep 10s


kubectl -n testing apply -f modelstudio-cr.yaml
LOCUSTRESOURCELIST=$( kubectl -n testing get locusttests.locust.io,pod 2>/dev/null );
echo "kubectl -n testing get locusttests.locust.io,pod"; echo "$LOCUSTRESOURCELIST"
kubectl wait --for=condition=complete job/model-studio-test-worker --timeout=1h -n testing
sleep 10s
MMM1=$(kubectl -n testing get pods | grep master | awk '{print $1}')
kubectl cp -n testing testing/$MMM1:/home/locust/stats.csv_stats.csv logs/modelstudio.csv
kubectl -n testing delete -f modelstudio-cr.yaml
