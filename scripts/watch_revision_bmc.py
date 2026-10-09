#!/usr/bin/env python3
"""Bounded scheduler driver using the separate revision submission ledger."""
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path


def main():
    start = time.monotonic()
    while time.monotonic() - start < 8 * 3600:
        # Port only our pending initial A800 requests; retain task identities.
        queue = subprocess.check_output(['squeue','--noheader','--array','--user','zihanhe25',
                                         '--format=%i|%P|%q|%T'],text=True)
        entries = [line.split('|') for line in queue.splitlines()]
        room = 8 - sum(q == '4gpus' for _,p,q,s in entries)
        ledger = [json.loads(line) for line in Path('artifacts/revision_bmc/submissions.jsonl').read_text().splitlines()]
        ours = {r['job_id'] for r in ledger if r['resource']=='gpu'}
        for job,partition,qos,state in entries:
            if room <= 0: break
            if job.split('_')[0] not in ours or partition!='gpua800' or state!='PENDING': continue
            command = ['scontrol','update','JobId='+job,'Partition=gpu3090','QOS=4gpus',
                       'Gres=gpu:gtx3090:1','NumCPUs=2','CPUsPerTask=2','MinCPUsNode=2',
                       'MinMemoryNode=8192','TimeLimit=01:00:00']
            result = subprocess.run(command,capture_output=True,text=True)
            with Path('artifacts/revision_bmc/scheduler_migrations.jsonl').open('a') as handle:
                handle.write(json.dumps({'command':command,'returncode':result.returncode,
                                        'message':result.stderr,'reason':'Available uniform RTX 3090 revision hardware'})+'\n')
            if result.returncode==0: room-=1
        total = {}
        for resource, names in (("gpu3090", ("revision_training", "revision_evaluation")),
                                ("cpu", ("revision_transfer",))):
            paths = [Path("configs/revision_bmc")/(n+".json") for n in names]
            counts = {s: 0 for s in ("complete", "failed", "running", "not_started")}
            for path in paths:
                manifest = json.loads(path.read_text())
                for task in manifest["tasks"]:
                    record = Path(manifest["job_records"])/(task["id"]+".json")
                    status = json.loads(record.read_text())["status"] if record.exists() else "not_started"
                    counts[status] += 1
            total[resource] = counts
            if counts['failed']:
                raise RuntimeError("Failed revision task: inspect before restarting")
            subprocess.run([sys.executable, "scripts/submit_ready_v2.py", "--manifests", *map(str,paths),
                            "--resource", resource, "--ledger", "artifacts/revision_bmc/submissions.jsonl",
                            "--submit"], check=True)
        state = {"updated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "counts": total}
        target = Path("artifacts/revision_bmc/queue_status.json")
        target.with_suffix('.tmp').write_text(json.dumps(state,indent=2)+"\n")
        target.with_suffix('.tmp').replace(target)
        print(json.dumps(state), flush=True)
        if all(sum(c.values()) == c['complete'] for c in total.values()):
            return
        time.sleep(25)
    raise TimeoutError("Bounded revision driver expired")


if __name__ == '__main__':
    main()
