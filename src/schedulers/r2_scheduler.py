# src/schedulers/r2_scheduler.py
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

from src.crud.r2CleanupService import R2CleanupService
from src.config.r2_client import r2_client
from src.config.settings import settings

logger = logging.getLogger(__name__)


class R2PeriodicCleanup:
    """Handles periodic R2 cleanup scheduling."""

    def __init__(self):
        self.cleanup_service = R2CleanupService(
            s3_client=r2_client,
            bucket_name=settings.R2_BUCKET
        )
        self.scheduler = AsyncIOScheduler()

    async def cleanup_task(self):
        """Task to run the cleanup"""
        try:
            result = await self.cleanup_service.cleanup_orphaned_media()
            logger.info(f"Scheduled cleanup completed: {result}")
        except Exception as e:
            logger.error(f"Scheduled cleanup failed: {e}")

    def start_periodic_cleanup(self, hour: int = 2, minute: int = 0):
        """
        Start periodic cleanup job.
        Default: runs daily at 2:00 AM
        Note: Environment check is now handled in the lifespan function.
        """
        try:
            self.scheduler.add_job(
                func=self.cleanup_task,
                trigger=CronTrigger(hour=hour, minute=minute),
                id="r2_cleanup",
                name="R2 Orphaned Media Cleanup",
                replace_existing=True
            )
            self.scheduler.start()
            logger.info(f"R2 cleanup scheduled to run daily at {hour:02d}:{minute:02d}")
        except Exception as e:
            logger.error(f"Failed to start R2 cleanup scheduler: {e}")

    def stop_periodic_cleanup(self):
        """Stop the periodic cleanup scheduler."""
        try:
            if hasattr(self, 'scheduler') and self.scheduler.running:
                self.scheduler.shutdown()
                logger.info("R2 cleanup scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping R2 cleanup scheduler: {e}")

    def is_running(self) -> bool:
        """Check if the scheduler is currently running."""
        return hasattr(self, 'scheduler') and self.scheduler.running


# Global instance
r2_scheduler = R2PeriodicCleanup()