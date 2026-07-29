import os
import time
import signal
import subprocess
import multiprocessing
import model
from config import get_config

PID_FILE = "queuectl_workers.pid"
shutdown_requested = False


def signal_handler(signum, frame):
    global shutdown_requested
    shutdown_requested = True


def worker_loop(config, worker_name):
    # Ensure shutdown signals are caught
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    print(f"[{worker_name}] Ready and waiting for jobs...")

    while not shutdown_requested:
        # 1. Zombie Sweep Phase
        pending_zombies, dead_zombies = model.recover_zombie_jobs()

        for job in pending_zombies:
            print(
                f"[{worker_name}] ZOMBIE RECOVERED: Job '{job['id']}' timed out. Reset to pending. (Attempt {job['attempts']}/{job['max_retries']})"
            )

        for z_id in dead_zombies:
            print(
                f"[{worker_name}] ZOMBIE KILLED: Job '{z_id}' timed out and reached max retries. Moved to DLQ (Dead)."
            )

        # 2. Claim Phase
        job = model.claim_atomic_job()

        if not job:
            time.sleep(1)  # Sleep if queue is empty
            continue

        print(
            f"[{worker_name}] CLAIMED: Job '{job['id']}' is under process by {worker_name}..."
        )

        # 3. Execution Phase
        result = subprocess.run(
            job["command"], shell=True, capture_output=True, text=True
        )

        # 4. Result Handling Phase
        if result.returncode == 0:
            model.mark_job_completed(job["id"])

            # Safely grab the captured output (ignoring empty strings)
            output = (result.stdout or "").strip()

            print(f"[{worker_name}] SUCCESS: Job '{job['id']}' completed.")
            if output:
                print(f"[{worker_name}] OUTPUT: {output}")
        else:
            # Safely grab the error message
            error_log = (
                (result.stderr or "").strip()
                or (result.stdout or "").strip()
                or "Failed without output"
            )
            attempts_now = job["attempts"] + 1

            print(
                f"[{worker_name}] FAILED: Job '{job['id']}' failed. Error: {error_log}"
            )

            if attempts_now >= job["max_retries"]:
                print(
                    f"[{worker_name}] DLQ: Max retries reached ({job['max_retries']}). Job '{job['id']}' moved to dead state."
                )
            else:
                delay = config["backoff_base"] ** attempts_now
                print(
                    f"[{worker_name}] RETRY: Job '{job['id']}' will wait {delay}s before next attempt. (Attempt {attempts_now}/{job['max_retries']})"
                )

            model.mark_job_failed(
                job["id"], job["attempts"], job["max_retries"], config["backoff_base"]
            )

def worker_start(count):
    config = get_config()
    processes = []

    # Save the main process ID for the status command
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    print(f"Starting {count} workers. Press Ctrl+C to stop gracefully.")

    try:
        for i in range(count):
            # 1. Create the worker name here
            worker_name = f"Worker-{i+1}"

            # 2. Pass both config AND worker_name in the args tuple
            p = multiprocessing.Process(target=worker_loop, args=(config, worker_name))
            p.start()
            processes.append(p)

        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("\nGracefully shutting down workers...")
        for p in processes:
            p.join()
    finally:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)


def worker_stop():
    if not os.path.exists(PID_FILE):
        print("No active workers found.")
        return

    with open(PID_FILE, "r") as f:
        pid = int(f.read().strip())

    try:
        os.kill(pid, signal.SIGTERM)
        print("Sent termination signal to workers.")
    except (ProcessLookupError, OSError):
        print("Worker process not found or access denied. Cleaning up PID file.")
        os.remove(PID_FILE)
