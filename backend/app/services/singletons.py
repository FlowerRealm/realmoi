#
# Singleton references initialized at app startup.
#
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .job_manager import JobManager


JOB_MANAGER: "JobManager | None" = None
