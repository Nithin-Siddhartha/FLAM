import json
import model
import config

def enqueue_cmd(args):
    cfg = config.get_config()
    try:
        job = json.loads(args.job_json)
    except json.JSONDecodeError:
        print("Error: Invalid JSON format.")
        return

    success = model.insert_job(job['id'], job['command'], cfg['max_retries'])
    if success:
        print(f"Enqueued job {job['id']}")
    else:
        print("Error: Job ID already exists.")

def status_cmd(args):
    rows = model.get_status_counts()
    print("--- Queue Status ---")
    for row in rows:
        print(f"{row['state']}: {row['count']}")
