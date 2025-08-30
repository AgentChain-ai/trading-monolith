#!/usr/bin/env python3
"""
Database migration script for NTM Trading Engine
Handles schema updates and data migration with versioning and rollback support
"""

import sys
import os
import sqlite3
from pathlib import Path
from datetime import datetime
import json
import shutil
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from backend.app.database import engine, SessionLocal
from backend.app.models import Base, Article, Bucket, Label, MLModel
from sqlalchemy import inspect, text, create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Migration version tracking
CURRENT_MIGRATION_VERSION = "1.2.0"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
MIGRATIONS_DIR.mkdir(exist_ok=True)

# Create migration history table
MigrationBase = declarative_base()

class MigrationHistory(MigrationBase):
    __tablename__ = 'migration_history'
    
    id = Column(Integer, primary_key=True)
    version = Column(String(20), nullable=False)
    description = Column(Text)
    applied_at = Column(DateTime, default=datetime.utcnow)
    rollback_sql = Column(Text)  # SQL commands to rollback this migration

def init_migration_tracking():
    """Initialize migration tracking table"""
    try:
        MigrationBase.metadata.create_all(bind=engine)
        logger.info("Migration tracking initialized")
    except Exception as e:
        logger.error(f"Failed to initialize migration tracking: {e}")
        raise

def get_current_version() -> Optional[str]:
    """Get the current database version"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT version FROM migration_history ORDER BY applied_at DESC LIMIT 1"
            )).fetchone()
            return result[0] if result else None
    except Exception:
        return None

def record_migration(version: str, description: str, rollback_sql: str = ""):
    """Record a successful migration"""
    try:
        db = SessionLocal()
        migration = MigrationHistory(
            version=version,
            description=description,
            rollback_sql=rollback_sql
        )
        db.add(migration)
        db.commit()
        db.close()
        logger.info(f"Migration {version} recorded successfully")
    except Exception as e:
        logger.error(f"Failed to record migration: {e}")

def create_backup(backup_suffix: str = None) -> Path:
    """Create database backup with optional suffix"""
    db_path = Path(__file__).parent.parent / "data" / "ntm_trading.db"
    if not db_path.exists():
        logger.warning("Database file does not exist, skipping backup")
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{backup_suffix}" if backup_suffix else ""
    backup_path = db_path.with_suffix(f'.db.backup_{timestamp}{suffix}')
    
    shutil.copy2(db_path, backup_path)
    logger.info(f"Database backed up to: {backup_path}")
    return backup_path

def validate_schema_integrity() -> bool:
    """Validate database schema integrity"""
    try:
        inspector = inspect(engine)
        required_tables = ['articles', 'buckets', 'labels', 'models']
        existing_tables = inspector.get_table_names()
        
        missing_tables = [t for t in required_tables if t not in existing_tables]
        if missing_tables:
            logger.error(f"Missing required tables: {missing_tables}")
            return False
            
        # Validate critical columns
        bucket_columns = [col['name'] for col in inspector.get_columns('buckets')]
        required_bucket_columns = ['article_count', 'avg_source_trust', 'avg_novelty']
        missing_columns = [c for c in required_bucket_columns if c not in bucket_columns]
        
        if missing_columns:
            logger.error(f"Missing required columns in buckets table: {missing_columns}")
            return False
            
        logger.info("Schema integrity validation passed")
        return True
        
    except Exception as e:
        logger.error(f"Schema validation failed: {e}")
        return False

def check_table_exists(engine, table_name):
    """Check if a table exists"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()

def get_table_columns(engine, table_name):
    """Get list of columns in a table"""
    inspector = inspect(engine)
    if table_name in inspector.get_table_names():
        return [col['name'] for col in inspector.get_columns(table_name)]
    return []

def migrate_database():
    """Migrate database to latest schema with full versioning support"""
    try:
        logger.info(f"Starting database migration to version {CURRENT_MIGRATION_VERSION}")
        
        # Initialize migration tracking
        init_migration_tracking()
        
        # Check current version
        current_version = get_current_version()
        logger.info(f"Current database version: {current_version or 'None (fresh install)'}")
        
        if current_version == CURRENT_MIGRATION_VERSION:
            logger.info("Database is already up to date")
            return True
            
        # Create pre-migration backup
        backup_path = create_backup("pre_migration")
        
        # Check current schema
        existing_tables = inspect(engine).get_table_names()
        logger.info(f"Existing tables: {existing_tables}")
        
        migration_steps = []
        rollback_commands = []
        
        try:
            # Migration Step 1: Add missing columns to buckets table
            if 'buckets' in existing_tables:
                bucket_columns = get_table_columns(engine, 'buckets')
                new_columns = [
                    ('article_count', 'INTEGER', 'ALTER TABLE buckets DROP COLUMN article_count'),
                    ('avg_source_trust', 'REAL', 'ALTER TABLE buckets DROP COLUMN avg_source_trust'),
                    ('avg_novelty', 'REAL', 'ALTER TABLE buckets DROP COLUMN avg_novelty')
                ]
                
                missing_columns = [(name, sql_type, rollback) for name, sql_type, rollback in new_columns
                                 if name not in bucket_columns]
                
                if missing_columns:
                    logger.info(f"Adding missing columns to buckets table: {[col[0] for col in missing_columns]}")
                    
                    with engine.connect() as conn:
                        for column_name, sql_type, rollback_sql in missing_columns:
                            alter_sql = f"ALTER TABLE buckets ADD COLUMN {column_name} {sql_type}"
                            conn.execute(text(alter_sql))
                            migration_steps.append(f"Added column {column_name}")
                            rollback_commands.append(rollback_sql)
                        
                        conn.commit()
                    logger.info("Successfully added missing columns")
            
            # Migration Step 2: Create all missing tables
            logger.info("Creating/updating all tables...")
            Base.metadata.create_all(bind=engine)
            migration_steps.append("Created/updated all tables")
            
            # Migration Step 3: Add indexes for performance
            with engine.connect() as conn:
                try:
                    # Create indexes if they don't exist
                    indexes = [
                        "CREATE INDEX IF NOT EXISTS idx_articles_token_created ON articles(token, created_at)",
                        "CREATE INDEX IF NOT EXISTS idx_buckets_token_ts ON buckets(token, bucket_ts)",
                        "CREATE INDEX IF NOT EXISTS idx_labels_token_ts ON labels(token, bucket_ts)",
                        "CREATE INDEX IF NOT EXISTS idx_models_token_created ON models(token, created_at)"
                    ]
                    
                    for index_sql in indexes:
                        conn.execute(text(index_sql))
                    
                    conn.commit()
                    migration_steps.append("Created performance indexes")
                    logger.info("Performance indexes created")
                    
                except Exception as e:
                    logger.warning(f"Index creation failed (may already exist): {e}")
            
            # Validate final schema
            if not validate_schema_integrity():
                raise Exception("Schema integrity validation failed")
            
            # Record successful migration
            migration_description = f"Migration to v{CURRENT_MIGRATION_VERSION}: " + "; ".join(migration_steps)
            rollback_sql = "; ".join(rollback_commands) if rollback_commands else ""
            
            record_migration(CURRENT_MIGRATION_VERSION, migration_description, rollback_sql)
            
            # Create post-migration backup
            create_backup("post_migration")
            
            logger.info(f"Database migration to v{CURRENT_MIGRATION_VERSION} completed successfully!")
            return True
            
        except Exception as migration_error:
            logger.error(f"Migration failed: {migration_error}")
            
            # Restore from backup if available
            if backup_path and backup_path.exists():
                logger.info("Attempting to restore from backup...")
                db_path = Path(__file__).parent.parent / "data" / "ntm_trading.db"
                shutil.copy2(backup_path, db_path)
                logger.info("Database restored from backup")
            
            raise migration_error
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False

def rollback_migration(target_version: str = None):
    """Rollback to a specific version or the previous version"""
    try:
        logger.info(f"Starting rollback to version: {target_version or 'previous'}")
        
        db = SessionLocal()
        try:
            # Get migration history
            if target_version:
                migrations = db.query(MigrationHistory).filter(
                    MigrationHistory.version == target_version
                ).all()
            else:
                # Get the last migration to rollback
                migrations = db.query(MigrationHistory).order_by(
                    MigrationHistory.applied_at.desc()
                ).limit(1).all()
            
            if not migrations:
                logger.error(f"No migration found for version: {target_version}")
                return False
            
            # Create backup before rollback
            create_backup("pre_rollback")
            
            # Execute rollback commands
            for migration in migrations:
                if migration.rollback_sql:
                    logger.info(f"Rolling back migration {migration.version}")
                    with engine.connect() as conn:
                        for sql in migration.rollback_sql.split(';'):
                            if sql.strip():
                                conn.execute(text(sql.strip()))
                        conn.commit()
                
                # Remove migration record
                db.delete(migration)
            
            db.commit()
            logger.info("Rollback completed successfully")
            return True
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        return False

def test_database_operations():
    """Test basic database operations"""
    try:
        logger.info("Testing database operations...")
        
        db = SessionLocal()
        try:
            # Test article creation
            test_article = Article(
                token="TEST",
                url="https://test.com/article1",
                title="Test Article",
                sentiment_score=0.5,
                source_trust=1.0,
                final_weight=0.8
            )
            db.add(test_article)
            db.flush()
            
            # Test bucket creation with new fields
            test_bucket = Bucket(
                token="TEST",
                bucket_ts=test_article.created_at,
                narrative_heat=1.5,
                positive_heat=2.0,
                negative_heat=0.5,
                consensus=0.8,
                hype_velocity=0.1,
                risk_polarity=0.2,
                event_distribution={"listing": 0.6, "partnership": 0.4},
                top_event="listing",
                article_count=1,
                avg_source_trust=1.0,
                avg_novelty=0.8
            )
            db.add(test_bucket)
            db.flush()
            
            # Test label creation
            test_label = Label(
                token="TEST",
                bucket_ts=test_bucket.bucket_ts,
                forward_return_60m=0.025,
                label_binary=1
            )
            db.add(test_label)
            
            # Commit all changes
            db.commit()
            
            # Verify data was created
            article_count = db.query(Article).filter(Article.token == "TEST").count()
            bucket_count = db.query(Bucket).filter(Bucket.token == "TEST").count()
            label_count = db.query(Label).filter(Label.token == "TEST").count()
            
            logger.info(f"Test data created - Articles: {article_count}, Buckets: {bucket_count}, Labels: {label_count}")
            
            # Clean up test data
            db.query(Label).filter(Label.token == "TEST").delete()
            db.query(Bucket).filter(Bucket.token == "TEST").delete()
            db.query(Article).filter(Article.token == "TEST").delete()
            db.commit()
            
            logger.info("Database operations test passed!")
            return True
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Database operations test failed: {e}")
        return False

def show_migration_history():
    """Show migration history"""
    try:
        db = SessionLocal()
        migrations = db.query(MigrationHistory).order_by(MigrationHistory.applied_at.desc()).all()
        
        if not migrations:
            print("No migrations found")
            return
            
        print("\n📋 Migration History:")
        print("-" * 80)
        for migration in migrations:
            print(f"Version: {migration.version}")
            print(f"Applied: {migration.applied_at}")
            print(f"Description: {migration.description}")
            print("-" * 80)
            
        db.close()
        
    except Exception as e:
        logger.error(f"Failed to show migration history: {e}")

def main():
    """Main CLI interface for migration script"""
    import argparse
    
    parser = argparse.ArgumentParser(description='NTM Trading Engine Database Migration Tool')
    parser.add_argument('command', nargs='?', default='migrate',
                       choices=['migrate', 'rollback', 'history', 'test'],
                       help='Command to execute (default: migrate)')
    parser.add_argument('--version', help='Target version for rollback')
    parser.add_argument('--force', action='store_true', help='Force operation without confirmation')
    
    args = parser.parse_args()
    
    print("🔧 NTM Trading Engine Database Migration Tool")
    print("=" * 50)
    
    if args.command == 'migrate':
        print("🚀 Starting database migration...")
        if migrate_database():
            print("✅ Database migration successful")
            
            # Run test operations
            if test_database_operations():
                print("✅ Database operations test passed")
                print("\n🚀 Database is ready for use!")
            else:
                print("❌ Database operations test failed")
                sys.exit(1)
        else:
            print("❌ Database migration failed")
            sys.exit(1)
    
    elif args.command == 'rollback':
        if not args.force:
            confirmation = input(f"⚠️  Are you sure you want to rollback to version {args.version or 'previous'}? [y/N]: ")
            if confirmation.lower() not in ['y', 'yes']:
                print("Rollback cancelled")
                return
        
        print(f"🔄 Rolling back to version: {args.version or 'previous'}")
        if rollback_migration(args.version):
            print("✅ Rollback completed successfully")
        else:
            print("❌ Rollback failed")
            sys.exit(1)
    
    elif args.command == 'history':
        show_migration_history()
    
    elif args.command == 'test':
        print("🧪 Running database tests...")
        if test_database_operations():
            print("✅ All tests passed")
        else:
            print("❌ Tests failed")
            sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)