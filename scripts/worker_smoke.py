"""Probe only the side-effect-free worker; durable job verification is Phase 2."""

import argparse
import time
from typing import Any

from app.core.config import get_settings

WORKER = "actiondesk@worker"


def observe_noop(client: Any, timeout: float = 15) -> None:
    replies = client.control.enable_events(destination=[WORKER], reply=True, timeout=3)
    if not any(reply.get(WORKER, {}).get("ok") for reply in replies or []):
        raise SystemExit("Worker did not acknowledge task-event activation")
    try:
        result: Any = client.signature("actiondesk.noop")
        task_id = result.freeze().id
        with client.connection() as connection:
            receiver = client.events.Receiver(connection, handlers={})
            observed: list[bool] = []

            def receive(event: dict[str, object]) -> None:
                if event.get("uuid") == task_id and event.get("type") == "task-succeeded":
                    observed.append(True)
                    receiver.should_stop = True

            receiver.handlers = {"*": receive}
            # Kombu creates a consumer connection clone. Drain the yielded connection,
            # rather than the producer connection used to construct the receiver.
            with receiver.consumer_context() as (consumer_connection, _, _):
                deadline = time.monotonic() + timeout
                result.apply_async()
                while not observed and time.monotonic() < deadline:
                    try:
                        consumer_connection.drain_events(timeout=1)
                    except TimeoutError:
                        pass
            if not observed:
                raise SystemExit("No-op task success was not observed")
    finally:
        # Phase 0 defaults to task events off; probes should not leave them enabled.
        client.control.disable_events(destination=[WORKER])


def main() -> None:
    from celery import Celery

    parser = argparse.ArgumentParser()
    parser.add_argument("--ping-only", action="store_true")
    args = parser.parse_args()
    client: Any = Celery("probe", broker=get_settings().redis_url)
    replies = client.control.inspect(destination=[WORKER], timeout=3).ping()
    if not replies or replies.get(WORKER) != {"ok": "pong"}:
        raise SystemExit("Worker ping failed")
    if not args.ping_only:
        observe_noop(client)
    print("No-op worker probe passed")


if __name__ == "__main__":
    main()
