import requests
import re
import io
import pandas as pd
import yfinance as yf
from collections import Counter
from functools import lru_cache
from openpyxl.utils import get_column_letter

from config import EXCHANGE_RATES

scryfall_cache = {}


@lru_cache(maxsize=10)
def get_exchange_rate(currency_code: str) -> float:
    currency_code = currency_code.upper()
    if currency_code == "USD":
        return 1.0
    try:
        ticker = yf.Ticker(f"{currency_code}=X")
        history = ticker.history(period="1d")
        if not history.empty:
            return float(history['Close'].iloc[-1])
    except Exception as e:
        print(f"⚠️ Error fetching rate for {currency_code}: {e}")
    return EXCHANGE_RATES.get(currency_code, 1.0)


def get_scryfall_data(card_name):
    if card_name in scryfall_cache:
        return scryfall_cache[card_name]
    try:
        response = requests.get(
            "https://api.scryfall.com/cards/named", params={"fuzzy": card_name})
        if response.status_code == 200:
            data = response.json()
            colors = data.get("colors", []) or data.get("color_identity", [])
            processed = {
                "name": data.get("name"), "mana_cost": data.get("mana_cost", ""),
                "cmc": data.get("cmc", 0.0), "colors": colors, "type_line": data.get("type_line", ""),
                "price_usd": float(data.get("prices", {}).get("usd") or 0),
                "image_url": data.get("image_uris", {}).get("normal") or data.get("card_faces", [{}])[0].get("image_uris", {}).get("normal")
            }
            scryfall_cache[card_name] = processed
            return processed
    except Exception:
        pass
    return None


def count_mana_pips(mana_cost_str):
    if not mana_cost_str:
        return Counter()
    clean = re.sub(r'\{\d+\}', '', mana_cost_str).replace('{X}', '')
    cnt = Counter()
    for color in ['W', 'U', 'B', 'R', 'G']:
        cnt[color] += clean.count(f'{{{color}}}')
    return cnt


def parse_type_line(type_line_raw):
    if not type_line_raw:
        return "N/A"
    clean = type_line_raw.split("—")[0].replace(
        "Legendary", "").replace("Snow", "").replace("World", "").strip()
    for t in ["Creature", "Land", "Artifact", "Enchantment", "Instant", "Sorcery", "Planeswalker"]:
        if t in clean:
            return t
    return clean


def format_excel_in_memory(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Smart_Deck", index=False)
        worksheet = writer.sheets["Smart_Deck"]
        for idx, col in enumerate(df.columns):
            max_len = max((df[col].astype(str).map(len).max(), len(col))) + 4
            worksheet.column_dimensions[get_column_letter(
                idx + 1)].width = max_len
    output.seek(0)
    return output.read()
