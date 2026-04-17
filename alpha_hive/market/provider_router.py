from __future__ import annotations

from typing import List

from alpha_hive.config import SETTINGS


class ProviderRouter:
    def provider_chain_for(self, symbol: str) -> List[str]:
        if symbol in SETTINGS.assets_pure_crypto:
            return ["yahoo"]

        if symbol in SETTINGS.assets_crypto:
            return ["binance", "yahoo"]

        if symbol in SETTINGS.assets_forex or symbol in SETTINGS.assets_metals:
            chain: List[str] = []
            if SETTINGS.finnhub_api_key:
                chain.append("finnhub")
            if SETTINGS.twelvedata_keys:
                chain.append("twelve")
            if SETTINGS.alpha_vantage_api_key:
                chain.append("alpha")
            chain.append("yahoo")
            return chain

        return ["yahoo"]
