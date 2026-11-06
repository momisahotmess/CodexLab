import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlencode

from app.main import app


class TaskSearchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.data_file = Path(directory) / "tasks.json"
        self.enterContext(patch("app.store.DATA_FILE", self.data_file))
        tasks = []
        for task_id, title, description, status in [
            (1, "Launch plan", "", "open"),
            (2, "Write notes", "Capture LAUNCH decisions", "done"),
            (3, "Review budget", "", "open"),
            (4, "Archive report", "", "done"),
        ]:
            tasks.append({
                "id": task_id,
                "title": title,
                "description": description,
                "status": status,
                "priority": "medium",
                "created_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-02T00:00:00Z" if status == "done" else None,
            })
        self.data_file.write_text(json.dumps(tasks), encoding="utf-8")

    async def request(self, path, method="GET", **query):
        # Send an HTTP request directly to the ASGI app without a test client dependency.
        events = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(event):
            events.append(event)

        await app({
            "type": "http",
            "method": method,
            "path": path,
            "query_string": urlencode(query).encode(),
            "headers": [],
        }, receive, send)
        self.assertEqual(events[0]["status"], 200)
        return json.loads(b"".join(event.get("body", b"") for event in events))

    async def test_task_list(self):
        cases = [
            ("title", {"q": "plan"}, [1]),
            ("description", {"q": "decisions"}, [2]),
            ("lowercase", {"q": "launch"}, [1, 2]),
            ("uppercase", {"q": "LAUNCH"}, [1, 2]),
            ("partial word", {"q": "aunc"}, [1, 2]),
            ("no match", {"q": "missing"}, []),
            ("search and open", {"q": "launch", "status": "open"}, [1]),
            ("search and done", {"q": "launch", "status": "done"}, [2]),
            ("no filters", {}, [1, 2, 3, 4]),
            ("open only", {"status": "open"}, [1, 3]),
            ("done only", {"status": "done"}, [2, 4]),
        ]
        for label, query, expected in cases:
            with self.subTest(label=label):
                tasks = await self.request("/tasks", **query)
                self.assertEqual([task["id"] for task in tasks], expected)

    async def test_completion_persists(self):
        completed = await self.request("/tasks/1/complete", method="POST")
        self.assertEqual(completed["status"], "done")
        self.assertIsNotNone(completed["completed_at"])
        self.assertEqual(await self.request("/tasks/1"), completed)
        done_matches = await self.request("/tasks", status="done", q="launch")
        self.assertEqual([task["id"] for task in done_matches], [1, 2])
