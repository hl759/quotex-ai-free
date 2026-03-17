from datetime import datetime, timedelta, timezone
BRAZIL_TZ = timezone(timedelta(hours=-3))
class SignalEngine:
    def __init__(self, learning_engine): self.learning_engine=learning_engine
    def score_signal(self, asset_name, ind):
        score=0; reasons=[]
        trend=ind.get("trend"); rsi=ind.get("rsi",50); pattern=ind.get("pattern"); volatility=ind.get("volatility",False)
        if trend=="bull": score+=2; reasons.append("Tendência de alta alinhada")
        elif trend=="bear": score+=2; reasons.append("Tendência de baixa alinhada")
        if rsi<30: score+=1; reasons.append("RSI em sobrevenda")
        elif rsi>70: score+=1; reasons.append("RSI em sobrecompra")
        if pattern=="bullish": score+=1; reasons.append("Padrão de candle bullish")
        elif pattern=="bearish": score+=1; reasons.append("Padrão de candle bearish")
        if volatility: score+=1; reasons.append("Volatilidade presente")
        bonus, reason=self.learning_engine.get_adaptive_bonus(asset_name, datetime.now(BRAZIL_TZ).strftime("%H:%M"))
        score+=bonus
        if bonus!=0: reasons.append(reason)
        if score<0: score=0
        return score, reasons
    def calculate_confidence(self, score):
        c=50+(score*10)
        return 95 if c>95 else c
    def generate_signals(self, market_data):
        signals=[]
        for asset in market_data:
            score, reasons=self.score_signal(asset["asset"], asset["indicators"])
            if score>=4:
                trend=asset["indicators"].get("trend","bull"); pattern=asset["indicators"].get("pattern","")
                signal="PUT" if (trend=="bear" or pattern=="bearish") else "CALL"
                signals.append({"asset":asset["asset"],"signal":signal,"score":score,"confidence":self.calculate_confidence(score),"provider":asset.get("provider","auto"),"reason":reasons})
        signals.sort(key=lambda x:(x["score"],x["confidence"]), reverse=True)
        return signals[:5]
