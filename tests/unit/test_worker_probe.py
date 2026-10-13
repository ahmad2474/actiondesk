from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts.worker_smoke import WORKER, observe_noop


def probe_client() -> tuple[Any, Any, Any]:
    client, producer, consumer, receiver = [MagicMock() for _ in range(4)]
    client.control.enable_events.return_value = [{WORKER: {"ok": "task events enabled"}}]
    client.connection.return_value.__enter__.return_value = producer
    client.events.Receiver.return_value = receiver
    receiver.consumer_context.return_value.__enter__.return_value = (consumer, None, [])
    producer.drain_events.side_effect = AssertionError("Producer cannot deliver consumer events")
    client.signature.return_value.freeze.return_value.id = "probe-id"
    return client, receiver, consumer


def test_noop_probe_observes_subscribed_consumer_and_restores_events() -> None:
    client, receiver, consumer = probe_client()

    def deliver(timeout: int) -> None:
        client.signature.return_value.apply_async.assert_called_once()
        receiver.handlers["*"]({"uuid": "unrelated-id", "type": "task-succeeded"})
        receiver.handlers["*"]({"uuid": "probe-id", "type": "task-succeeded"})

    consumer.drain_events.side_effect = deliver
    observe_noop(client)
    consumer.drain_events.assert_called_once_with(timeout=1)
    client.control.disable_events.assert_called_once_with(destination=[WORKER])


def test_noop_probe_fails_if_events_are_not_acknowledged() -> None:
    client, _, _ = probe_client()
    client.control.enable_events.return_value = []
    with pytest.raises(SystemExit, match="acknowledge"):
        observe_noop(client)
    client.signature.assert_not_called()


def test_noop_probe_does_not_report_success_without_matching_event() -> None:
    client, _, _ = probe_client()
    with pytest.raises(SystemExit, match="success was not observed"):
        observe_noop(client, timeout=0)
    client.control.disable_events.assert_called_once_with(destination=[WORKER])
