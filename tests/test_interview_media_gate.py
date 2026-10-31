"""Regression tests for the interview media/camera completion gate.

A candidate must not be able to finish an interview by only typing. The server
requires a minimum amount of streamed speech, live camera heartbeats, and a
server-side transcript before evaluation is allowed.

Runs without pytest::

    python tests/test_interview_media_gate.py
"""

import asyncio
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backend.main as main  # noqa: E402

FUTURE = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
PAST = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()


def _status(exc):
    return getattr(exc, "status_code", None)


def _media(**over):
    media = {
        "audio_seconds": 45.0,
        "speech_seconds": 31.0,
        "speech_chunks": 40,
        "video_frames": 8,
        "last_audio_at": time.time(),
        "last_video_at": time.time(),
    }
    media.update(over)
    return media


def _spoken_transcript():
    return [{
        "role": "candidate",
        "content": (
            "I led a migration project across three teams, designed the rollout plan, "
            "coordinated the database cutover with the platform and security groups, "
            "documented the rollback process, and reduced deployment incidents by half."
        ),
    }]


def _written_transcript():
    return [{"role": "candidate", "content": "typed answer", "type": "written"}]


def _candidate(**over):
    doc = {
        "email": "priya@example.com",
        "job_id": "j1",
        "hr_invitation": {
            "token": "HR-TOKEN",
            "type": "hr",
            "expires_at": FUTURE,
        },
    }
    doc.update(over)
    return doc


def _payload(**over):
    values = {
        "token": "HR-TOKEN",
        "interview_type": "hr",
        "transcript": [{"role": "candidate", "content": "CLIENT FAKE"}],
    }
    values.update(over)
    return main.EvaluationPayload(**values)


def _call_evaluate(doc, payload=None):
    captured = {}

    def fake_run(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"email": doc["email"], "interview_type": "hr", "decision": "PASS"}

    with mock.patch.object(
        main, "_candidate_ref_for_token", return_value=("priya@example.com", "c1", "j1")
    ), mock.patch.object(main.database, "get_candidate_doc", return_value=doc), \
         mock.patch.object(main.database, "load_candidates", return_value=[
             SimpleNamespace(email="priya@example.com", full_name="Priya", raw_text="resume")
         ]), \
         mock.patch.object(main.database, "get_job_by_id", return_value=None), \
         mock.patch.object(main.database, "load_job", return_value=main.DEFAULT_JOB), \
         mock.patch.object(main, "_run_interview_evaluation", side_effect=fake_run):
        result = main.evaluate_interview(payload or _payload())
    return result, captured


class _IdleSession:
    async def receive(self):
        await asyncio.Event().wait()
        yield  # pragma: no cover

    async def send_client_content(self, **kwargs):
        pass


class _ClosingSession:
    async def receive(self):
        await asyncio.sleep(0.2)
        yield SimpleNamespace(server_content=SimpleNamespace(
            interrupted=False,
            model_turn=None,
            input_transcription=None,
            output_transcription=SimpleNamespace(
                text="This concludes the interview. The interview is now complete."
            ),
            turn_complete=True,
        ))
        await asyncio.Event().wait()
        yield  # pragma: no cover

    async def send_client_content(self, **kwargs):
        pass


class _FakeRelay:
    available = True

    def __init__(self, session):
        self.session = session

    @asynccontextmanager
    async def connect(self):
        yield self.session

    async def begin_interview(self, session):
        pass

    async def send_audio(self, session, payload):
        pass

    async def audio_stream_end(self, session):
        pass


def _drain_ws(ws):
    messages = []
    while True:
        try:
            messages.append(ws.receive_json())
        except (WebSocketDisconnect, RuntimeError):
            return messages


def _exercise_ws(session, send_typed_answer):
    candidate = _candidate()
    ready_calls = []
    run_calls = []

    def fake_ready(email, interview_type, ready, media=None, company_id=None, job_id=None):
        ready_calls.append((email, interview_type, ready, media, company_id, job_id))

    with mock.patch.object(
        main, "_candidate_ref_for_token", return_value=("priya@example.com", "c1", "j1")
    ), mock.patch.object(main.database, "get_candidate_doc", return_value=candidate), \
         mock.patch.object(main.database, "load_candidates", return_value=[
             SimpleNamespace(email="priya@example.com", full_name="Priya", raw_text="resume")
         ]), \
         mock.patch.object(main.database, "get_job_by_id", return_value=None), \
         mock.patch.object(main.database, "load_job", return_value=main.DEFAULT_JOB), \
         mock.patch.object(main.database, "mark_interview_started"), \
         mock.patch.object(main.database, "append_transcript_turn"), \
         mock.patch.object(main.database, "mark_interview_abandoned"), \
         mock.patch.object(
             main.database, "set_candidate_interview_evaluation_ready", side_effect=fake_ready
         ), \
         mock.patch.object(main, "get_interviewer_prompt", return_value="prompt"), \
         mock.patch.object(main, "GeminiLiveRelay", return_value=_FakeRelay(session)), \
         mock.patch.object(
             main, "_run_interview_evaluation", side_effect=lambda *a, **kw: run_calls.append((a, kw))
         ):
        with TestClient(main.app) as client:
            with client.websocket_connect("/ws/interview/HR-TOKEN") as ws:
                assert ws.receive_json()["type"] == "ready"
                first = None
                if send_typed_answer:
                    ws.send_json({
                        "type": "answer",
                        "text": "I am only typing this answer.",
                        "question": "Tell me about yourself.",
                    })
                    first = ws.receive_json()
                    ws.send_json({"type": "end"})
                messages = _drain_ws(ws)
    return first, messages, ready_calls, run_calls


def test_typed_only_websocket_cannot_complete_interview():
    first, messages, ready_calls, run_calls = _exercise_ws(_IdleSession(), True)
    assert first["code"] == "speech_required"
    assert not any(message.get("type") == "evaluation" for message in messages)
    assert any(
        message.get("type") == "error" and message.get("code") == "media_required"
        for message in messages
    )
    assert run_calls == []
    assert ready_calls and ready_calls[-1][2] is False


def test_closing_phrase_without_media_does_not_complete_interview():
    _, messages, ready_calls, run_calls = _exercise_ws(_ClosingSession(), False)
    assert not any(message.get("type") == "evaluation" for message in messages)
    assert any(
        message.get("type") == "error" and message.get("code") == "media_required"
        for message in messages
    )
    assert run_calls == []
    assert ready_calls and ready_calls[-1][2] is False


def test_media_gate_rejects_typed_only_interview():
    assert not main._media_gate_ok(_media(speech_seconds=0), _written_transcript())


def test_media_gate_rejects_missing_camera_frames():
    assert not main._media_gate_ok(_media(video_frames=0), _spoken_transcript())


def test_media_gate_rejects_stale_camera_frames():
    assert not main._media_gate_ok(
        _media(last_video_at=time.time() - 60), _spoken_transcript()
    )


def test_media_gate_rejects_without_spoken_turn():
    assert not main._media_gate_ok(_media(), _written_transcript())


def test_media_gate_rejects_a_token_spoken_greeting():
    assert not main._media_gate_ok(
        _media(), [{"role": "candidate", "content": "Hello."}]
    )


def test_media_gate_accepts_speech_and_fresh_camera():
    assert main._media_gate_ok(_media(), _spoken_transcript())


def test_evaluate_rejects_an_unstarted_interview():
    try:
        _call_evaluate(_candidate())
    except main.HTTPException as exc:
        assert _status(exc) == 409
    else:
        raise AssertionError("an interview that never started must not be evaluable")


def test_evaluate_rejects_missing_media_evidence():
    doc = _candidate(
        hr_interview={
            "status": "in_progress",
            "attempts_used": 1,
            "evaluation_ready": False,
        }
    )
    try:
        _call_evaluate(doc)
    except main.HTTPException as exc:
        assert _status(exc) == 409
    else:
        raise AssertionError("an interview without media evidence must not be evaluable")


def test_evaluate_uses_server_transcript_not_client_payload():
    doc = _candidate(
        hr_interview={
            "status": "in_progress",
            "attempts_used": 1,
            "evaluation_ready": True,
            "media": _media(),
        },
        interview_transcript=[
            {"role": "interviewer", "content": "Tell me about yourself.", "interview": "hr"},
            {"role": "candidate", "content": "server spoken turn", "interview": "hr"},
        ],
    )
    _, captured = _call_evaluate(doc)
    server_transcript = captured["args"][3]
    assert [turn["content"] for turn in server_transcript] == [
        "Tell me about yourself.",
        "server spoken turn",
    ]
    assert captured["kwargs"]["media"] == doc["hr_interview"]["media"]


def test_run_evaluation_preserves_attempt_and_media_fields():
    doc = _candidate(
        hr_interview={
            "status": "in_progress",
            "started_at": PAST,
            "attempts_used": 1,
            "evaluation_ready": True,
            "media": _media(),
            "recording": {"local_path": "temp_files/hr/test.webm"},
        }
    )
    saved = {}

    def fake_set(email, interview, company_id=None, job_id=None):
        saved["interview"] = interview

    with mock.patch.object(main.database, "get_candidate_doc", return_value=doc), \
         mock.patch.object(main.hr_evaluator, "evaluate", return_value={
             "decision": "PASS", "final_round_score": 88,
         }), \
         mock.patch.object(main.database, "set_candidate_hr_interview", side_effect=fake_set), \
         mock.patch.object(main.database, "record_interview_usage", return_value={
             "total_duration_seconds": 600,
             "credits_consumed": 1,
             "new_remainder_seconds": 0,
         }), \
         mock.patch.object(main, "log_activity"):
        main._run_interview_evaluation(
            "priya@example.com",
            SimpleNamespace(raw_text="resume"),
            "hr",
            _spoken_transcript(),
            main.DEFAULT_JOB,
            "c1",
            "j1",
            media=_media(),
        )

    interview = saved["interview"]
    assert interview["status"] == "completed"
    assert interview["attempts_used"] == 1
    assert interview["evaluation_ready"] is True
    assert interview["media"]["video_frames"] == 8
    assert interview["recording"]["local_path"] == "temp_files/hr/test.webm"


def _main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            print(f"  FAIL  {name}: {exc}")
            failed.append(name)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
            failed.append(name)
    print(f"\n{len(tests) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
