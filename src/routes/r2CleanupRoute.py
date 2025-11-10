# src/routes/r2CleanupRoute.py
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
import logging

from src.crud.r2CleanupService import R2CleanupService
from src.config.r2_client import r2_client
from src.config.settings import settings

from src.crud.userService import super_user
from src.schemas.userSchema import UserRead

logger = logging.getLogger(__name__)
router = APIRouter()


# Dependency to get cleanup service
def get_cleanup_service() -> R2CleanupService:
    return R2CleanupService(
        s3_client=r2_client,
        bucket_name=settings.R2_BUCKET
    )


async def run_r2_cleanup_job(
        cleanup_service: R2CleanupService,
        dry_run: bool = False
):
    """Background task wrapper for the cleanup job."""
    try:
        result = await cleanup_service.cleanup_orphaned_media(dry_run=dry_run)
        logger.info(f"Cleanup job completed with result: {result}")
        return result
    except Exception as e:
        logger.error(f"Background cleanup job failed: {e}")
        raise


@router.post("/cleanup-r2")
async def trigger_r2_cleanup(
        background_tasks: BackgroundTasks,
        dry_run: bool = Query(False, description="If true, only shows what would be deleted without actually deleting"),
        cleanup_service: R2CleanupService = Depends(get_cleanup_service),
        current_user: UserRead = Depends(super_user)  # Only superusers can trigger cleanup
):
    """
    Trigger R2 cleanup job to remove orphaned media files.
    Use dry_run=true to see what would be deleted without actually deleting.
    """
    try:
        if dry_run:
            # For dry run, execute immediately to return results
            result = await cleanup_service.cleanup_orphaned_media(dry_run=True)
            return {
                "message": "Dry run completed",
                "result": result
            }
        else:
            # For actual cleanup, run in background
            background_tasks.add_task(run_r2_cleanup_job, cleanup_service, False)
            return {
                "message": "R2 cleanup job scheduled and running in background",
                "note": "Check logs for completion status"
            }
    except Exception as e:
        logger.error(f"Failed to trigger R2 cleanup: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger cleanup: {str(e)}"
        )


@router.get("/cleanup-r2/stats")
async def get_cleanup_stats(
        cleanup_service: R2CleanupService = Depends(get_cleanup_service),
        current_user: UserRead = Depends(super_user)  # Only superusers can view stats
):
    """Get statistics about database vs R2 storage without cleaning up."""
    try:
        db_keys = await cleanup_service.get_all_media_keys_from_db()
        r2_keys = cleanup_service.get_all_objects_from_r2()
        orphaned_keys = r2_keys - db_keys

        return {
            "database_files": len(db_keys),
            "r2_files": len(r2_keys),
            "orphaned_files": len(orphaned_keys),
            "storage_efficiency": f"{((len(r2_keys) - len(orphaned_keys)) / len(r2_keys) * 100):.1f}%" if r2_keys else "100%"
        }
    except Exception as e:
        logger.error(f"Failed to get cleanup stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get stats: {str(e)}"
        )