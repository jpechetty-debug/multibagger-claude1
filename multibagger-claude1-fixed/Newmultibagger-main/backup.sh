#!/bin/bash
# Sovereign Terminal — Backup Script (Linux/WSL)
# Backs up databases and configuration state.

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="./backups/$DATE"
mkdir -p "$BACKUP_DIR"

echo "Starting backup to $BACKUP_DIR..."

# 1. Databases
cp sovereign_v12.db "$BACKUP_DIR/" 2>/dev/null || echo "Main DB not found."
cp data_cache.db "$BACKUP_DIR/" 2>/dev/null || echo "Cache DB not found."
cp test_stocks.db "$BACKUP_DIR/" 2>/dev/null || echo "Test DB not found."

# 2. Configuration & State
cp .env "$BACKUP_DIR/" 2>/dev/null
cp data/universe_flags.json "$BACKUP_DIR/" 2>/dev/null || echo "Universe flags not found."

# 3. Models
if [ -d "runtime/models" ]; then
    cp -r runtime/models "$BACKUP_DIR/"
fi

# 4. Compress
tar -czf "backups/sovereign_backup_$DATE.tar.gz" -C "./backups" "$DATE"
rm -rf "$BACKUP_DIR"

echo "Backup complete: backups/sovereign_backup_$DATE.tar.gz"
