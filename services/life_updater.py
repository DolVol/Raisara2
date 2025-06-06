import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import sqlite3
import atexit

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TreeLifeUpdater:
    def __init__(self, database_url):
        """Initialize the tree life updater service"""
        self.database_url = database_url.replace('sqlite:///', '')  # Remove sqlite:/// prefix
        self.scheduler = BackgroundScheduler()
        
    def update_all_trees_life_days(self):
        """Update life days for all trees by incrementing by 1"""
        try:
            conn = sqlite3.connect(self.database_url)
            cursor = conn.cursor()
            
            # Ensure life_days column exists
            try:
                cursor.execute('ALTER TABLE tree ADD COLUMN life_days INTEGER DEFAULT 0')
                cursor.execute('ALTER TABLE tree ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
                conn.commit()
                logger.info("Added life_days and updated_at columns to tree table")
            except:
                pass  # Columns already exist
            
            # Update all trees' life_days by adding 1
            cursor.execute('''
                UPDATE tree 
                SET life_days = COALESCE(life_days, 0) + 1,
                    updated_at = ?
                WHERE id IS NOT NULL
            ''', (datetime.now(),))
            
            affected_rows = cursor.rowcount
            conn.commit()
            conn.close()
            
            logger.info(f"Successfully updated life days for {affected_rows} trees")
            return affected_rows
            
        except Exception as e:
            logger.error(f"Error updating tree life days: {str(e)}")
            return 0
    
    def start_scheduler(self):
        """Start the daily scheduler"""
        try:
            # Schedule daily update at midnight (00:00)
            self.scheduler.add_job(
                func=self.update_all_trees_life_days,
                trigger=CronTrigger(hour=0, minute=0),  # Run at midnight every day
                id='daily_tree_life_update',
                name='Daily Tree Life Days Update',
                replace_existing=True
            )
            
            self.scheduler.start()
            logger.info("Tree life updater scheduler started successfully")
            
            # Ensure scheduler shuts down when the application exits
            atexit.register(lambda: self.scheduler.shutdown())
            
        except Exception as e:
            logger.error(f"Error starting scheduler: {str(e)}")
    
    def stop_scheduler(self):
        """Stop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Tree life updater scheduler stopped")
    
    def run_manual_update(self):
        """Manually trigger the life days update (for testing)"""
        logger.info("Running manual tree life days update...")
        return self.update_all_trees_life_days()
    
    def get_scheduler_status(self):
        """Get current scheduler status"""
        is_running = self.scheduler.running if self.scheduler else False
        jobs = []
        
        if is_running:
            jobs = [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None
                }
                for job in self.scheduler.get_jobs()
            ]
        
        return {
            "scheduler_running": is_running,
            "jobs": jobs
        }