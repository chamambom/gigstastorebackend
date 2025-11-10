import asyncio
import logging
from datetime import datetime
from typing import List, Set
from motor.motor_asyncio import AsyncIOMotorDatabase
import boto3
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger(__name__)


class R2CleanupService:
    """Service for cleaning up orphaned media files from Cloudflare R2."""

    def __init__(self, s3_client, bucket_name: str):
        self.s3_client = s3_client
        self.bucket_name = bucket_name

    async def get_all_media_keys_from_db(self) -> Set[str]:
        """Get all object keys currently referenced in the database."""
        try:
            # Import here to avoid circular imports
            from src.models.serviceModel import Services

            # Aggregate all media object_keys from all services
            pipeline = [
                {"$match": {"media": {"$exists": True, "$ne": []}}},
                {"$unwind": "$media"},
                {"$group": {"_id": None, "keys": {"$addToSet": "$media.object_key"}}}
            ]

            result = await Services.aggregate(pipeline).to_list(1)
            if result:
                return set(result[0]["keys"])
            return set()

        except Exception as e:
            logger.error(f"Failed to fetch media keys from database: {e}")
            raise

    def get_all_objects_from_r2(self, prefix: str = "services/") -> Set[str]:
        """Get all object keys from R2 storage with the given prefix."""
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            object_keys = set()

            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        object_keys.add(obj['Key'])

            return object_keys

        except (ClientError, BotoCoreError) as e:
            logger.error(f"Failed to list objects from R2: {e}")
            raise

    async def delete_objects_from_r2(self, object_keys: List[str]) -> tuple[int, int]:
        """
        Delete multiple objects from R2 storage.
        Returns (successful_deletions, failed_deletions).
        """
        if not object_keys:
            return 0, 0

        successful_deletions = 0
        failed_deletions = 0

        # Delete in batches of 1000 (S3 delete limit)
        batch_size = 1000
        for i in range(0, len(object_keys), batch_size):
            batch = object_keys[i:i + batch_size]

            try:
                delete_request = {
                    'Objects': [{'Key': key} for key in batch],
                    'Quiet': True  # Only return errors, not successes
                }

                response = self.s3_client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete=delete_request
                )

                # Count errors
                errors = response.get('Errors', [])
                failed_deletions += len(errors)
                successful_deletions += len(batch) - len(errors)

                # Log any errors
                for error in errors:
                    logger.error(f"Failed to delete {error['Key']}: {error['Message']}")

            except (ClientError, BotoCoreError) as e:
                logger.error(f"Failed to delete batch: {e}")
                failed_deletions += len(batch)

        return successful_deletions, failed_deletions

    async def cleanup_orphaned_media(self, dry_run: bool = False) -> dict:
        """
        Main cleanup method that identifies and deletes orphaned media files.
        Returns a summary of the cleanup operation.
        """
        start_time = datetime.now()
        logger.info("Starting R2 cleanup job")

        try:
            # Get all media keys from database
            db_keys = await self.get_all_media_keys_from_db()
            logger.info(f"Found {len(db_keys)} media files referenced in database")

            # Get all objects from R2
            r2_keys = self.get_all_objects_from_r2()
            logger.info(f"Found {len(r2_keys)} objects in R2 storage")

            # Find orphaned keys (in R2 but not in DB)
            orphaned_keys = r2_keys - db_keys

            if not orphaned_keys:
                logger.info("No orphaned files found")
                return {
                    "status": "completed",
                    "orphaned_files_found": 0,
                    "files_deleted": 0,
                    "deletion_failures": 0,
                    "duration_seconds": (datetime.now() - start_time).total_seconds(),
                    "dry_run": dry_run
                }

            logger.info(f"Found {len(orphaned_keys)} orphaned files")

            # If dry run, just return what would be deleted
            if dry_run:
                return {
                    "status": "dry_run_completed",
                    "orphaned_files_found": len(orphaned_keys),
                    "orphaned_files": list(orphaned_keys)[:10],  # Show first 10 as sample
                    "files_deleted": 0,
                    "deletion_failures": 0,
                    "duration_seconds": (datetime.now() - start_time).total_seconds(),
                    "dry_run": True
                }

            # Delete orphaned files
            successful_deletions, failed_deletions = await self.delete_objects_from_r2(
                list(orphaned_keys)
            )

            duration = (datetime.now() - start_time).total_seconds()

            summary = {
                "status": "completed",
                "orphaned_files_found": len(orphaned_keys),
                "files_deleted": successful_deletions,
                "deletion_failures": failed_deletions,
                "duration_seconds": duration,
                "dry_run": False
            }

            logger.info(f"R2 cleanup completed: {summary}")
            return summary

        except Exception as e:
            logger.error(f"R2 cleanup job failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "duration_seconds": (datetime.now() - start_time).total_seconds(),
                "dry_run": dry_run
            }
