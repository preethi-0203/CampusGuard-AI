import os
import shutil
import sqlite3
import sys

DB_PATH = "campusguard.db"
BACKUP_PATH = "campusguard_backup_option_b.db"

VERIFIED_SCORES = {
    60: 100,  # Weapon Detection (critical)
    62: 100,  # Weapon Detection (critical)
    65: 80,   # Fall Detection (high)
    66: 80,   # Fall Detection (high)
    67: 80,   # Fall Detection (high)
    68: 100,  # Weapon Detection (critical)
}


def run_migration():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database file '{DB_PATH}' not found.")

    # 1. Back up database file
    print(f"Backing up '{DB_PATH}' to '{BACKUP_PATH}'...")
    shutil.copy2(DB_PATH, BACKUP_PATH)
    backup_size = os.path.getsize(BACKUP_PATH)
    print(f"Backup created successfully: {BACKUP_PATH} ({backup_size} bytes).")

    # 2. Perform idempotent migration in transaction
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()

        # Check total rows pre-migration
        initial_count = cur.execute("SELECT COUNT(*) FROM alerts;").fetchone()[0]
        initial_ids = set(r[0] for r in cur.execute("SELECT id FROM alerts;").fetchall())
        print(f"Pre-migration alert count: {initial_count}")

        # Check if column exists
        columns = [row[1] for row in cur.execute("PRAGMA table_info(alerts);").fetchall()]
        if "operational_score" not in columns:
            print("Adding 'operational_score' column to alerts table...")
            cur.execute("ALTER TABLE alerts ADD COLUMN operational_score INTEGER DEFAULT NULL;")
            print("Column 'operational_score' added.")
        else:
            print("Column 'operational_score' already exists in alerts table.")

        # Populate ONLY verified historical alerts without overwriting existing non-NULL values
        updated_count = 0
        for alert_id, score in VERIFIED_SCORES.items():
            cur.execute(
                "UPDATE alerts SET operational_score = ? WHERE id = ? AND operational_score IS NULL;",
                (score, alert_id),
            )
            if cur.rowcount > 0:
                updated_count += cur.rowcount
                print(f"  Populated Alert #{alert_id} with operational_score = {score}")
            else:
                current_val = cur.execute("SELECT operational_score FROM alerts WHERE id = ?;", (alert_id,)).fetchone()
                val_str = current_val[0] if current_val else "Not found"
                print(f"  Alert #{alert_id} already has operational_score = {val_str} (no overwrite).")

        conn.commit()
        print(f"Updated {updated_count} verified historical alert records.")

        # Post-migration verifications
        post_count = cur.execute("SELECT COUNT(*) FROM alerts;").fetchone()[0]
        post_ids = set(r[0] for r in cur.execute("SELECT id FROM alerts;").fetchall())

        if post_count != initial_count:
            raise RuntimeError(f"Row count mismatch! Pre: {initial_count}, Post: {post_count}")
        if initial_ids != post_ids:
            raise RuntimeError("Alert ID set mismatch after migration!")

        # Foreign key & integrity checks
        fk_violations = cur.execute("PRAGMA foreign_key_check;").fetchall()
        if fk_violations:
            raise RuntimeError(f"Foreign key violations detected: {fk_violations}")

        integrity = cur.execute("PRAGMA integrity_check;").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Integrity check failed: {integrity}")

        # Summary of scores
        populated_rows = cur.execute(
            "SELECT id, alert_type, severity, operational_score FROM alerts WHERE operational_score IS NOT NULL;"
        ).fetchall()
        null_count = cur.execute("SELECT COUNT(*) FROM alerts WHERE operational_score IS NULL;").fetchone()[0]

        print("\n--- Migration Verification Summary ---")
        print(f"Total alerts: {post_count}")
        print(f"Alerts with operational_score populated: {len(populated_rows)}")
        for r in populated_rows:
            print(f"  Alert #{r[0]}: {r[1]} ({r[2]}) -> operational_score = {r[3]}")
        print(f"Alerts with operational_score NULL: {null_count}")
        print(f"Database integrity check: {integrity}")
        print(f"Database foreign key check: 0 violations")
        print("Migration completed successfully.")

    except Exception as exc:
        conn.rollback()
        print(f"ERROR during migration: {exc}", file=sys.stderr)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
