import json, os
JOURNAL_FILE="/tmp/nexus_journal.json"
class JournalManager:
    def __init__(self):
        if not os.path.exists(JOURNAL_FILE):
            with open(JOURNAL_FILE,"w",encoding="utf-8") as f: json.dump([],f)
    def _load(self):
        try:
            with open(JOURNAL_FILE,"r",encoding="utf-8") as f: return json.load(f)
        except Exception: return []
    def _save(self,data):
        tmp=JOURNAL_FILE+".tmp"
        with open(tmp,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False)
        os.replace(tmp,JOURNAL_FILE)
    def _trade_id(self,trade): return f"{trade.get('asset')}-{trade.get('signal')}-{trade.get('analysis_time')}-{trade.get('entry_time')}-{trade.get('expiration')}"
    def _valid_trades(self): return [t for t in self._load() if t.get("result") in ("WIN","LOSS")]
    def _extract_hour_bucket(self, trade):
        try:
            analysis_time=str(trade.get("analysis_time","")).strip()
            if ":" not in analysis_time: return None
            hour=int(analysis_time.split(":")[0]); return f"{hour:02d}:00" if 0<=hour<=23 else None
        except Exception: return None
    def add_trade(self, trade):
        data=self._load(); incoming=self._trade_id(trade)
        for item in data:
            if self._trade_id(item)==incoming: return
        data.insert(0, trade)
        if len(data)>500: data=data[:500]
        self._save(data)
    def stats(self):
        valid=self._valid_trades()
        if not valid: return {"total":0,"wins":0,"loss":0,"winrate":0.0}
        wins=sum(1 for t in valid if t.get("result")=="WIN"); total=len(valid)
        return {"total":total,"wins":wins,"loss":total-wins,"winrate":round((wins/total)*100,2)}
    def asset_stats(self, asset):
        valid=[t for t in self._valid_trades() if t.get("asset")==asset]
        if not valid: return {"asset":asset,"total":0,"wins":0,"loss":0,"winrate":0.0}
        wins=sum(1 for t in valid if t.get("result")=="WIN"); total=len(valid)
        return {"asset":asset,"total":total,"wins":wins,"loss":total-wins,"winrate":round((wins/total)*100,2)}
    def best_assets(self):
        grouped={}
        for t in self._valid_trades():
            a=t.get("asset","N/A"); grouped.setdefault(a,{"asset":a,"total":0,"wins":0}); grouped[a]["total"]+=1
            if t.get("result")=="WIN": grouped[a]["wins"]+=1
        result=[]
        for info in grouped.values():
            if info["total"]==0: continue
            result.append({"asset":info["asset"],"total":info["total"],"wins":info["wins"],"winrate":round((info["wins"]/info["total"])*100,2)})
        result=[r for r in result if r["total"]>=3]; result.sort(key=lambda x:(x["winrate"],x["total"]), reverse=True)
        return result[:10]
    def hour_stats(self, hour_bucket):
        valid=[t for t in self._valid_trades() if self._extract_hour_bucket(t)==hour_bucket]
        if not valid: return {"hour":hour_bucket,"total":0,"wins":0,"loss":0,"winrate":0.0}
        wins=sum(1 for t in valid if t.get("result")=="WIN"); total=len(valid)
        return {"hour":hour_bucket,"total":total,"wins":wins,"loss":total-wins,"winrate":round((wins/total)*100,2)}
    def best_hours(self):
        grouped={}
        for t in self._valid_trades():
            hb=self._extract_hour_bucket(t)
            if not hb: continue
            grouped.setdefault(hb,{"hour":hb,"total":0,"wins":0}); grouped[hb]["total"]+=1
            if t.get("result")=="WIN": grouped[hb]["wins"]+=1
        result=[]
        for info in grouped.values():
            if info["total"]==0: continue
            result.append({"hour":info["hour"],"total":info["total"],"wins":info["wins"],"winrate":round((info["wins"]/info["total"])*100,2)})
        result=[r for r in result if r["total"]>=3]; result.sort(key=lambda x:(x["winrate"],x["total"]), reverse=True)
        return result[:10]
