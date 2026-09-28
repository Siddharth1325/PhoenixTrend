from .stock_automation import stock_automation
from .options_automation import options_automation
from .crypto_automation import crypto_automation
from .etf_automation import etf_automation
from .forex_automation import forex_automation
from .bond_automation import bond_automation

asset_automations = {
    "stocks": stock_automation,
    "options": options_automation,
    "crypto": crypto_automation,
    "etfs": etf_automation,
    "forex": forex_automation,
    "bonds": bond_automation,
}


def get_asset_automation(asset_class: str):
    key = (asset_class or "").strip().lower()
    aliases = {"stock": "stocks", "equity": "stocks", "option": "options", "crypto": "crypto", "etf": "etfs", "forex": "forex", "bond": "bonds"}
    key = aliases.get(key, key)
    return asset_automations.get(key)
