from journal_manager import JournalManager
class LearningEngine:
    def __init__(self): self.journal=JournalManager()
    def _extract_hour_bucket(self,*args,**kwargs):
        candidates=list(args)
        if "hour" in kwargs: candidates.append(kwargs.get("hour"))
        for value in candidates:
            try:
                if value is None: continue
                text=str(value).strip(); hour=int(text.split(":")[0] if ":" in text else text)
                if 0<=hour<=23: return f"{hour:02d}:00"
            except Exception: continue
        return None
    def get_adaptive_bonus(self, asset, *args, **kwargs):
        asset_bonus=0; hour_bonus=0; reasons=[]
        a=self.journal.asset_stats(asset)
        if a.get("total",0)>=5:
            wr=a.get("winrate",0.0)
            if wr>=65: asset_bonus=2; reasons.append("Ativo forte")
            elif wr>=55: asset_bonus=1; reasons.append("Ativo favorável")
            elif wr<=40: asset_bonus=-1; reasons.append("Ativo fraco")
        hb=self._extract_hour_bucket(*args, **kwargs)
        if hb:
            h=self.journal.hour_stats(hb)
            if h.get("total",0)>=5:
                wr=h.get("winrate",0.0)
                if wr>=65: hour_bonus=1; reasons.append("Horário forte")
                elif wr<=40: hour_bonus=-1; reasons.append("Horário fraco")
        if not reasons: reasons.append("Histórico insuficiente")
        return asset_bonus+hour_bonus, " | ".join(reasons)
    def should_filter_asset(self, asset):
        s=self.journal.asset_stats(asset)
        return bool(s.get("total",0)>=12 and s.get("winrate",0.0)<=35)
    def update_stats(self, signals): return
    def register_result(self, signal, result_data):
        self.journal.add_trade({"asset":signal.get("asset"),"signal":signal.get("signal"),"score":signal.get("score",0),"confidence":signal.get("confidence",0),"provider":signal.get("provider","auto"),"analysis_time":signal.get("analysis_time","--:--"),"entry_time":signal.get("entry_time","--:--"),"expiration":signal.get("expiration","--:--"),"entry_price":result_data.get("entry_price"),"exit_price":result_data.get("exit_price"),"result":result_data.get("result","UNKNOWN")})
