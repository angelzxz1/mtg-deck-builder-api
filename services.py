import base64
import pandas as pd
from collections import Counter
from pyedhrec import EDHRec
from fastapi import HTTPException
from sqlalchemy.orm import Session

from config import DECK_ARCHETYPES
from models import DeckResponse, Analytics, CardInfo, AlternativeCard, DeckRequest
from utils import get_scryfall_data, count_mana_pips, parse_type_line, format_excel_in_memory, get_exchange_rate
from database import DeckModel


class DeckBuilderService:
    def __init__(self, request: DeckRequest, db: Session = None):
        self.req = request
        self.db = db
        self.edh = EDHRec()
        self.ratios = DECK_ARCHETYPES.get(
            request.archetype, DECK_ARCHETYPES["Balanced"])
        self.rate = get_exchange_rate(request.currency)
        self.owned_set = {x.lower() for x in request.owned_cards}

        self.deck = []
        self.seen_names = set()
        self.current_cost = 0.0
        self.mana_pips = Counter()
        self.cmc_curve = Counter()
        self.color_dist = Counter()
        self.all_cards_map = {}
        self.commander_colors = []

    def generate(self) -> DeckResponse:
        self._fetch_data()
        self.seen_names.add(self.req.commander_name)
        self._build_spells_phase()
        self._build_lands_phase()
        response = self._construct_response()

        # --- 🛡️ CORRECCIÓN: GUARDADO A PRUEBA DE FALLOS ---
        if self.db:
            try:
                db_deck = self._save_to_db(response)
                response.id = db_deck.id
            except Exception as e:
                print(f"⚠️ Error guardando en BD (ignorado): {e}")

        return response

    def _fetch_data(self):
        try:
            self.all_cards_map = self.edh.get_commander_cards(
                self.req.commander_name)
        except Exception:
            raise HTTPException(
                status_code=404, detail="Commander not found on EDHRec")
        cmd_data = get_scryfall_data(self.req.commander_name)
        self.commander_colors = cmd_data.get("colors", []) if cmd_data else []

    def _add_single_card(self, name: str, role: str, is_land_slot: bool = False, force_budget_bypass: bool = False, ignore_single_limit: bool = False) -> bool:
        if name in self.seen_names: return False
        data = get_scryfall_data(name)
        if not data: return False

        type_line = parse_type_line(data["type_line"])
        is_actual_land = "Land" in type_line and "Double Faced" not in data.get("type_line", "")
        if not is_land_slot and is_actual_land: return False

        real_price = data["price_usd"]
        is_owned = name.lower() in self.owned_set
        
        actual_cost_to_add = 0.0 if is_owned else real_price

        # Filtros Inteligentes
        if not is_owned:
            # 1. Filtro de precio individual (se puede ignorar en Fase Upgrade)
            if not ignore_single_limit and real_price > self.req.max_single_card: 
                return False
            # 2. Filtro de presupuesto total (se puede ignorar en Fase Emergencia)
            if not is_land_slot and not force_budget_bypass:
                if self.current_cost + actual_cost_to_add > self.req.budget: 
                    return False

        self.current_cost += actual_cost_to_add
        self.seen_names.add(name)
        
        if not is_actual_land: self.cmc_curve[str(int(data["cmc"]))] += 1
        for c in data["colors"]: self.color_dist[c] += 1
        self.mana_pips.update(count_mana_pips(data["mana_cost"]))

        self.deck.append({
            "Role": role, "Card Name": data["name"], "Type": type_line, "Mana Cost": data["mana_cost"],
            "CMC": data["cmc"], "Price (USD)": real_price, "Price (Local)": real_price * self.rate,
            "Image URL": data["image_url"]
        })
        return True

    def _build_spells_phase(self):
        target_spells = 99 - self.ratios["lands"]
        premium_pool = [] 
        
        # Staples y Cuotas (Igual que antes...)
        for c in ["Sol Ring", "Arcane Signet", "Commander's Sphere", "Mind Stone"]: self._add_single_card(c, "Ramp (Core)")
        for c in ["Lightning Greaves", "Swiftfoot Boots"]: self._add_single_card(c, "Protection")
        
        self._fill_category_quota(self.ratios["ramp"], "Ramp", ["Mana Artifacts", "Ramp"])
        self._fill_category_quota(self.ratios["draw"], "Draw", ["Draw", "Card Draw"])
        self._fill_category_quota(self.ratios["removal"], "Removal", ["Removal", "Instants", "Sorceries"])
        
        # Sinergia
        synergy_cats = ["Instants", "Sorceries", "High Synergy"] if self.req.archetype == "Spellslinger" else ["High Synergy", "Creatures", "Planeswalkers", "Enchantments", "Top Cards"]
        
        candidates = []
        for cat in synergy_cats:
            if cat in self.all_cards_map: candidates.extend(self.all_cards_map[cat])

        # Primer pase: Cartas que cumplen todo
        for c in candidates:
            if len(self.deck) >= target_spells: break
            data = get_scryfall_data(c['name'])
            if not data or "Land" in data["type_line"]: continue
            
            if data["price_usd"] <= self.req.max_single_card:
                self._add_single_card(c['name'], "Synergy")
            else:
                if data["price_usd"] <= (self.req.max_single_card * 3):
                    premium_pool.append(c['name'])

        # Segundo pase: Gastar presupuesto sobrante (Upgrade)
        if len(self.deck) < target_spells:
            premium_pool.sort(key=lambda n: get_scryfall_data(n).get("price_usd", 999))
            for name in premium_pool:
                if len(self.deck) >= target_spells: break
                self._add_single_card(name, "Synergy (Upgrade)", ignore_single_limit=True)

        # Tercer pase: Relleno de emergencia (Cualquier cosa barata para llegar a 99)
        if len(self.deck) < target_spells:
            for c in candidates:
                if len(self.deck) >= target_spells: break
                # Forzamos entrada ignorando budget para que el mazo NO sea corto
                self._add_single_card(c['name'], "Synergy (Filler)", force_budget_bypass=True)

    def _fill_category_quota(self, quota: int, role_prefix: str, categories: list):
        needed = quota - \
            len([x for x in self.deck if x['Role'].startswith(role_prefix)])
        if needed <= 0:
            return
        candidates = []
        for cat in categories:
            if cat in self.all_cards_map:
                candidates.extend(self.all_cards_map[cat])
        if "Top Cards" in self.all_cards_map:
            candidates.extend(self.all_cards_map["Top Cards"])
        for c in candidates:
            if needed <= 0:
                break
            if "Basic Land" not in c.get("type_line", "") and self._add_single_card(c['name'], role_prefix):
                needed -= 1

    def _build_lands_phase(self):
        needed_lands = self.ratios["lands"]
        rem_budget = max(0, self.req.budget - self.current_cost)

        if len(self.commander_colors) > 1:
            for c in ["Command Tower", "Exotic Orchard", "Path of Ancestry"]:
                self._add_single_card(c, "Land (Fixing)", is_land_slot=True)

        limit_utility = needed_lands - 5
        if "Lands" in self.all_cards_map:
            for c in self.all_cards_map["Lands"]:
                if len([x for x in self.deck if "Land" in x["Type"]]) >= limit_utility:
                    break
                self._add_single_card(
                    c['name'], "Land (Utility/Dual)", is_land_slot=True)

        self._fill_basic_lands(needed_lands)

    def _fill_basic_lands(self, total_land_slots: int):
        current_lands = sum(c.get("Quantity", 1) for c in self.deck if "Land" in c["Type"])
        needed = total_land_slots - current_lands
        if needed <= 0: return

        b_map = {'W': 'Plains', 'U': 'Island', 'B': 'Swamp', 'R': 'Mountain', 'G': 'Forest', 'C': 'Wastes'}
        total_pips = sum(self.mana_pips.values())

        if total_pips > 0:
            # Reparto basado en símbolos encontrados
            for color, count in self.mana_pips.items():
                if color in b_map:
                    num = int(needed * (count / total_pips)) # Usamos int para no pasarnos
                    if num > 0: self._add_basic_land_entry(b_map[color], num)
        else:
            # --- 🛡️ PROTECCIÓN: Si no hay pips, repartir entre colores del comandante ---
            colors = self.commander_colors if self.commander_colors else ['C']
            share = needed // len(colors)
            for color in colors:
                if color in b_map: self._add_basic_land_entry(b_map[color], share)

        # Ajuste final para llegar exactamente a 100 cartas
        current_total = len(self.deck) + sum(c.get("Quantity", 1) - 1 for c in self.deck if "Quantity" in c)
        missing = 99 - current_total
        
        if missing > 0:
            # Añadir el resto al color principal (o al primero del comandante)
            main_color = self.mana_pips.most_common(1)[0][0] if total_pips > 0 else (self.commander_colors[0] if self.commander_colors else 'C')
            self._add_basic_land_entry(b_map.get(main_color, "Island"), missing)

    def _add_basic_land_entry(self, name: str, qty: int):
        for c in self.deck:
            if c["Card Name"] == name and c["Role"] == "Land (Basic)":
                c["Quantity"] = c.get("Quantity", 1) + qty
                return
        self.deck.append({"Role": "Land (Basic)", "Card Name": name, "Type": "Basic Land", "Mana Cost": "",
                         "CMC": 0.0, "Price (USD)": 0.0, "Price (Local)": 0.0, "Image URL": "", "Quantity": qty})

    def _construct_response(self) -> DeckResponse:
        spells = [c for c in self.deck if "Land" not in c["Type"]]
        visual_list, export_txt, df = self._format_lists()
        return DeckResponse(
            commander=self.req.commander_name, archetype_used=self.req.archetype, final_budget_usd=self.current_cost,
            currency=self.req.currency, total_price_local=sum(
                c["Price (Local)"] for c in self.deck),
            analytics=Analytics(mana_curve=dict(sorted(self.cmc_curve.items())), color_distribution=dict(
                self.color_dist), total_cmc=sum(c["CMC"] for c in spells) / len(spells) if spells else 0),
            export_text=export_txt, excel_base64=base64.b64encode(format_excel_in_memory(df)).decode('utf-8'), deck_list=visual_list, message="Deck created successfully"
        )

    def _format_lists(self):
        v_list, f_list = [], []
        for c in self.deck:
            qty = c.get("Quantity", 1)
            v_list.append(CardInfo(name=f"{qty}x {c['Card Name']}" if qty > 1 else c['Card Name'], role=c["Role"], type=c["Type"],
                          mana_cost=c["Mana Cost"], cmc=c["CMC"], price_usd=c["Price (USD)"], price_local=c["Price (Local)"], image_url=c["Image URL"]))
            for _ in range(qty):
                copy = c.copy()
                copy["Quantity"] = 1
                f_list.append(copy)
        return v_list, "".join([f"1 {c['Card Name']}\n" for c in f_list]), pd.DataFrame(f_list)[["Role", "Card Name", "Type", "Price (USD)", "Price (Local)"]]

    def _save_to_db(self, res: DeckResponse):
        # --- 🛡️ CORRECCIÓN: USAR model_dump() PARA PYDANTIC V2 ---
        db_deck = DeckModel(
            commander=res.commander, 
            archetype=res.archetype_used, 
            budget=res.final_budget_usd, 
            currency=res.currency,
            deck_list=[c.model_dump() for c in res.deck_list], 
            analytics=res.analytics.model_dump(), 
            export_text=res.export_text, 
            excel_base64=res.excel_base64
        )
        self.db.add(db_deck)
        self.db.commit()
        self.db.refresh(db_deck)
        return db_deck


def build_advanced_deck_logic(request: DeckRequest, db: Session) -> DeckResponse:
    return DeckBuilderService(request, db).generate()


def get_alternatives_logic(commander_name, role, max_price, current_card_name):
    edh = EDHRec()
    try:
        cards_map = edh.get_commander_cards(commander_name)
    except:
        raise HTTPException(status_code=404, detail="Commander not found")

    role_map = {"Ramp": ["Mana Artifacts", "Ramp"], "Draw": ["Draw", "Card Draw"], "Removal": [
        "Removal", "Instants", "Sorceries"], "Synergy": ["High Synergy", "Top Cards", "Creatures"], "Land": ["Lands"]}
    cats_to_search = ["Top Cards"]
    for k, v in role_map.items():
        if k.lower() in role.lower():
            cats_to_search = v
            break

    cands, seen = [], {current_card_name} if current_card_name else set()
    for cat in cats_to_search:
        if cat in cards_map:
            for c in cards_map[cat]:
                if c['name'] in seen:
                    continue
                data = get_scryfall_data(c['name'])
                if data and data['price_usd'] <= max_price:
                    cands.append(AlternativeCard(name=c['name'], price_usd=data['price_usd'], synergy=c.get(
                        'synergy', 0), image_url=data['image_url']))
                    seen.add(c['name'])
                if len(cands) >= 10:
                    break
        if len(cands) >= 10:
            break
    return cands
