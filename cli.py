import json
import os
import model
import config
from workers import PID_FILE


def enqueue_cmd(args):
    cfg = config.get_config()
    try:
        job = json.loads(args.job_json)
    except json.JSONDecodeError:
        print("Error: Invalid JSON format.")
        return

    success = model.insert_job(job["id"], job["command"], cfg["max_retries"])
    if success:
        print(f"Enqueued job {job['id']}")
    else:
        print("Error: Job ID already exists.")


def status_cmd(args):
    rows = model.get_status_counts()
    print("--- Queue Status ---")
    for row in rows:
        print(f"{row['state']}: {row['count']}")

    active = "Yes" if os.path.exists(PID_FILE) else "No"
    print(f"Active Workers Foreground Process Running: {active}")


def list_cmd(args):
    jobs = model.get_jobs_by_state(args.state)
    if args.json:
        print(json.dumps(jobs, indent=2))
    else:
        for j in jobs:
            print(j)


def dlq_list_cmd(args):
    args.state = "dead"
    args.json = True
    list_cmd(args)


def dlq_retry_cmd(args):
    success = model.reset_dlq_job(args.id)
    if success:
        print(f"Re-enqueued DLQ job {args.id}")
    else:
        print("Job not found in DLQ.")


def config_set_cmd(args):
    cfg = config.get_config()
    if args.key == "max-retries":
        cfg["max_retries"] = int(args.value)
    elif args.key == "backoff-base":
        cfg["backoff_base"] = int(args.value)
    else:
        print("Invalid config key. Use max-retries or backoff-base.")
        return
    config.save_config(cfg)
    print(f"Config updated: {args.key} = {args.value}")


def delete_cmd(args):
    model.delete_job(args.id)
    print(f"Job '{args.id}' has been permanently deleted.")
