import asyncio
from datetime import datetime
from sqlalchemy.orm import Session
from .. import models, database
from . import archiver

async def process_url(db: Session, url_item: models.URLItem):
    # Try Wayback Machine first
    result = await archiver.submit_to_wayback(url_item.normalized_url)
    
    submission = models.ArchiveSubmission(
        url_id=url_item.id,
        service="Wayback Machine",
        status=result["status"],
        archive_url=result.get("archive_url"),
        http_status=result.get("http_status"),
        error_message=result.get("error_message"),
        submission_timestamp=datetime.utcnow(),
        last_attempted=datetime.utcnow()
    )
    db.add(submission)
    
    if result["status"] == "Success":
        url_item.status = "Submitted"
    else:
        # Fallback to Archive.today
        result_at = await archiver.submit_to_archive_today(url_item.normalized_url)
        submission_at = models.ArchiveSubmission(
            url_id=url_item.id,
            service="Archive.today",
            status=result_at["status"],
            archive_url=result_at.get("archive_url"),
            http_status=result_at.get("http_status"),
            error_message=result_at.get("error_message"),
            submission_timestamp=datetime.utcnow(),
            last_attempted=datetime.utcnow()
        )
        db.add(submission_at)
        
        if result_at["status"] == "Success":
            url_item.status = "Submitted"
        else:
            url_item.status = "Failed" # Both failed
            
    db.commit()

async def queue_worker_loop():
    """
    Advanced background daemon with controlled concurrency.
    Fetches batches of URLs and processes them concurrently.
    """
    CONCURRENCY_LIMIT = 5 # Process 5 URLs concurrently
    
    while True:
        db = database.SessionLocal()
        try:
            # Fetch a batch of queued URLs
            queued_items = db.query(models.URLItem).filter(models.URLItem.status == "Queued").limit(CONCURRENCY_LIMIT).all()
            
            if queued_items:
                # Mark all as processing
                for item in queued_items:
                    item.status = "Processing"
                db.commit()
                
                # Process concurrently
                tasks = [process_url(db, item) for item in queued_items]
                await asyncio.gather(*tasks, return_exceptions=True)
                
                # Minimal sleep to respect rate limits while maintaining throughput
                await asyncio.sleep(1)
            else:
                # Sleep if queue is empty
                await asyncio.sleep(5)
        except Exception as e:
            print(f"Worker error: {e}")
            await asyncio.sleep(5)
        finally:
            db.close()
