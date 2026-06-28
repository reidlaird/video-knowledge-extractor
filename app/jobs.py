from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

ProgressCallback = Callable[[str, int, str], None]


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class JobState:
    job_id: str
    status: JobStatus = JobStatus.PENDING
    stage: str = "queued"
    percent: int = 0
    message: str = "Waiting to start…"
    result: dict[str, Any] | None = None
    output_dir: str | None = None
    output_files: list[str] = field(default_factory=list)
    error: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "job_id": self.job_id,
                "status": self.status.value,
                "stage": self.stage,
                "percent": self.percent,
                "message": self.message,
                "result": self.result,
                "output_dir": self.output_dir,
                "output_files": list(self.output_files),
                "error": self.error,
            }

    def update(
        self,
        *,
        status: JobStatus | None = None,
        stage: str | None = None,
        percent: int | None = None,
        message: str | None = None,
        result: dict[str, Any] | None = None,
        output_dir: str | None = None,
        output_files: list[str] | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            if status is not None:
                self.status = status
            if stage is not None:
                self.stage = stage
            if percent is not None:
                self.percent = max(0, min(100, percent))
            if message is not None:
                self.message = message
            if result is not None:
                self.result = result
            if output_dir is not None:
                self.output_dir = output_dir
            if output_files is not None:
                self.output_files = output_files
            if error is not None:
                self.error = error

    def progress_callback(self) -> ProgressCallback:
        def emit(stage: str, percent: int, message: str) -> None:
            self.update(status=JobStatus.RUNNING, stage=stage, percent=percent, message=message)

        return emit


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()

    def create(self) -> JobState:
        job = JobState(job_id=str(uuid.uuid4()))
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def remove_old_jobs(self, *, keep: int = 20) -> None:
        with self._lock:
            if len(self._jobs) <= keep:
                return
            ordered = sorted(self._jobs.values(), key=lambda job: job.job_id)
            for job in ordered[:-keep]:
                self._jobs.pop(job.job_id, None)


JOB_STORE = JobStore()


def dumps_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"
