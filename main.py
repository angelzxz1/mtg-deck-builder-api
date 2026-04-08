from fastapi import FastAPI, Query
from typing import List, Optional

from models import DeckRequest, DeckResponse, AlternativeCard
from services import build_advanced_deck_logic, get_alternatives_logic

app = FastAPI(title="MTG Smart Deck Builder API v3.0")


@app.post("/generate-deck", response_model=DeckResponse)
async def generate_deck(request: DeckRequest):
    return build_advanced_deck_logic(request)


@app.get("/get-alternatives", response_model=List[AlternativeCard])
async def get_alternatives(
    commander_name: str,
    role: str = Query(..., description="Ej: 'Removal', 'Ramp'"),
    max_price: float = 5.0,
    current_card_name: Optional[str] = None
):
    return get_alternatives_logic(commander_name, role, max_price, current_card_name)
