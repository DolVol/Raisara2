import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, time
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TreeLifeUpdater:
    def __init__(self, database_url=None):
        """Initialize the TreeLifeUpdater with database URL"""
        self.database_url = database_url
        self.scheduler = BackgroundScheduler()
        self.is_postgresql = False
        
        # Determine database type
        if database_url:
            if database_url.startswith('postgresql://') or database_url.startswith('postgres://'):
                self.is_postgresql = True
                # Fix postgres:// to postgresql:// for psycopg2
                if database_url.startswith('postgres://'):
                    self.database_url = database_url.replace('postgres://', 'postgresql://', 1)
            elif database_url.startswith('sqlite:///'):
                self.is_postgresql = False
                self.database_url = database_url.replace('sqlite:///', '')
            else:
                logger.warning(f"Unknown database URL format: {database_url}")
                self.database_url = 'db.sqlite3'  # Fallback to SQLite
        else:
            # Fallback to SQLite if no URL provided
            self.database_url = 'db.sqlite3'
            self.is_postgresql = False
            logger.warning("No database URL provided, using SQLite fallback")
        
        logger.info(f"TreeLifeUpdater initialized with {'PostgreSQL' if self.is_postgresql else 'SQLite'}")

    def get_connection(self):
        """Get database connection based on database type"""
        try:
            if self.is_postgresql:
                return psycopg2.connect(self.database_url)
            else:
                return sqlite3.connect(self.database_url)
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            return None

    def update_tree_life_days(self):
        """Update life_days for all trees by incrementing by 1"""
        try:
            conn = self.get_connection()
            if not conn:
                logger.error("Could not establish database connection")
                return 0
            
            cursor = conn.cursor()
            
            if self.is_postgresql:
                # PostgreSQL syntax
                cursor.execute("""
                    UPDATE tree 
                    SET life_days = COALESCE(life_days, 0) + 1
                    WHERE life_days IS NOT NULL OR life_days IS NULL
                """)
                affected_rows = cursor.rowcount
            else:
                # SQLite syntax
                cursor.execute("""
                    UPDATE tree 
                    SET life_days = COALESCE(life_days, 0) + 1
                """)
                affected_rows = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            logger.info(f"Updated life_days for {affected_rows} trees")
            return affected_rows
            
        except Exception as e:
            logger.error(f"Error updating tree life days: {e}")
            if conn:
                conn.close()
            return 0

    def run_manual_update(self):
        """Manually trigger the life days update"""
        logger.info("Manual tree life days update triggered")
        return self.update_tree_life_days()

    def start_scheduler(self):
        """Start the background scheduler for daily updates"""
        try:
            # Schedule daily update at midnight
            self.scheduler.add_job(
                func=self.update_tree_life_days,
                trigger="cron",
                hour=0,
                minute=0,
                id='daily_tree_update',
                name='Daily Tree Life Days Update',
                replace_existing=True
            )
            
            self.scheduler.start()
            logger.info("Tree life updater scheduler started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")

    def stop_scheduler(self):
        """Stop the background scheduler"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown()
                logger.info("Tree life updater scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")

    def get_scheduler_status(self):
        """Get the current status of the scheduler"""
        try:
            return {
                "running": self.scheduler.running if self.scheduler else False,
                "jobs": len(self.scheduler.get_jobs()) if self.scheduler else 0,
                "database_type": "PostgreSQL" if self.is_postgresql else "SQLite",
                "database_url": self.database_url[:50] + "..." if len(self.database_url) > 50 else self.database_url
            }
        except Exception as e:
            logger.error(f"Error getting scheduler status: {e}")
            return {"error": str(e)}