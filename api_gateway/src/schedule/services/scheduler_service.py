# import asyncio
# from datetime import datetime, timedelta
# from typing import Dict, Any, Optional, List
# import logging
# import pytz
# from apscheduler.schedulers.asyncio import AsyncIOScheduler
# from apscheduler.triggers.cron import CronTrigger
# from apscheduler.triggers.date import DateTrigger
# from apscheduler.triggers.interval import IntervalTrigger
# from apscheduler.jobstores.memory import MemoryJobStore
# from apscheduler.executors.asyncio import AsyncIOExecutor

# logger = logging.getLogger(__name__)
# # Reduce scheduler service verbosity
# logger.setLevel(logging.WARNING)


# class SchedulerService:
#     """Service for managing scheduled calls using APScheduler"""

#     def __init__(self):
#         # Configure job stores and executors
#         jobstores = {
#             'default': MemoryJobStore()
#         }
#         executors = {
#             'default': AsyncIOExecutor()
#         }

#         job_defaults = {
#             'coalesce': False,
#             'max_instances': 3,
#             'misfire_grace_time': 300  # Increased grace time to 5 minutes
#         }

#         self.scheduler = AsyncIOScheduler(
#             jobstores=jobstores,
#             executors=executors,
#             job_defaults=job_defaults,
#             timezone='UTC'  # Explicitly set timezone to avoid issues
#         )

#         self.is_running = False

#     async def start(self):
#         """Start the scheduler"""
#         if not self.is_running:
#             try:
#                 self.scheduler.start()
#                 self.is_running = True
#                 logger.info("Scheduler service started successfully")
#                 # Log all existing jobs for debugging
#                 jobs = self.scheduler.get_jobs()
#                 logger.info(f"Loaded {len(jobs)} jobs into scheduler")
#                 for job in jobs:
#                     logger.info(f"Job {job.id} scheduled for {job.next_run_time}")
#             except Exception as e:
#                 logger.error(f"Failed to start scheduler service: {e}", exc_info=True)
#                 raise

#     async def stop(self):
#         """Stop the scheduler"""
#         if self.is_running:
#             try:
#                 self.scheduler.shutdown()
#                 self.is_running = False
#                 logger.info("Scheduler service stopped")
#             except Exception as e:
#                 logger.error(f"Error stopping scheduler: {e}")

#     async def schedule_call(self, job_id: str, run_time: datetime,
#                            callback_func, args: tuple = (), kwargs: dict = None):
#         """Schedule a single call"""
#         try:
#             if kwargs is None:
#                 kwargs = {}

#             # Handle timezone-aware and timezone-naive datetime objects properly
#             now = datetime.now(pytz.UTC)

#             # If run_time is timezone-naive, make it timezone-aware (UTC)
#             if run_time.tzinfo is None:
#                 logger.info(f"Converting naive datetime {run_time} to UTC timezone-aware")
#                 run_time = pytz.UTC.localize(run_time)
#             # If run_time already has a timezone, convert it to UTC for consistency
#             elif run_time.tzinfo != pytz.UTC:
#                 logger.info(f"Converting from timezone {run_time.tzinfo} to UTC")
#                 run_time = run_time.astimezone(pytz.UTC)

#             logger.info(f"Scheduling job {job_id} for time: {run_time} (UTC)")

#             # Check if run_time is in the past
#             if run_time < now:
#                 logger.warning(f"Scheduled time {run_time} is in the past. Adjusting to current time + 30 seconds.")
#                 run_time = now + timedelta(seconds=5)

#             # Remove existing job if it exists
#             if self.scheduler.get_job(job_id):
#                 logger.info(f"Removing existing job {job_id}")
#                 self.scheduler.remove_job(job_id)

#             # Add new job - run_time is now guaranteed to be timezone-aware in UTC
#             self.scheduler.add_job(
#                 callback_func,
#                 DateTrigger(run_date=run_time),
#                 id=job_id,
#                 args=args,
#                 kwargs=kwargs,
#                 replace_existing=True,
#                 misfire_grace_time=300  # 5 minutes grace time for misfires
#             )

#             # Verify the job was added
#             job = self.scheduler.get_job(job_id)
#             if job:
#                 logger.info(f"Successfully scheduled job {job_id} for {run_time}. Next run time: {job.next_run_time}")
#                 return True
#             else:
#                 logger.error(f"Failed to verify job {job_id} was added to scheduler")
#                 return False

#         except Exception as e:
#             logger.error(f"Error scheduling call job {job_id}: {e}", exc_info=True)
#             return False

#     async def schedule_recurring_call(self, job_id: str, callback_func,
#                                     cron_expression: str = None,
#                                     interval_seconds: int = None,
#                                     args: tuple = (), kwargs: dict = None):
#         """Schedule a recurring call"""
#         try:
#             if kwargs is None:
#                 kwargs = {}

#             # Remove existing job if it exists
#             if self.scheduler.get_job(job_id):
#                 self.scheduler.remove_job(job_id)

#             # Choose trigger type
#             if cron_expression:
#                 trigger = CronTrigger.from_crontab(cron_expression)
#             elif interval_seconds:
#                 trigger = IntervalTrigger(seconds=interval_seconds)
#             else:
#                 raise ValueError("Either cron_expression or interval_seconds must be provided")

#             # Add recurring job
#             self.scheduler.add_job(
#                 callback_func,
#                 trigger,
#                 id=job_id,
#                 args=args,
#                 kwargs=kwargs,
#                 replace_existing=True
#             )

#             logger.info(f"Scheduled recurring call job {job_id}")
#             return True

#         except Exception as e:
#             logger.error(f"Error scheduling recurring call job {job_id}: {e}")
#             return False

#     async def cancel_job(self, job_id: str):
#         """Cancel a scheduled job"""
#         try:
#             if self.scheduler.get_job(job_id):
#                 self.scheduler.remove_job(job_id)
#                 logger.info(f"Cancelled job {job_id}")
#                 return True
#             else:
#                 logger.warning(f"Job {job_id} not found for cancellation")
#                 return False

#         except Exception as e:
#             logger.error(f"Error cancelling job {job_id}: {e}")
#             return False

#     async def pause_job(self, job_id: str):
#         """Pause a scheduled job"""
#         try:
#             if self.scheduler.get_job(job_id):
#                 self.scheduler.pause_job(job_id)
#                 logger.info(f"Paused job {job_id}")
#                 return True
#             else:
#                 logger.warning(f"Job {job_id} not found for pausing")
#                 return False

#         except Exception as e:
#             logger.error(f"Error pausing job {job_id}: {e}")
#             return False

#     async def resume_job(self, job_id: str):
#         """Resume a paused job"""
#         try:
#             if self.scheduler.get_job(job_id):
#                 self.scheduler.resume_job(job_id)
#                 logger.info(f"Resumed job {job_id}")
#                 return True
#             else:
#                 logger.warning(f"Job {job_id} not found for resuming")
#                 return False

#         except Exception as e:
#             logger.error(f"Error resuming job {job_id}: {e}")
#             return False

#     async def get_job_info(self, job_id: str) -> Optional[Dict[str, Any]]:
#         """Get information about a scheduled job"""
#         try:
#             job = self.scheduler.get_job(job_id)
#             if job:
#                 return {
#                     "id": job.id,
#                     "name": job.name,
#                     "next_run_time": job.next_run_time,
#                     "trigger": str(job.trigger),
#                     "executor": job.executor,
#                     "misfire_grace_time": job.misfire_grace_time,
#                     "max_instances": job.max_instances,
#                     "coalesce": job.coalesce
#                 }
#             return None

#         except Exception as e:
#             logger.error(f"Error getting job info for {job_id}: {e}")
#             return None

#     async def get_all_jobs(self) -> List[Dict[str, Any]]:
#         """Get information about all scheduled jobs"""
#         try:
#             jobs = []
#             for job in self.scheduler.get_jobs():
#                 jobs.append({
#                     "id": job.id,
#                     "name": job.name,
#                     "next_run_time": job.next_run_time,
#                     "trigger": str(job.trigger),
#                     "executor": job.executor
#                 })
#             return jobs

#         except Exception as e:
#             logger.error(f"Error getting all jobs: {e}")
#             return []
