"""
Database migration script for Leviathan Graph Control Plane.

Usage:
    python -m leviathan.graph.migrate [--postgres-url URL]
"""
import argparse
import sys
from pathlib import Path
import psycopg2


def run_migrations(postgres_url: str):
    """
    Run all SQL migrations in order.
    
    Args:
        postgres_url: PostgreSQL connection URL
    """
    migrations_dir = Path(__file__).parent / "migrations"
    
    # Get all migration files in order
    migration_files = sorted(migrations_dir.glob("*.sql"))
    
    if not migration_files:
        print("No migration files found")
        return
    
    print(f"Found {len(migration_files)} migration(s)")
    
    # Connect to database
    conn = psycopg2.connect(postgres_url)
    
    try:
        for migration_file in migration_files:
            print(f"Running migration: {migration_file.name}")
            
            with open(migration_file, 'r') as f:
                sql = f.read()
            
            with conn.cursor() as cur:
                cur.execute(sql)
            
            conn.commit()
            print(f"✅ {migration_file.name} completed")
        
        print("\n✅ All migrations completed successfully")
    
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {str(e)}", file=sys.stderr)
        sys.exit(1)
    
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Run Leviathan graph database migrations")
    parser.add_argument(
        "--postgres-url",
        default="postgresql://leviathan:leviathan_dev_password@localhost:5432/leviathan",
        help="PostgreSQL connection URL"
    )
    
    args = parser.parse_args()
    
    print("Leviathan Graph Control Plane - Database Migration")
    print("=" * 60)
    print(f"Database: {args.postgres_url.split('@')[1] if '@' in args.postgres_url else args.postgres_url}")
    print()
    
    run_migrations(args.postgres_url)


if __name__ == "__main__":
    main()
