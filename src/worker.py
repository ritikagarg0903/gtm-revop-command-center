"""Run once from a scheduler, or continuously with --watch. Inputs are trusted adapter snapshots."""
import argparse
import json
import time
import pandas as pd
from src.workflow import Workflow

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--records', required=True, help='CSV with prospect identity, validation flags and total_score')
    parser.add_argument('--reps', required=True)
    parser.add_argument('--events', help='JSON array with event_id, prospect_id, type, occurred_at')
    parser.add_argument('--db', required=True, help='Durable SQLite database path shared with the dashboard')
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    while True:
        events = []
        if args.events:
            with open(args.events, encoding='utf-8') as handle:
                events = json.load(handle)
        worker = Workflow(args.db)
        try:
            worker.run(pd.read_csv(args.records), pd.read_csv(args.reps), events)
        finally:
            worker.close()
        if not args.watch:
            break
        time.sleep(60)

if __name__ == '__main__': main()
