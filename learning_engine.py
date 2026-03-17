from journal_manager import JournalManager


class LearningEngine:
    def __init__(self):
        self.journal = JournalManager()

    def _normalize_hour_bucket(self, raw_hour):
        try:
            if raw_hour is None:
                return None

            if isinstance(raw_hour, int):
                hour = raw_hour
            else:
                text = str(raw_hour).strip()

                if ":" in text:
                    hour = int(text.split(":")[0])
                else:
                    hour = int(text)

            if hour < 0 or hour > 23:
                return None

            return f"{hour:02d}:00"
        except Exception:
            return None

    def get_adaptive_bonus(self, asset, *args, **kwargs):
        asset_bonus = 0
        hour_bonus = 0
        reasons = []

        # compatível com chamadas antigas e novas
        # exemplos:
        # get_adaptive_bonus(asset)
        # get_adaptive_bonus(asset, "14:00")
        # get_adaptive_bonus(asset, 14)
        # get_adaptive_bonus(asset, score, "14:00")
        hour_candidate = None

        for arg in args:
            normalized = self._normalize_hour_bucket(arg)
            if normalized is not None:
                hour_candidate = normalized
                break

        if hour_candidate is None:
            hour_candidate = self._normalize_hour_bucket(kwargs.get("hour"))

        asset_stats = self.journal.asset_stats(asset)
        asset_total = asset_stats.get("total", 0)
        asset_winrate = asset_stats.get("winrate", 0.0)

        if asset_total >= 5:
            if asset_winrate >= 65:
                asset_bonus = 2
                reasons.append("Ativo com win rate forte")
            elif asset_winrate >= 55:
                asset_bonus = 1
                reasons.append("Ativo com win rate favorável")
            elif asset_winrate <= 40:
                asset_bonus = -1
                reasons.append("Ativo com win rate fraco")

        if hour_candidate:
            hour_stats = self.journal.hour_stats(hour_candidate)
            hour_total = hour_stats.get("total", 0)
            hour_winrate = hour_stats.get("winrate", 0.0)

            if hour_total >= 5:
                if hour_winrate >= 65:
                    hour_bonus = 1
                    reasons.append("Horário forte")
                elif hour_winrate <= 40:
                    hour_bonus = -1
                    reasons.append("Horário fraco")

        total_bonus = asset_bonus + hour_bonus

        if not reasons:
            reasons.append("Histórico insuficiente")

        return total_bonus, " | ".join(reasons)

    def should_filter_asset(self, asset):
        stats = self.journal.asset_stats(asset)
        total = stats.get("total", 0)
        winrate = stats.get("winrate", 0.0)

        # filtro conservador: só corta quando já há histórico suficiente
        if total >= 12 and winrate <= 35:
            return True

        return False

    def update_stats(self, signals):
        # Mantido por compatibilidade com o restante da Nexus
        return

    def register_result(self, signal, result_data):
        trade = {
            "asset": signal.get("asset"),
            "signal": signal.get("signal"),
            "score": signal.get("score", 0),
            "confidence": signal.get("confidence", 0),
            "provider": signal.get("provider", "auto"),
            "analysis_time": signal.get("analysis_time", "--:--"),
            "entry_time": signal.get("entry_time", "--:--"),
            "expiration": signal.get("expiration", "--:--"),
            "entry_price": result_data.get("entry_price"),
            "exit_price": result_data.get("exit_price"),
            "result": result_data.get("result", "UNKNOWN"),
        }

        self.journal.add_trade(trade)

    def get_stats(self):
        return self.journal.stats()

    def get_best_assets(self):
        return self.journal.best_assets()

    def get_best_hours(self):
        return self.journal.best_hours()
