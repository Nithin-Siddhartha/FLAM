import os
import time
import signal
import subprocess
import multiprocessing
import model
from config import get_config

PID_FILE = "queuectl_workers.pid"
shutdown_requested = False

def worker_start(count):
    config = get_config()
    processes = []

    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    print(f"Starting {count} workers. Press Ctrl+C to stop gracefully.")

    try:
        for _ in range(count):
            p = multiprocessing.Process(target=worker_loop, args=(config,))
            p.start()
            processes.append(p)

        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("\nShutting down workers...")
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
