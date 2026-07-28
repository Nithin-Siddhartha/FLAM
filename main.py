import argparse
import connection
import cli

def main():
    # Initialize the DB file on startup
    connection.init_db()
    
    parser = argparse.ArgumentParser(description="QueueCTL - Background Job Queue")
    subparsers = parser.add_subparsers(dest="command")

    # Enqueue Command
    enq_p = subparsers.add_parser("enqueue")
    enq_p.add_argument("job_json", type=str, help="JSON string of the job")

    # Status Command
    subparsers.add_parser("status")

    args = parser.parse_args()

    # Routing logic
    if args.command == "enqueue": 
        cli.enqueue_cmd(args)
    elif args.command == "status": 
        cli.status_cmd(args)

if __name__ == "__main__":
    main()
