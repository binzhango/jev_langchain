"""First-run setup and the combined frontend/API service used by start.sh."""
import argparse
from getpass import getpass
import os
from pathlib import Path
import socket
import sys

from dotenv import dotenv_values, set_key

from .config import Settings


def configure(root: Path, interactive: bool) -> None:
    destination = root / ".env"
    if destination.exists():
        return
    template = root / ".env.example"
    defaults = dotenv_values(template)
    values = {}
    if interactive:
        print("First-time setup. Press Enter to accept a default.")
        print("New values are saved in the private, Git-ignored .env file.")
        for key, label in (("LOCAL_LLM_BASE_URL", "Local model server URL"),
                           ("LOCAL_LLM_MODEL", "Exact loaded model ID")):
            if not os.getenv(key):
                default = defaults[key]
                values[key] = input(f"{label} [{default}]: ").strip() or default
        if not os.getenv("LOCAL_LLM_API_KEY"):
            values["LOCAL_LLM_API_KEY"] = getpass("Local server API key (hidden; Enter if no authentication): ") or "lm-studio"
        if not (os.getenv("JEV_TOKEN") or os.getenv("TYPESAFE_API_KEY")):
            token = getpass("Jev token (hidden; Enter to use scripted walkthroughs only): ").strip()
            if token:
                values["JEV_TOKEN"] = token
    # Exclusive creation prevents overwriting a file created during the prompts.
    with open(destination, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as handle:
        handle.write(template.read_text())
    for key, value in values.items():
        set_key(destination, key, value)
    print("Created .env. Existing environment variables take precedence.")


def main():
    parser = argparse.ArgumentParser(description="Start the dashboard and API together.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    # Check before creating a runner, which holds the data-directory lease.
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", args.port))
    except OSError:
        parser.exit(1, f"Port {args.port} is unavailable. If the app is already running, open http://127.0.0.1:{args.port}. Otherwise stop the service using that port and try again.\n")
    root = Path(__file__).resolve().parents[2]
    try:
        configure(root, sys.stdin.isatty())
    except (EOFError, KeyboardInterrupt):
        parser.exit(1, "\nSetup cancelled. Run bash start.sh to try again.\n")
    settings = Settings.from_env()
    if not settings.jev_token:
        print("No Jev token configured. Choose Scripted walkthrough in the dashboard; add JEV_TOKEN to .env for live runs.", flush=True)
    print(f"\nOpen http://127.0.0.1:{args.port}\nThis one service hosts the dashboard and API. Press Ctrl+C to stop both.\n", flush=True)
    import uvicorn
    from .api import create_app
    try:
        app = create_app(settings)
    except ValueError as error:
        parser.exit(1, settings.safe_error(error) + "\nStop the other Jev Lab server before starting this one.\n")
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
