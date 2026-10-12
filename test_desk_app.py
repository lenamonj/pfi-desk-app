"""Tests for the desk app: every endpoint through the test client, with no port, no network, and no key."""
import json

import pytest
from fastapi.testclient import TestClient

import deploykit
import desk_app_main

SNAPSHOT = json.loads(desk_app_main.SNAPSHOT_PATH.read_text(encoding="utf-8"))
# adversarial: four requests for a view; the app must refuse each before anything is looked up
VIEWS = ['Which of these bonds should the desk buy?', "Rank the three issuers' indentures.", 'Where will the 10-year yield be next month?', 'Is Lamar a holding in this portfolio?']
NOT_RECORDED = "As of 2026-10-02, what is the 30 Yr Treasury par yield?"
# a fake key made in pieces, so this file holds no key-like string for a scan to find
FAKE_KEY = "sk-or-" + "FAKE" * 3


def desk(daily_cap=desk_app_main.DAILY_CAP, environ=None):
    """The app on a fake clock, with its log lines kept in a list."""
    lines = []
    wall, clock = deploykit.fake_clock("2026-10-02T14:00:00", 10.0)
    app = desk_app_main.make_app(sink=lines.append, clock=clock, wall=wall, daily_cap=daily_cap,
                                 environ={} if environ is None else environ)
    return TestClient(app), lines


def test_health_states_the_date_and_replay():
    client, _ = desk()
    assert client.get("/health").json() == {"status": "ok", "version": deploykit.VERSION, "as_of": "2026-10-02",
                                            "mode": "replay"}


def test_every_response_carries_the_as_of_date():
    client, _ = desk()
    replies = [client.get("/health"), client.get("/brief"), client.get("/checks"), client.get("/nowhere"),
               client.post("/ask", json={"question": NOT_RECORDED}), client.post("/ask", json={})]
    assert [r.status_code for r in replies] == [200, 200, 200, 404, 404, 422]
    assert all(r.headers["X-Desk-As-Of"] == "2026-10-02" for r in replies)


def test_brief_and_checks_are_the_snapshot():
    client, _ = desk()
    assert client.get("/brief").json() == {"as_of": "2026-10-02", "mode": "replay", "brief": SNAPSHOT["brief"]}
    assert client.get("/checks").json()["checks"] == SNAPSHOT["checks"]


def test_recorded_question_returns_its_saved_answer():
    client, _ = desk()
    for question, answer in SNAPSHOT["answers"].items():
        reply = client.post("/ask", json={"question": question}).json()
        assert reply == {"question": question, "answer": answer, "refused": False, "as_of": "2026-10-02"}


def test_unrecorded_question_is_404_never_a_guess():
    client, _ = desk()
    reply = client.post("/ask", json={"question": NOT_RECORDED})
    assert reply.status_code == 404 and reply.json()["detail"] == deploykit.NOT_SAVED


@pytest.mark.parametrize("question", VIEWS)
def test_request_for_a_view_is_refused(question):
    client, _ = desk()
    reply = client.post("/ask", json={"question": question})
    assert reply.status_code == 200 and reply.headers["X-Desk-Refused"] == "true"
    assert reply.json() == {"question": question, "answer": deploykit.REFUSAL_LINE, "refused": True,
                            "as_of": "2026-10-02"}


def test_real_documents_and_synthetic_book_never_meet():
    client, _ = desk()
    separation = [row for row in client.get("/checks").json()["checks"] if row["check"] == "separation"]
    assert separation and all(row["passed"] for row in separation)
    portfolio = json.dumps(client.get("/brief").json()["brief"]["portfolio"])
    assert not [name for name in SNAPSHOT["guard"]["real_issuers"] if name in portfolio]


def test_no_key_in_any_response():
    client, _ = desk(environ={"DESK_MODE": "live", "OPENAI_API_KEY": FAKE_KEY})
    texts = [client.get(path).text for path in ("/health", "/brief", "/checks")]
    texts += [client.post("/ask", json={"question": VIEWS[0]}).text]
    assert not any(FAKE_KEY in text for text in texts)
    assert not any(pattern.search(text) for text in texts for pattern in deploykit.KEY_PATTERNS.values())


def test_one_log_line_per_request_and_never_the_question():
    client, lines = desk()
    client.get("/health")
    client.post("/ask", json={"question": VIEWS[0]})
    assert len(lines) == 2
    logged = [json.loads(line) for line in lines]
    assert [(row["path"], row["status"], row["refused"]) for row in logged] == [("/health", 200, False),
                                                                                  ("/ask", 200, True)]
    assert all(set(row) == set(deploykit.LOG_COLUMNS) for row in logged)
    assert VIEWS[0] not in "".join(lines)


def test_daily_cap_answers_429_and_logs_it():
    client, lines = desk(daily_cap=2)
    statuses = [client.get("/health").status_code for _ in range(3)]
    assert statuses == [200, 200, 429]
    assert json.loads(lines[-1])["status"] == 429
