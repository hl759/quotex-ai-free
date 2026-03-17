import time, requests
from datetime import datetime
from config import TWELVE_API_KEYS, FINNHUB_API_KEY, ALPHA_VANTAGE_API_KEY, TWELVE_DAILY_SOFT_LIMIT_PER_KEY, TWELVE_MINUTE_LIMIT_PER_KEY, TWELVE_GLOBAL_DAILY_HARD_STOP, CACHE_TTL_1MIN, CACHE_TTL_5MIN, ECONOMY_MODE_AFTER_TOTAL, FREEZE_TWELVE_AFTER_TOTAL, FINNHUB_PAUSE_SECONDS, ALPHA_PAUSE_SECONDS
class DataManager:
    def __init__(self):
        self.cache={}; self.day_marker=datetime.utcnow().strftime("%Y-%m-%d"); self.credits_today=0; self.last_provider_used={}; self.twelve_frozen_for_day=False; self.twelve_pause_until_ts=0; self.finnhub_pause_until_ts=0; self.alpha_pause_until_ts=0; self.key_usage=[{"key":k,"daily":0,"minute":0,"minute_window_start":time.time()} for k in TWELVE_API_KEYS]
    def _reset_daily_if_needed(self):
        d=datetime.utcnow().strftime("%Y-%m-%d")
        if d!=self.day_marker:
            self.day_marker=d; self.credits_today=0; self.twelve_frozen_for_day=False; self.twelve_pause_until_ts=0; self.finnhub_pause_until_ts=0; self.alpha_pause_until_ts=0
            for i in self.key_usage: i["daily"]=0; i["minute"]=0; i["minute_window_start"]=time.time()
    def _reset_minute_windows_if_needed(self):
        n=time.time()
        for i in self.key_usage:
            if n-i["minute_window_start"]>=60: i["minute"]=0; i["minute_window_start"]=n
    def _is_crypto(self,s): return s.endswith(("USDT","BUSD","BTC","ETH","BNB"))
    def _ttl(self,interval): return CACHE_TTL_5MIN if interval=="5min" else CACHE_TTL_1MIN
    def _ck(self,p,s,i): return f"{p}:{s}:{i}"
    def _get(self,p,s,i):
        item=self.cache.get(self._ck(p,s,i))
        if not item or time.time()>item["expires_at"]: return None
        return item["data"]
    def _set(self,p,s,i,d): self.cache[self._ck(p,s,i)]={"data":d,"expires_at":time.time()+self._ttl(i)}
    def _to_twelve(self,s): return {"EURUSD":"EUR/USD","GBPUSD":"GBP/USD","USDJPY":"USD/JPY","AUDUSD":"AUD/USD","USDCAD":"USD/CAD","USDCHF":"USD/CHF","NZDUSD":"NZD/USD","EURJPY":"EUR/JPY","GBPJPY":"GBP/JPY","EURGBP":"EUR/GBP","GOLD":"XAU/USD","SILVER":"XAG/USD"}.get(s,s)
    def _to_finnhub(self,s): return {"EURUSD":"OANDA:EUR_USD","GBPUSD":"OANDA:GBP_USD","USDJPY":"OANDA:USD_JPY","AUDUSD":"OANDA:AUD_USD","USDCAD":"OANDA:USD_CAD","USDCHF":"OANDA:USD_CHF","NZDUSD":"OANDA:NZD_USD","EURJPY":"OANDA:EUR_JPY","GBPJPY":"OANDA:GBP_JPY","EURGBP":"OANDA:EUR_GBP"}.get(s)
    def _choose_twelve(self):
        self._reset_daily_if_needed(); self._reset_minute_windows_if_needed()
        if self.twelve_frozen_for_day or time.time()<self.twelve_pause_until_ts or self.credits_today>=FREEZE_TWELVE_AFTER_TOTAL:
            self.twelve_frozen_for_day=self.credits_today>=FREEZE_TWELVE_AFTER_TOTAL; return None
        a=[i for i,x in enumerate(self.key_usage) if x["daily"]<TWELVE_DAILY_SOFT_LIMIT_PER_KEY and x["minute"]<TWELVE_MINUTE_LIMIT_PER_KEY]
        if not a: return None
        a.sort(key=lambda idx:self.key_usage[idx]["daily"]); return a[0]
    def _consume(self,idx): self.key_usage[idx]["daily"]+=1; self.key_usage[idx]["minute"]+=1; self.credits_today+=1
    def _norm_twelve(self,vals): return [{"datetime":r.get("datetime"),"open":r.get("open"),"high":r.get("high"),"low":r.get("low"),"close":r.get("close"),"volume":r.get("volume","0")} for r in vals]
    def _norm_binance(self,rows):
        out=[]
        for it in rows: out.append({"datetime":datetime.utcfromtimestamp(it[0]/1000).strftime("%Y-%m-%d %H:%M:%S"),"open":str(it[1]),"high":str(it[2]),"low":str(it[3]),"close":str(it[4]),"volume":str(it[5])})
        out.reverse(); return out
    def _norm_finnhub(self,d):
        if d.get("s")!="ok" or not d.get("c"): return None
        out=[]
        for i in range(len(d["c"])): out.append({"datetime":datetime.utcfromtimestamp(d["t"][i]).strftime("%Y-%m-%d %H:%M:%S"),"open":str(d["o"][i]),"high":str(d["h"][i]),"low":str(d["l"][i]),"close":str(d["c"][i]),"volume":str(d["v"][i] if i<len(d["v"]) else 0)})
        out.reverse(); return out
    def _norm_alpha(self,d):
        ts=d.get("Time Series FX (1min)",{})
        if not ts: return None
        return [{"datetime":k,"open":v.get("1. open"),"high":v.get("2. high"),"low":v.get("3. low"),"close":v.get("4. close"),"volume":"0"} for k,v in list(ts.items())[:50]]
    def _fetch_binance(self,s,interval="1min",limit=50):
        c=self._get("binance",s,interval)
        if c: self.last_provider_used[s]="binance-cache"; return c
        try:
            r=requests.get("https://data-api.binance.vision/api/v3/klines",params={"symbol":s,"interval":"5m" if interval=="5min" else "1m","limit":limit},timeout=10); d=r.json()
            if not isinstance(d,list): return None
            c=self._norm_binance(d); self._set("binance",s,interval,c); self.last_provider_used[s]="binance"; return c
        except Exception: return None
    def _fetch_finnhub(self,s,interval="1min"):
        c=self._get("finnhub",s,interval)
        if c: self.last_provider_used[s]="finnhub-cache"; return c
        if not FINNHUB_API_KEY or time.time()<self.finnhub_pause_until_ts: return None
        sym=self._to_finnhub(s)
        if not sym: return None
        try:
            to_ts=int(time.time()); from_ts=to_ts-60*50
            r=requests.get("https://finnhub.io/api/v1/forex/candle",params={"symbol":sym,"resolution":"1","from":from_ts,"to":to_ts,"token":FINNHUB_API_KEY},timeout=10); d=r.json()
            if d.get("error"): self.finnhub_pause_until_ts=time.time()+FINNHUB_PAUSE_SECONDS; return None
            c=self._norm_finnhub(d)
            if not c: return None
            self._set("finnhub",s,interval,c); self.last_provider_used[s]="finnhub"; return c
        except Exception: self.finnhub_pause_until_ts=time.time()+FINNHUB_PAUSE_SECONDS; return None
    def _fetch_twelve(self,s,interval="1min",outputsize=50):
        c=self._get("twelve",s,interval)
        if c: self.last_provider_used[s]="twelve-cache"; return c
        self._reset_daily_if_needed(); self._reset_minute_windows_if_needed()
        if self.twelve_frozen_for_day or time.time()<self.twelve_pause_until_ts or self.credits_today>=TWELVE_GLOBAL_DAILY_HARD_STOP: self.twelve_frozen_for_day=self.credits_today>=TWELVE_GLOBAL_DAILY_HARD_STOP; return None
        idx=self._choose_twelve()
        if idx is None: return None
        try:
            r=requests.get("https://api.twelvedata.com/time_series",params={"symbol":self._to_twelve(s),"interval":interval,"outputsize":outputsize,"apikey":self.key_usage[idx]["key"]},timeout=10); d=r.json()
            if "values" not in d:
                msg=str(d.get("message","")).lower()
                if d.get("code")==429 and "for the day" in msg: self.twelve_frozen_for_day=True
                elif d.get("code")==429: self.twelve_pause_until_ts=time.time()+65
                return None
            c=self._norm_twelve(d["values"]); self._set("twelve",s,interval,c); self._consume(idx); self.last_provider_used[s]=f"twelve-key-{idx+1}"; return c
        except Exception: self.twelve_pause_until_ts=time.time()+30; return None
    def _fetch_alpha(self,s,interval="1min"):
        c=self._get("alpha",s,interval)
        if c: self.last_provider_used[s]="alpha-cache"; return c
        if not ALPHA_VANTAGE_API_KEY or time.time()<self.alpha_pause_until_ts or len(s)!=6: return None
        try:
            r=requests.get("https://www.alphavantage.co/query",params={"function":"FX_INTRADAY","from_symbol":s[:3],"to_symbol":s[3:],"interval":"1min","outputsize":"compact","apikey":ALPHA_VANTAGE_API_KEY},timeout=12); d=r.json()
            if "Note" in d or "Information" in d: self.alpha_pause_until_ts=time.time()+ALPHA_PAUSE_SECONDS; return None
            c=self._norm_alpha(d)
            if not c: return None
            self._set("alpha",s,interval,c); self.last_provider_used[s]="alpha"; return c
        except Exception: self.alpha_pause_until_ts=time.time()+ALPHA_PAUSE_SECONDS; return None
    def get_candles(self,s,interval="1min",outputsize=50):
        self._reset_daily_if_needed()
        if self._is_crypto(s): return self._fetch_binance(s,interval=interval,limit=outputsize)
        c=self._fetch_finnhub(s,interval=interval)
        if c: return c
        c=self._fetch_twelve(s,interval=interval,outputsize=30 if self.credits_today>=ECONOMY_MODE_AFTER_TOTAL else outputsize)
        if c: return c
        return self._fetch_alpha(s,interval=interval)
