import json
import os

CONFIG_PATH = "queuectl.json"


def get_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {"max_retries": 3, "backoff_base": 2}


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)
