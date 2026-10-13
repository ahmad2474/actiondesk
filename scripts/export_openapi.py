import argparse
import json
from pathlib import Path

from app.main import app

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    content = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if args.stdout:
        print(content, end="")
    else:
        output = Path("packages/contracts/openapi.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content)
