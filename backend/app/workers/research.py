from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ResearchJob, ResearchJobStatus


def claim_next_research_job(db: Session) -> ResearchJob | None:
    """Atomically claim one queued job for a separately deployed research worker."""
    job = db.scalar(
        select(ResearchJob)
        .where(ResearchJob.status == ResearchJobStatus.QUEUED)
        .order_by(ResearchJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status = ResearchJobStatus.RUNNING
    job.started_at = datetime.now(UTC)
    job.attempt_count += 1
    db.commit()
    db.refresh(job)
    return job
