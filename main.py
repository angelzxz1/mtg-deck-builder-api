from fastapi import FastAPI, Query, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from models import DeckRequest, DeckResponse, AlternativeCard
from services import build_advanced_deck_logic, get_alternatives_logic
from database import get_db, DeckModel

app = FastAPI(title="MTG Smart Deck Builder API")


@app.post("/generate-deck", response_model=DeckResponse)
async def generate_deck(request: DeckRequest, db: Session = Depends(get_db)):
    return build_advanced_deck_logic(request, db)


@app.get("/decks", response_model=List[DeckResponse])
async def list_decks(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return db.query(DeckModel).offset(skip).limit(limit).all()


@app.get("/decks/{deck_id}", response_model=DeckResponse)
async def get_deck(deck_id: int, db: Session = Depends(get_db)):
    deck = db.query(DeckModel).filter(DeckModel.id == deck_id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    return deck


@app.get("/get-alternatives", response_model=List[AlternativeCard])
async def get_alternatives(commander_name: str, role: str = Query(..., description="Ej: 'Removal', 'Ramp'"), max_price: float = 5.0, current_card_name: str = None):
    return get_alternatives_logic(commander_name, role, max_price, current_card_name)
