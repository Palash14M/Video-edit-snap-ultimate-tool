"""A bounded private worker with cooperative cancellation and explicit outcomes."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Event, RLock
import time
import uuid

from .media import Cancelled


@dataclass
class Job:
    id: str
    kind: str
    project_id: str | None
    status: str = 'queued'
    progress: float = 0
    message: str = 'Waiting for worker'
    error: str | None = None
    clip_id: str | None = None
    created_at: float = field(default_factory=time.time)
    cancel_event: Event = field(default_factory=Event)

    def public(self):
        return {key: getattr(self, key) for key in (
            'id', 'kind', 'project_id', 'status', 'progress', 'message', 'error', 'clip_id', 'created_at'
        )}


class Jobs:
    def __init__(self):
        self.lock = RLock()
        self.entries = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='video-worker')

    def submit(self, kind, project_id, task, finalize=None):
        with self.lock:
            if sum(j.status in ('queued', 'running') for j in self.entries.values()) >= 4:
                raise ValueError('The worker queue is full. Wait for a job or cancel one.')
            job = Job(uuid.uuid4().hex, kind, project_id)
            self.entries[job.id] = job

        def run():
            try:
                if job.cancel_event.is_set():
                    raise Cancelled('Cancelled')
                with self.lock:
                    job.status, job.message = 'running', 'Processing video'

                def progress(value, message=None):
                    with self.lock:
                        job.progress = min(.99, max(0, float(value)))
                        if message:
                            job.message = message

                task(job, progress)
                if job.cancel_event.is_set():
                    raise Cancelled('Cancelled')
                with self.lock:
                    job.status, job.progress, job.message = 'completed', 1, 'Complete'
            except Cancelled:
                with self.lock:
                    job.status, job.message = 'cancelled', 'Cancelled'
            except Exception as exc:
                # Deliberately retain useful validation errors, never raw downloader logs/credential data.
                with self.lock:
                    job.status, job.message = 'failed', 'Could not complete this job'
                    job.error = str(exc)[:400] if isinstance(exc, ValueError) else 'Processing failed. Check server logs.'
            finally:
                if finalize:
                    finalize(job)
        self.pool.submit(run)
        return job.public()

    def close(self):
        for job in self.entries.values():
            job.cancel_event.set()
        self.pool.shutdown(wait=True, cancel_futures=True)
