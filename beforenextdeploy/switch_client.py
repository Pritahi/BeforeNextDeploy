"""Minimal Switch 0.31 custom-agent protocol: SSE down, HTTP operations up.

Based on the public Switch agent protocol and the Shield-for-Data walkthrough;
see README references. Runtime credentials are never printed or sent to models.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Iterator
import requests


@dataclass
class Event:
    kind: str
    data: dict
    event_id: str | None


def parse_events(lines: Iterator[str]) -> Iterator[Event]:
    kind, data, event_id = "message", [], None
    for line in lines:
        if line is None:
            continue
        line = line.rstrip("\r")
        if not line:
            if data:
                try:
                    obj = json.loads("\n".join(data))
                except json.JSONDecodeError:
                    obj = {}
                yield Event(kind, obj, event_id)
            kind, data, event_id = "message", [], None
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "event": kind = value
        elif field == "id": event_id = value
        elif field == "data": data.append(value)


class SwitchClient:
    def __init__(self, base: str, agent_id: str, key: str):
        self.base, self.agent_id = base.rstrip("/"), agent_id
        self.headers = {"Authorization": f"Bearer {key}"}

    @staticmethod
    def register(base: str, token: str, name: str) -> tuple[str, str]:
        payload = {"name": name, "description": "Evidence-based pre-deployment review teammate",
            "connector_type": "custom-python",
            "integration_profile": {"connection_model": "always_on", "message_exchange": True,
               "pre_invocation_mediation": [], "post_invocation_mediation": [], "event_reporting": [],
               "command_capabilities": {"reset": "unsupported", "compact": "unsupported", "interrupt": "unsupported"}},
            "tools": [], "models": [], "metadata": {"project": "beforenextdeploy"}, "overwrite": False}
        r = requests.post(f"{base.rstrip('/')}/agents", json=payload,
                          headers={"Authorization": f"Bearer {token}"}, timeout=30)
        r.raise_for_status()
        return r.json()["id"], r.json()["api_key"]

    def events(self, connection_id: str, room: str | None = None, last_id: str | None = None):
        params = {"connection_id": connection_id, "scope": "single" if room else "all",
                  "filter": "addressed" if room else "all", "start_from": "head",
                  "client": "beforenextdeploy", "client_version": "0.1.0"}
        if room: params["rooms"] = room
        headers = {**self.headers, "Accept": "text/event-stream"}
        if last_id: headers["Last-Event-ID"] = last_id
        r = requests.get(f"{self.base}/agents/{self.agent_id}/events", headers=headers,
                         params=params, stream=True, timeout=(10, 65))
        r.raise_for_status()
        try:
            yield from parse_events(r.iter_lines(decode_unicode=True))
        finally:
            r.close()

    def beat(self, connection_id: str, generation):
        # Protocol 9 fences a heartbeat to the generation in connection_state.
        payload = {"connection_id": connection_id}
        if generation is not None: payload["generation"] = generation
        r = requests.post(f"{self.base}/agents/{self.agent_id}/connection/beat", headers=self.headers,
                          json=payload, timeout=10)
        r.raise_for_status()
        return r.json()

    def op(self, name: str, args: dict, connection_id: str):
        r = requests.post(f"{self.base}/agents/{self.agent_id}/ops/{name}",
                          headers={**self.headers, "X-Switch-Connection-Id": connection_id},
                          json=args, timeout=45)
        r.raise_for_status()
        return r.json().get("result") or {}

    def post(self, room: str, message: str):
        r = requests.post(f"{self.base}/agents/{self.agent_id}/message", headers=self.headers,
                          json={"room_id": room, "content": message}, timeout=25)
        r.raise_for_status()
