
import gzip
import json
import os
import shutil
import time
from datetime import datetime, timedelta

from json_safe import safe_dump, to_jsonable
from storage_paths import DATA_DIR, STATE_DIR, ensure_parent
from storage_governance_config import (
    STORAGE_ARCHIVE_DIR,
    STORAGE_AUDIT_LOG,
    STORAGE_REPORT_FILE,
    STORAGE_THRESHOLDS,
    RETENTION_POLICY,
    MONITORED_DIRS,
    CRITICAL_FILES,
)


class StorageGovernanceEngine:
    def __init__(self, state_store=None):
        self.state_store = state_store
        self.audit_key = 'storage_governance_meta'
        os.makedirs(STORAGE_ARCHIVE_DIR, exist_ok=True)
        ensure_parent(STORAGE_AUDIT_LOG)
        ensure_parent(STORAGE_REPORT_FILE)

    def _now(self):
        return datetime.utcnow()

    def _safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return float(default)

    def _safe_int(self, value, default=0):
        try:
            return int(value)
        except Exception:
            return int(default)

    def _read_json(self, path, default=None):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return default

    def _write_json(self, path, data):
        tmp = path + '.tmp'
        ensure_parent(path)
        with open(tmp, 'w', encoding='utf-8') as f:
            safe_dump(data, f)
        os.replace(tmp, path)


def _append_audit(self, event_type, payload):
    row = {
        'ts': self._now().isoformat(),
        'event_type': str(event_type),
        'payload': to_jsonable(payload),
    }
    try:
        ensure_parent(STORAGE_AUDIT_LOG)
        with open(STORAGE_AUDIT_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass

    def _disk_usage_pct(self):
        try:
            usage = shutil.disk_usage(DATA_DIR)
            used = usage.total - usage.free
            pct = (used / usage.total * 100.0) if usage.total else 0.0
            return round(pct, 2), usage.total, usage.free
        except Exception:
            return 0.0, 0, 0

    def _dir_size(self, path):
        total = 0
        try:
            for root, _, files in os.walk(path):
                for name in files:
                    fp = os.path.join(root, name)
                    try:
                        total += os.path.getsize(fp)
                    except Exception:
                        continue
        except Exception:
            return 0
        return total

    def _hot_warm_cold_sizes(self):
        hot = 0
        warm = 0
        cold = 0
        try:
            hot += self._dir_size(STATE_DIR)
            hot += sum(os.path.getsize(os.path.join(DATA_DIR, f)) for f in os.listdir(DATA_DIR) if os.path.isfile(os.path.join(DATA_DIR, f)) and not f.startswith('storage_'))
        except Exception:
            pass
        try:
            cold += self._dir_size(STORAGE_ARCHIVE_DIR)
        except Exception:
            pass
        warm = max(0, self._dir_size(DATA_DIR) - hot - cold)
        return hot, warm, cold

    def _state_name(self, usage_pct):
        if usage_pct >= STORAGE_THRESHOLDS['critical']:
            return 'critical'
        if usage_pct >= STORAGE_THRESHOLDS['pressure']:
            return 'pressure'
        if usage_pct >= STORAGE_THRESHOLDS['attention']:
            return 'attention'
        return 'normal'

    def _load_meta(self):
        if self.state_store:
            try:
                meta = self.state_store.get_json(self.audit_key, {})
                if isinstance(meta, dict):
                    return meta
            except Exception:
                pass
        return self._read_json(STORAGE_REPORT_FILE, {}) or {}

    def _save_meta(self, meta):
        meta = to_jsonable(meta)
        if self.state_store:
            try:
                self.state_store.set_json(self.audit_key, meta)
            except Exception:
                pass
        try:
            self._write_json(STORAGE_REPORT_FILE, meta)
        except Exception:
            pass

    def _estimate_days_to_pressure(self, usage_pct, prev_meta):
        try:
            prev_usage = self._safe_float(prev_meta.get('usage_pct'), usage_pct)
            prev_ts = prev_meta.get('measured_at')
            if not prev_ts:
                return None
            prev_dt = datetime.fromisoformat(prev_ts)
            elapsed_days = max(0.0001, (self._now() - prev_dt).total_seconds() / 86400.0)
            growth_per_day = (usage_pct - prev_usage) / elapsed_days
            if growth_per_day <= 0:
                return None
            remaining = max(0.0, STORAGE_THRESHOLDS['pressure'] - usage_pct)
            return round(remaining / growth_per_day, 1)
        except Exception:
            return None

    def _cleanup_old_files(self, max_age_days, suffixes):
        removed = []
        cutoff = time.time() - (max_age_days * 86400)
        for d in MONITORED_DIRS:
            if not os.path.isdir(d):
                continue
            for root, _, files in os.walk(d):
                for name in files:
                    if name in CRITICAL_FILES:
                        continue
                    if not any(name.endswith(s) for s in suffixes):
                        continue
                    fp = os.path.join(root, name)
                    try:
                        if os.path.getmtime(fp) <= cutoff:
                            size = os.path.getsize(fp)
                            os.remove(fp)
                            removed.append((fp, size))
                    except Exception:
                        continue
        return removed

    def _remove_pyc_and_caches(self):
        removed = []
        root = os.getcwd()
        for dirpath, dirnames, filenames in os.walk(root):
            if '__pycache__' in dirnames:
                cache_dir = os.path.join(dirpath, '__pycache__')
                try:
                    size = self._dir_size(cache_dir)
                    shutil.rmtree(cache_dir, ignore_errors=True)
                    removed.append((cache_dir, size))
                except Exception:
                    pass
            for name in filenames:
                if name.endswith('.pyc'):
                    fp = os.path.join(dirpath, name)
                    try:
                        size = os.path.getsize(fp)
                        os.remove(fp)
                        removed.append((fp, size))
                    except Exception:
                        continue
        return removed

    def _journal_summary(self, trade):
        return {
            'asset': trade.get('asset'),
            'date': trade.get('date'),
            'analysis_time': trade.get('analysis_time'),
            'entry_time': trade.get('entry_time'),
            'regime': trade.get('regime'),
            'strategy_name': trade.get('strategy_name'),
            'market_narrative': trade.get('market_narrative'),
            'trend_quality': trade.get('trend_quality'),
            'breakout_quality': trade.get('breakout_quality'),
            'conflict_type': trade.get('conflict_type'),
            'direction': trade.get('direction') or trade.get('signal'),
            'decision': trade.get('decision'),
            'score': trade.get('score'),
            'confidence': trade.get('confidence'),
            'result': trade.get('result'),
            'gross_pnl': trade.get('gross_pnl'),
            'suggested_stake': trade.get('suggested_stake'),
        }

    def _archive_old_journal_file(self):
        journal_path = os.path.join(DATA_DIR, 'alpha_hive_journal.json')
        rows = self._read_json(journal_path, [])
        if not isinstance(rows, list):
            return {'archived': 0, 'kept': 0, 'space_recovered': 0}
        keep_rows = RETENTION_POLICY['journal_detailed_keep_rows']
        min_batch = RETENTION_POLICY['journal_archive_batch_min']
        if len(rows) <= keep_rows + min_batch:
            return {'archived': 0, 'kept': len(rows), 'space_recovered': 0}
        archive_rows = rows[keep_rows:]
        kept_rows = rows[:keep_rows]
        archive_name = f"journal_archive_{self._now().strftime('%Y%m%d_%H%M%S')}.json.gz"
        archive_path = os.path.join(STORAGE_ARCHIVE_DIR, archive_name)
        before = os.path.getsize(journal_path) if os.path.exists(journal_path) else 0
        with gzip.open(archive_path, 'wt', encoding='utf-8') as gz:
            json.dump([self._journal_summary(r) for r in archive_rows], gz, ensure_ascii=False)
        self._write_json(journal_path, kept_rows)
        after = os.path.getsize(journal_path) if os.path.exists(journal_path) else 0
        recovered = max(0, before - after)
        self._append_audit('archive_journal_file', {'archived_rows': len(archive_rows), 'archive_path': archive_path, 'space_recovered': recovered})
        return {'archived': len(archive_rows), 'kept': len(kept_rows), 'space_recovered': recovered}

    def _prune_state_store(self):
        if not self.state_store:
            return {'scans_removed': 0, 'collections_pruned': {}}
        report = {'scans_removed': 0, 'collections_pruned': {}}
        try:
            removed = self.state_store.prune_scans(
                keep_latest=RETENTION_POLICY['scan_snapshots_keep_rows'],
                max_age_days=RETENTION_POLICY['scan_snapshots_max_age_days'],
            )
            report['scans_removed'] = int(removed or 0)
        except Exception:
            pass
        for name, keep in RETENTION_POLICY['collection_keep_latest'].items():
            try:
                removed = self.state_store.prune_collection(
                    collection_name=name,
                    keep_latest=int(keep),
                    max_age_days=int(RETENTION_POLICY['collection_max_age_days'].get(name, 90)),
                )
                report['collections_pruned'][name] = int(removed or 0)
            except Exception:
                report['collections_pruned'][name] = 0
        try:
            self.state_store.vacuum_if_sqlite()
        except Exception:
            pass
        return report

    def _cleanup_audit_log(self):
        if not os.path.exists(STORAGE_AUDIT_LOG):
            return 0
        keep_days = int(RETENTION_POLICY['report_keep_days'])
        cutoff = self._now() - timedelta(days=keep_days)
        kept = []
        removed = 0
        try:
            with open(STORAGE_AUDIT_LOG, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        row = json.loads(line)
                        ts = datetime.fromisoformat(str(row.get('ts')))
                        if ts >= cutoff:
                            kept.append(line)
                        else:
                            removed += 1
                    except Exception:
                        kept.append(line)
            with open(STORAGE_AUDIT_LOG + '.tmp', 'w', encoding='utf-8') as f:
                f.writelines(kept)
            os.replace(STORAGE_AUDIT_LOG + '.tmp', STORAGE_AUDIT_LOG)
        except Exception:
            return 0
        return removed

    def collect_report(self):
        prev = self._load_meta()
        usage_pct, total_bytes, free_bytes = self._disk_usage_pct()
        hot, warm, cold = self._hot_warm_cold_sizes()
        report = {
            'measured_at': self._now().isoformat(),
            'usage_pct': usage_pct,
            'state': self._state_name(usage_pct),
            'total_bytes': total_bytes,
            'free_bytes': free_bytes,
            'hot_data_size': hot,
            'warm_data_size': warm,
            'cold_data_size': cold,
            'estimated_days_to_pressure': self._estimate_days_to_pressure(usage_pct, prev),
            'last_cleanup': prev.get('last_cleanup'),
            'last_archive': prev.get('last_archive'),
            'last_integrity_check': prev.get('last_integrity_check'),
            'files_cleaned': prev.get('files_cleaned', 0),
            'files_archived': prev.get('files_archived', 0),
            'files_compressed': prev.get('files_compressed', 0),
            'space_recovered': prev.get('space_recovered', 0),
            'recommended_next_action': 'none',
        }
        state = report['state']
        if state == 'attention':
            report['recommended_next_action'] = 'preventive_cleanup'
        elif state == 'pressure':
            report['recommended_next_action'] = 'archive_and_cleanup'
        elif state == 'critical':
            report['recommended_next_action'] = 'critical_safe_mode'
        return report

    def run_maintenance(self, force=False):
        prev = self._load_meta()
        now_ts = time.time()
        min_interval = int(RETENTION_POLICY['maintenance_min_interval_seconds'])
        last_run_ts = self._safe_float(prev.get('last_run_ts'), 0.0)
        if not force and last_run_ts and (now_ts - last_run_ts) < min_interval:
            return self.collect_report()

        report = self.collect_report()
        cleaned = []
        pyc_removed = self._remove_pyc_and_caches()
        cleaned.extend(pyc_removed)
        cleaned.extend(self._cleanup_old_files(int(RETENTION_POLICY['tmp_max_age_days']), ('.tmp',)))
        cleaned.extend(self._cleanup_old_files(int(RETENTION_POLICY['log_max_age_days']), ('.log', '.jsonl.log')))

        archive_info = {'archived': 0, 'kept': 0, 'space_recovered': 0}
        store_info = {'scans_removed': 0, 'collections_pruned': {}}

        if report['state'] in ('attention', 'pressure', 'critical') or force:
            archive_info = self._archive_old_journal_file()
            store_info = self._prune_state_store()

        if report['state'] in ('pressure', 'critical'):
            # stronger cleanup under pressure
            cleaned.extend(self._cleanup_old_files(1, ('.tmp', '.bak')))

        audit_removed = self._cleanup_audit_log()
        space_recovered = sum(size for _, size in cleaned) + int(archive_info.get('space_recovered', 0) or 0)

        final = self.collect_report()
        final.update({
            'last_run_ts': now_ts,
            'last_cleanup': self._now().isoformat(),
            'last_archive': self._now().isoformat() if archive_info.get('archived', 0) else prev.get('last_archive'),
            'last_integrity_check': self._now().isoformat(),
            'files_cleaned': len(cleaned) + int(audit_removed or 0),
            'files_archived': int(archive_info.get('archived', 0) or 0),
            'files_compressed': 1 if archive_info.get('archived', 0) else 0,
            'space_recovered': int(space_recovered),
            'journal_archived_rows': int(archive_info.get('archived', 0) or 0),
            'journal_kept_rows': int(archive_info.get('kept', 0) or 0),
            'scans_removed': int(store_info.get('scans_removed', 0) or 0),
            'collections_pruned': store_info.get('collections_pruned', {}),
        })
        self._save_meta(final)
        self._append_audit('maintenance_run', final)
        return final

    def maybe_run_maintenance(self, scan_count=None, force=False):
        meta = self._load_meta()
        interval_scans = int(RETENTION_POLICY['maintenance_every_scans'])
        last_scan = self._safe_int(meta.get('last_maintenance_scan_count'), 0)
        if force:
            report = self.run_maintenance(force=True)
            report['last_maintenance_scan_count'] = int(scan_count or 0)
            self._save_meta(report)
            return report
        if scan_count is None:
            return self.run_maintenance(force=False)
        if int(scan_count) - last_scan >= interval_scans:
            report = self.run_maintenance(force=False)
            report['last_maintenance_scan_count'] = int(scan_count)
            self._save_meta(report)
            return report
        return self.collect_report()
