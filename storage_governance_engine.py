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
    """
    Governança de armazenamento integrada à IA.

    Compatibilidade obrigatória com o app atual:
    - maybe_run_maintenance(scan_count=None, force=False)
    - collect_report()
    """

    def __init__(self, state_store=None):
        self.state_store = state_store
        self.audit_key = "storage_governance_meta"
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(STATE_DIR, exist_ok=True)
        os.makedirs(STORAGE_ARCHIVE_DIR, exist_ok=True)
        ensure_parent(STORAGE_AUDIT_LOG)
        ensure_parent(STORAGE_REPORT_FILE)

    # =========================
    # Helpers básicos
    # =========================
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
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _write_json(self, path, data):
        tmp = path + ".tmp"
        ensure_parent(path)
        with open(tmp, "w", encoding="utf-8") as f:
            safe_dump(to_jsonable(data), f)
        os.replace(tmp, path)

    def _append_audit(self, event_type, payload):
        row = {
            "ts": self._now().isoformat(),
            "event_type": str(event_type),
            "payload": to_jsonable(payload),
        }
        try:
            ensure_parent(STORAGE_AUDIT_LOG)
            with open(STORAGE_AUDIT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # =========================
    # Métricas de armazenamento
    # =========================
    def _disk_usage_pct(self):
        try:
            usage = shutil.disk_usage(DATA_DIR)
            used = usage.total - usage.free
            pct = (used / usage.total * 100.0) if usage.total else 0.0
            return round(pct, 2), int(usage.total), int(usage.free)
        except Exception:
            return 0.0, 0, 0

    def _dir_size(self, path):
        total = 0
        try:
            if not os.path.exists(path):
                return 0
            for root, _, files in os.walk(path):
                for name in files:
                    fp = os.path.join(root, name)
                    try:
                        total += os.path.getsize(fp)
                    except Exception:
                        continue
        except Exception:
            return 0
        return int(total)

    def _hot_warm_cold_sizes(self):
        hot = 0
        warm = 0
        cold = 0

        try:
            # hot: state + arquivos ativos em DATA_DIR
            hot += self._dir_size(STATE_DIR)
            for f in os.listdir(DATA_DIR):
                fp = os.path.join(DATA_DIR, f)
                if os.path.isfile(fp) and f not in (
                    os.path.basename(STORAGE_AUDIT_LOG),
                    os.path.basename(STORAGE_REPORT_FILE),
                ):
                    if not fp.startswith(STORAGE_ARCHIVE_DIR):
                        hot += os.path.getsize(fp)
        except Exception:
            pass

        try:
            cold += self._dir_size(STORAGE_ARCHIVE_DIR)
        except Exception:
            pass

        total_data = self._dir_size(DATA_DIR)
        warm = max(0, total_data - hot - cold)
        return int(hot), int(warm), int(cold)

    def _state_name(self, usage_pct):
        if usage_pct >= STORAGE_THRESHOLDS.get("critical", 90):
            return "critical"
        if usage_pct >= STORAGE_THRESHOLDS.get("pressure", 85):
            return "pressure"
        if usage_pct >= STORAGE_THRESHOLDS.get("attention", 75):
            return "attention"
        return "normal"

    # =========================
    # Persistência de meta/report
    # =========================
    def _load_meta(self):
        if self.state_store:
            try:
                meta = self.state_store.get_json(self.audit_key, {})
                if isinstance(meta, dict):
                    return meta
            except Exception:
                pass
        meta = self._read_json(STORAGE_REPORT_FILE, {}) or {}
        return meta if isinstance(meta, dict) else {}

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
            prev_usage = self._safe_float(prev_meta.get("usage_pct"), usage_pct)
            prev_ts = prev_meta.get("measured_at")
            if not prev_ts:
                return None
            prev_dt = datetime.fromisoformat(prev_ts)
            elapsed_days = max(0.0001, (self._now() - prev_dt).total_seconds() / 86400.0)
            growth_per_day = (usage_pct - prev_usage) / elapsed_days
            if growth_per_day <= 0:
                return None
            remaining = max(0.0, STORAGE_THRESHOLDS.get("pressure", 85) - usage_pct)
            return round(remaining / growth_per_day, 1)
        except Exception:
            return None

    # =========================
    # Limpeza
    # =========================
    def _cleanup_old_files(self, max_age_days, suffixes):
        removed = []
        cutoff = time.time() - (max(1, int(max_age_days or 1)) * 86400)

        for directory in MONITORED_DIRS:
            try:
                if not os.path.exists(directory):
                    continue
                for root, dirs, files in os.walk(directory):
                    # limpa __pycache__
                    for d in list(dirs):
                        if d == "__pycache__":
                            full = os.path.join(root, d)
                            try:
                                shutil.rmtree(full, ignore_errors=True)
                                removed.append(full)
                            except Exception:
                                pass

                    for name in files:
                        fp = os.path.join(root, name)
                        rel_name = os.path.basename(fp)

                        if rel_name in CRITICAL_FILES:
                            continue
                        if fp.startswith(STORAGE_ARCHIVE_DIR):
                            continue
                        if os.path.basename(fp) in (
                            os.path.basename(STORAGE_AUDIT_LOG),
                            os.path.basename(STORAGE_REPORT_FILE),
                        ):
                            continue

                        lower = rel_name.lower()
                        if not any(lower.endswith(suf.lower()) for suf in suffixes):
                            continue

                        try:
                            if os.path.getmtime(fp) < cutoff:
                                os.remove(fp)
                                removed.append(fp)
                        except Exception:
                            continue
            except Exception:
                continue

        return removed

    def _prune_state_store(self):
        stats = {
            "scans_removed": 0,
            "journal_trades_removed": 0,
            "trade_ledger_removed": 0,
            "vacuumed": False,
        }
        if not self.state_store:
            return stats

        try:
            stats["scans_removed"] = int(
                self.state_store.prune_scans(
                    keep_latest=RETENTION_POLICY.get("scan_snapshots_keep_rows", 1200),
                    max_age_days=RETENTION_POLICY.get("scan_snapshots_max_age_days", 14),
                ) or 0
            )
        except Exception:
            pass

        for collection_name, keep_latest in (RETENTION_POLICY.get("collection_keep_latest", {}) or {}).items():
            try:
                max_age_days = (RETENTION_POLICY.get("collection_max_age_days", {}) or {}).get(collection_name, 90)
                removed = self.state_store.prune_collection(
                    collection_name=collection_name,
                    keep_latest=keep_latest,
                    max_age_days=max_age_days,
                )
                stats[f"{collection_name}_removed"] = int(removed or 0)
            except Exception:
                continue

        try:
            stats["vacuumed"] = bool(self.state_store.vacuum_if_sqlite())
        except Exception:
            pass

        return stats

    # =========================
    # Arquivamento do journal
    # =========================
    def _archive_old_journal_rows(self):
        journal_path = os.path.join(DATA_DIR, "alpha_hive_journal.json")
        if not os.path.exists(journal_path):
            return {"archived_rows": 0, "archive_file": None}

        rows = self._read_json(journal_path, [])
        if not isinstance(rows, list) or not rows:
            return {"archived_rows": 0, "archive_file": None}

        keep_rows = max(100, int(RETENTION_POLICY.get("journal_detailed_keep_rows", 2500)))
        batch_min = max(100, int(RETENTION_POLICY.get("journal_archive_batch_min", 500)))
        max_age_days = max(1, int(RETENTION_POLICY.get("journal_archive_max_age_days", 45)))
        cutoff = self._now() - timedelta(days=max_age_days)

        old_rows = []
        keep_candidates = []

        for row in rows:
            ts = None
            for key in ("created_at", "ts", "resolved_at", "analysis_time"):
                raw = row.get(key) if isinstance(row, dict) else None
                if not raw:
                    continue
                try:
                    ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00").replace("+00:00", ""))
                    break
                except Exception:
                    continue
            if ts and ts < cutoff:
                old_rows.append(row)
            else:
                keep_candidates.append(row)

        # nunca desmontar o histórico ativo: só arquiva se houver batch relevante
        if len(old_rows) < batch_min and len(rows) <= keep_rows:
            return {"archived_rows": 0, "archive_file": None}

        # Se ainda estiver grande demais, manda excedente antigo para arquivo também
        if len(keep_candidates) > keep_rows:
            overflow = keep_candidates[:-keep_rows]
            old_rows.extend(overflow)
            keep_candidates = keep_candidates[-keep_rows:]

        if len(old_rows) < batch_min:
            return {"archived_rows": 0, "archive_file": None}

        stamp = self._now().strftime("%Y%m%d_%H%M%S")
        archive_file = os.path.join(STORAGE_ARCHIVE_DIR, f"alpha_hive_journal_{stamp}.jsonl.gz")
        ensure_parent(archive_file)

        with gzip.open(archive_file, "wt", encoding="utf-8") as gz:
            for row in old_rows:
                gz.write(json.dumps(to_jsonable(row), ensure_ascii=False) + "\n")

        self._write_json(journal_path, keep_candidates)

        return {"archived_rows": len(old_rows), "archive_file": archive_file}

    # =========================
    # Relatório
    # =========================
    def collect_report(self):
        prev_meta = self._load_meta()
        usage_pct, total_bytes, free_bytes = self._disk_usage_pct()
        hot, warm, cold = self._hot_warm_cold_sizes()
        state = self._state_name(usage_pct)
        growth_days = self._estimate_days_to_pressure(usage_pct, prev_meta)

        report = {
            "status": "ok",
            "measured_at": self._now().isoformat(),
            "usage_pct": usage_pct,
            "storage_state": state,
            "growth_trend": "rising" if growth_days is not None else "stable",
            "estimated_days_to_pressure": growth_days,
            "total_bytes": int(total_bytes),
            "free_bytes": int(free_bytes),
            "hot_data_size": hot,
            "warm_data_size": warm,
            "cold_data_size": cold,
            "files_cleaned": self._safe_int(prev_meta.get("files_cleaned"), 0),
            "files_archived": self._safe_int(prev_meta.get("files_archived"), 0),
            "files_compressed": self._safe_int(prev_meta.get("files_compressed"), 0),
            "space_recovered": self._safe_int(prev_meta.get("space_recovered"), 0),
            "last_cleanup": prev_meta.get("last_cleanup"),
            "last_archive": prev_meta.get("last_archive"),
            "last_integrity_check": prev_meta.get("last_integrity_check"),
            "next_recommended_action": "none",
            "recommended_actions": [],
            "scan_count_seen": self._safe_int(prev_meta.get("scan_count_seen"), 0),
        }

        if state == "attention":
            report["next_recommended_action"] = "preventive_cleanup"
            report["recommended_actions"].append("light_cleanup")
        elif state == "pressure":
            report["next_recommended_action"] = "archive_and_cleanup"
            report["recommended_actions"].extend(["light_cleanup", "archive_old_journal", "prune_state"])
        elif state == "critical":
            report["next_recommended_action"] = "aggressive_pressure_relief"
            report["recommended_actions"].extend(["light_cleanup", "archive_old_journal", "prune_state", "vacuum"])

        self._save_meta({**prev_meta, **report})
        return report

    def get_health_report(self, force=False, scan_count=None):
        if force:
            return self.maybe_run_maintenance(scan_count=scan_count, force=True)
        return self.collect_report()

    # =========================
    # Manutenção principal
    # =========================
    def maybe_run_maintenance(self, scan_count=None, force=False):
        prev_meta = self._load_meta()
        now = self._now()

        every_scans = max(1, int(RETENTION_POLICY.get("maintenance_every_scans", 25)))
        min_interval = max(60, int(RETENTION_POLICY.get("maintenance_min_interval_seconds", 900)))

        last_run_scan = self._safe_int(prev_meta.get("last_maintenance_scan"), 0)
        last_run_ts = prev_meta.get("last_maintenance_at")
        seconds_since_last = None
        if last_run_ts:
            try:
                seconds_since_last = (now - datetime.fromisoformat(last_run_ts)).total_seconds()
            except Exception:
                seconds_since_last = None

        due_by_scan = scan_count is not None and (int(scan_count) - last_run_scan) >= every_scans
        due_by_time = seconds_since_last is None or seconds_since_last >= min_interval

        report = self.collect_report()
        storage_state = report.get("storage_state", "normal")

        should_run = force or ((due_by_scan or due_by_time) and storage_state in ("attention", "pressure", "critical"))
        if not should_run:
            report["maintenance_status"] = "skipped"
            report["maintenance_reason"] = "not_due_or_not_needed"
            return report

        before_usage, _, before_free = self._disk_usage_pct()
        files_cleaned = 0
        files_archived = 0
        files_compressed = 0

        removed_tmp = self._cleanup_old_files(
            max_age_days=RETENTION_POLICY.get("tmp_max_age_days", 2),
            suffixes=[".tmp", ".temp", ".pyc", ".log"],
        )
        files_cleaned += len(removed_tmp)

        # limpeza de audit logs antigos não essenciais
        try:
            if os.path.exists(STORAGE_AUDIT_LOG):
                keep_days = max(7, int(RETENTION_POLICY.get("report_keep_days", 45)))
                cutoff = time.time() - (keep_days * 86400)
                if os.path.getmtime(STORAGE_AUDIT_LOG) < cutoff and os.path.getsize(STORAGE_AUDIT_LOG) > 2_000_000:
                    stamp = now.strftime("%Y%m%d_%H%M%S")
                    archive_audit = os.path.join(STORAGE_ARCHIVE_DIR, f"storage_audit_{stamp}.jsonl.gz")
                    with open(STORAGE_AUDIT_LOG, "rb") as src, gzip.open(archive_audit, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    with open(STORAGE_AUDIT_LOG, "w", encoding="utf-8") as f:
                        f.write("")
                    files_archived += 1
                    files_compressed += 1
        except Exception:
            pass

        journal_archive = self._archive_old_journal_rows()
        files_archived += 1 if journal_archive.get("archive_file") else 0
        files_compressed += 1 if journal_archive.get("archive_file") else 0

        prune_stats = self._prune_state_store()
        after_usage, _, after_free = self._disk_usage_pct()
        recovered = max(0, int(after_free - before_free))

        meta = {
            **prev_meta,
            "measured_at": now.isoformat(),
            "last_cleanup": now.isoformat(),
            "last_archive": now.isoformat() if journal_archive.get("archive_file") else prev_meta.get("last_archive"),
            "last_integrity_check": now.isoformat(),
            "last_maintenance_at": now.isoformat(),
            "last_maintenance_scan": self._safe_int(scan_count, self._safe_int(prev_meta.get("last_maintenance_scan"), 0)),
            "files_cleaned": self._safe_int(prev_meta.get("files_cleaned"), 0) + files_cleaned,
            "files_archived": self._safe_int(prev_meta.get("files_archived"), 0) + files_archived,
            "files_compressed": self._safe_int(prev_meta.get("files_compressed"), 0) + files_compressed,
            "space_recovered": self._safe_int(prev_meta.get("space_recovered"), 0) + recovered,
            "scan_count_seen": self._safe_int(scan_count, self._safe_int(prev_meta.get("scan_count_seen"), 0)),
        }
        self._save_meta(meta)

        payload = {
            "before_usage_pct": before_usage,
            "after_usage_pct": after_usage,
            "files_cleaned": files_cleaned,
            "files_archived": files_archived,
            "files_compressed": files_compressed,
            "space_recovered": recovered,
            "journal_archive": journal_archive,
            "prune_stats": prune_stats,
        }
        self._append_audit("maintenance", payload)

        report = self.collect_report()
        report["maintenance_status"] = "executed"
        report["maintenance_reason"] = "forced" if force else "due"
        report["maintenance_details"] = payload
        return report
