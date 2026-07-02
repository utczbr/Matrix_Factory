#!/usr/bin/env python3
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="Render factory.jcm from template.")
    parser.add_argument("--run-id", type=int, default=0, help="The RUN_ID to inject.")
    args = parser.parse_args()

    try:
        with open("factory.jcm.template", "r") as f:
            template = f.read()
    except FileNotFoundError:
        print("Error: factory.jcm.template not found.", file=sys.stderr)
        sys.exit(1)

    rendered = template.replace("{{RUN_ID}}", str(args.run_id))

    with open("factory.jcm", "w") as f:
        f.write(rendered)
        
    print(f"Rendered factory.jcm with RUN_ID={args.run_id}")

if __name__ == "__main__":
    main()
