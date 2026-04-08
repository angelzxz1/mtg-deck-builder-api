from typing import List, Dict, Optional
from pydantic import BaseModel, ConfigDict


class DeckRequest(BaseModel):
    commander_name: str
    budget: float = 60.0
    max_single_card: float = 5.0
    currency: str = "USD"
    archetype: str = "Balanced"
    owned_cards: List[str] = []


class CardInfo(BaseModel):
    name: str
    role: str
    type: str
    mana_cost: str
    cmc: float
    price_usd: float
    price_local: float
    image_url: str
    model_config = ConfigDict(from_attributes=True)  # Para SQLAlchemy


class Analytics(BaseModel):
    mana_curve: Dict[str, int]
    color_distribution: Dict[str, int]
    total_cmc: float
    model_config = ConfigDict(from_attributes=True)


class DeckResponse(BaseModel):
    id: Optional[int] = None  # Agregado para la base de datos
    commander: str
    archetype_used: str
    final_budget_usd: float
    currency: str
    total_price_local: float
    analytics: Analytics
    export_text: str
    excel_base64: str
    deck_list: List[CardInfo]
    message: str
    model_config = ConfigDict(from_attributes=True)  # Para SQLAlchemy


class AlternativeCard(BaseModel):
    name: str
    price_usd: float
    synergy: float
    image_url: str
