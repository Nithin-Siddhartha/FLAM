#!/usr/bin/env python3
import argparse
import connection
import cli
import workers


def main():
    # Initialize the DB file on startup
    connection.init_db()

    parser = argparse.ArgumentParser(description="QueueCTL - Background Job Queue")
    subparsers = parser.add_subparsers(dest="command")

    # Enqueue
    enq_p = subparsers.add_parser("enqueue")
    enq_p.add_argument("job_json", type=str, help="JSON string of the job")

    # Worker Start & Stop
    worker_p = subparsers.add_parser("worker")
    w_sub = worker_p.add_subparsers(dest="worker_cmd")
    w_start = w_sub.add_parser("start")
    w_start.add_argument("count_word", choices=["count"])
    w_start.add_argument("count", type=int)
    w_stop = w_sub.add_parser("stop")

    # Status
    subparsers.add_parser("status")

    # List
    list_p = subparsers.add_parser("list")
    list_p.add_argument("--state", required=True)
    list_p.add_argument("--json", action="store_true")

    # DLQ List & Retry
    dlq_p = subparsers.add_parser("dlq")
    dlq_sub = dlq_p.add_subparsers(dest="dlq_cmd")
    dlq_sub.add_parser("list")
    dlq_retry_p = dlq_sub.add_parser("retry")
    dlq_retry_p.add_argument("id")

    # Config Set
    conf_p = subparsers.add_parser("config")
    conf_sub = conf_p.add_subparsers(dest="config_cmd")
    c_set = conf_sub.add_parser("set")
    c_set.add_argument("key")
    c_set.add_argument("value")

    # Delete Command
    del_p = subparsers.add_parser("delete")
    del_p.add_argument("id", help="The ID of the job to delete")

    args = parser.parse_args()

    # Routing logic
    if args.command == "enqueue":
        cli.enqueue_cmd(args)
    elif args.command == "worker":
        if args.worker_cmd == "start":
            workers.worker_start(args.count)
        elif args.worker_cmd == "stop":
            workers.worker_stop()
    elif args.command == "status":
        cli.status_cmd(args)
    elif args.command == "list":
        cli.list_cmd(args)
    elif args.command == "dlq":
        if args.dlq_cmd == "list":
            cli.dlq_list_cmd(args)
        elif args.dlq_cmd == "retry":
            cli.dlq_retry_cmd(args)
    elif args.command == "config":
        if args.config_cmd == "set":
            cli.config_set_cmd(args)
    elif args.command == "delete":
        cli.delete_cmd(args)


if __name__ == "__main__":
    main()
