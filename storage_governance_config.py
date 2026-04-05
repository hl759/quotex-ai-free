
import os
from storage_paths import DATA_DIR, STATE_DIR

PROJECT_ROOT = os.getcwd()
STORAGE_ARCHIVE_DIR = os.path.join(DATA_DIR, 'archives')
STORAGE_AUDIT_LOG = os.path.join(DATA_DIR, 'storage_governance_audit.jsonl')
STORAGE_REPORT_FILE = os.path.join(DATA_DIR, 'storage_governance_report.json')

STORAGE_THRESHOLDS = {
    'normal': 60,
    'attention': 75,
    'pressure': 85,
    'critical': 90,
}

RETENTION_POLICY = {
    'scan_snapshots_keep_rows': 1200,
    'scan_snapshots_max_age_days': 14,
    'journal_detailed_keep_rows': 2500,
    'journal_archive_batch_min': 500,
    'journal_archive_max_age_days': 45,
    'collection_keep_latest': {
        'journal_trades': 4000,
        'trade_ledger': 8000,
    },
    'collection_max_age_days': {
        'journal_trades': 90,
        'trade_ledger': 120,
    },
    'tmp_max_age_days': 2,
    'log_max_age_days': 7,
    'report_keep_days': 45,
    'min_free_bytes_guard': 64 * 1024 * 1024,
    'maintenance_every_scans': 25,
    'maintenance_min_interval_seconds': 900,
}

MONITORED_DIRS = [DATA_DIR, STATE_DIR]
CRITICAL_FILES = {
    'alpha_hive_journal.json',
    'alpha_hive_state.db',
    'latest_signals.json',
    'current_decision.json',
    'pending_decisions.json',
    'meta.json',
    'capital_state.json',
}
