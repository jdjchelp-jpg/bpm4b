"""
Live SSE Sub-Task Progress Mirror

Streams ultra-precise, real-time conversion progress indicators
to the web UI using Server-Sent Events (SSE).

Feature #9 from the BPM4B v13 feature set.
"""

import json
import queue
import time
import threading
import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

# ─── Progress Event Types ───────────────────────────────────

class ProgressEvent:
    """A single progress event to be streamed via SSE."""

    def __init__(
        self,
        job_id: str,
        stage: str,
        percent: float = 0.0,
        message: str = '',
        detail: Optional[Dict[str, Any]] = None,
    ):
        self.job_id = job_id
        self.stage = stage
        self.percent = percent
        self.message = message
        self.detail = detail or {}
        self.timestamp = time.time()

    def to_sse(self) -> str:
        """Serialize to SSE format."""
        data = {
            'job_id': self.job_id,
            'stage': self.stage,
            'percent': self.percent,
            'message': self.message,
            'detail': self.detail,
            'timestamp': self.timestamp,
        }
        return f'data: {json.dumps(data)}\n\n'

    def to_dict(self) -> Dict[str, Any]:
        return {
            'job_id': self.job_id,
            'stage': self.stage,
            'percent': self.percent,
            'message': self.message,
            'detail': self.detail,
            'timestamp': self.timestamp,
        }


# ─── Progress Manager ───────────────────────────────────────

class ProgressManager:
    """
    Manages progress events across multiple concurrent jobs.
    Each job has its own event queue for SSE streaming.
    """

    def __init__(self):
        self._queues: Dict[str, queue.Queue] = {}
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_job(self, job_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Register a new job."""
        with self._lock:
            self._queues[job_id] = queue.Queue()
            self._jobs[job_id] = {
                'job_id': job_id,
                'status': 'running',
                'created_at': time.time(),
                'metadata': metadata or {},
                'last_event': None,
            }

    def emit(self, job_id: str, event: ProgressEvent) -> None:
        """Emit a progress event for a job."""
        with self._lock:
            if job_id in self._queues:
                self._queues[job_id].put(event)
                if job_id in self._jobs:
                    self._jobs[job_id]['last_event'] = event

    def emit_progress(
        self,
        job_id: str,
        stage: str,
        percent: float,
        message: str = '',
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Convenience: create and emit a progress event."""
        event = ProgressEvent(job_id, stage, percent, message, detail)
        self.emit(job_id, event)

    def complete(self, job_id: str, message: str = 'Complete') -> None:
        """Mark a job as complete."""
        self.emit_progress(job_id, 'complete', 100.0, message)
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]['status'] = 'complete'
                self._jobs[job_id]['completed_at'] = time.time()

    def fail(self, job_id: str, error: str) -> None:
        """Mark a job as failed."""
        self.emit_progress(job_id, 'error', 0.0, error)
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]['status'] = 'error'
                self._jobs[job_id]['error'] = error
                self._jobs[job_id]['completed_at'] = time.time()

    def get_events_generator(self, job_id: str):
        """
        Generator for SSE streaming.
        Yields SSE-formatted strings and blocks for new events.
        """
        q = self._queues.get(job_id)
        if not q:
            return

        # Send initial connection event
        yield f'data: {json.dumps({"type": "connected", "job_id": job_id})}\n\n'

        try:
            while True:
                try:
                    event = q.get(timeout=30)  # 30-second timeout for keep-alive
                    yield event.to_sse()

                    if event.stage in ('complete', 'error'):
                        break
                except queue.Empty:
                    # Send keep-alive comment
                    yield ': keepalive\n\n'
        except GeneratorExit:
            pass
        finally:
            self._cleanup_job(job_id)

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the current status of a job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                return dict(job)
            return None

    def list_active_jobs(self) -> List[Dict[str, Any]]:
        """List all active (running) jobs."""
        with self._lock:
            return [
                dict(job) for job in self._jobs.values()
                if job.get('status') == 'running'
            ]

    def _cleanup_job(self, job_id: str, max_age: int = 3600) -> None:
        """Remove a job's queue after it's done, keep status for a while."""
        with self._lock:
            self._queues.pop(job_id, None)

    def cleanup_old_jobs(self, max_age_seconds: int = 3600) -> None:
        """Remove jobs older than max_age_seconds."""
        now = time.time()
        with self._lock:
            stale = [
                jid for jid, job in self._jobs.items()
                if job.get('completed_at', 0) < now - max_age_seconds
            ]
            for jid in stale:
                self._jobs.pop(jid, None)
                self._queues.pop(jid, None)


# ─── Progress Callback Factory ──────────────────────────────

def make_progress_callback(
    progress_manager: ProgressManager,
    job_id: str,
) -> Callable:
    """
    Create a progress callback function compatible with existing
    audiobook_builder and core functions.

    Usage:
        callback = make_progress_callback(progress_manager, job_id)
        build_audiobook(..., on_progress=callback)
    """

    def on_progress(stage, detail=''):
        if isinstance(stage, (int, float)):
            # Numeric progress (percent)
            progress_manager.emit_progress(
                job_id, 'processing', float(stage), str(detail)
            )
        elif isinstance(stage, str):
            # Stage-based progress
            if stage == 'complete':
                progress_manager.complete(job_id, detail)
            elif stage.startswith('error') or 'fail' in stage.lower():
                progress_manager.fail(job_id, detail)
            else:
                progress_manager.emit_progress(
                    job_id, stage, 0.0, str(detail)
                )

    return on_progress


# ─── Global Singleton ────────────────────────────────────────

_default_manager: Optional[ProgressManager] = None


def get_progress_manager() -> ProgressManager:
    """Get or create the global progress manager singleton."""
    global _default_manager
    if _default_manager is None:
        _default_manager = ProgressManager()
    return _default_manager



