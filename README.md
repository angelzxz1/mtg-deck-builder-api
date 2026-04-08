# 📘 MTG Smart Deck Builder API v1.0

MTG Smart Deck Builder es una API REST desarrollada con FastAPI que automatiza la creación de mazos para el formato Commander de Magic: The Gathering.

A diferencia de generadores aleatorios, esta API utiliza datos de EDHRec para sinergia, Scryfall para precios e imágenes, y Yahoo Finance para conversión de divisas en tiempo real. Construye mazos matemáticamente balanceados ajustándose estrictamente al presupuesto del usuario.

---

##🏗️ Arquitectura del Proyecto

| Archivo | Tipo | Descripcion |
|---------|------|-------------|
| `main.py`|**Controller**|Punto de entrada. Define los endpoints (`POST`, `GET`) y gestiona las peticiones HTTP.|
|`services.py`|**Logic**|Contiene la clase `DeckBuilderService`.Aquí reside la lógica de construcción del mazo, fases de hechizos y cálculo de tierras.|
|`models.py`|**DTOs**|Define los esquemas de datos (Pydantic) para validar las entradas y salidas de la API.|
|`utils.py`|**Helpers**|Funciones auxiliares: Conexión con APIs externas (`yfinance`, `scryfall`), caché y generación de Excel.|
|`config.py`|**Config**|Constantes globales como los Arquetipos de Mazo y tasas de cambio de respaldo.|

---

## 🚀 Instalación y Despliegue
1. Requisitos
  - Python 3.9 o superior.

2. Instalación de Dependencias

Ejecuta el siguiente comando para instalar las librerías necesarias:
```
pip install fastapi uvicorn requests pandas openpyxl pyedhrec yfinance
```

3. Ejecutar el Servidor

Para iniciar la API en modo desarrollo (recarga automática al guardar cambios):

```
uvicorn main:app --reload
```
  - **API URL:** `http://127.0.0.1:8000`
  - **Documentación Interactiva (Swagger):** `http://127.0.0.1:8000/docs`
---
## 📡 Referencia de API (Endpoints)
1. Generar Mazo (`POST /generate-deck`)

    Genera un mazo completo de 100 cartas optimizado.
    - URL: /generate-deck
    - Método: POST

**Cuerpo de la Petición (Request Body)**
```javascript
{
  "commander_name": "Krenko, Mob Boss",
  "budget": 50.0,            // Presupuesto total
  "max_single_card": 2.0,    // Precio máximo por carta individual
  "currency": "MXN",         // Moneda de salida (USD, COP, MXN, EUR)
  "archetype": "Aggro",      // Estrategia: "Balanced", "Control", "Aggro", "Spellslinger"
  "owned_cards": ["Sol Ring"] // Cartas que ya tienes (coste $0)
}
```

**Respuesta (Response)**
```javascript
{
  "commander": "Krenko, Mob Boss",
  "archetype_used": "Aggro",
  "final_budget_usd": 48.50,
  "currency": "MXN",
  "total_price_local": 985.40,  // Precio convertido a MXN usando tasa real
  "analytics": {
    "mana_curve": { "1": 8, "2": 15, "3": 10 ... }, // Excluye tierras
    "color_distribution": { "R": 45 },
    "total_cmc": 2.85
  },
  "deck_list": [
    {
      "name": "Goblin Chieftain",
      "role": "Synergy",
      "type": "Creature",
      "mana_cost": "{1}{R}{R}",
      "price_usd": 1.50,
      "price_local": 30.50,
      "image_url": "https://cards.scryfall.io/..."
    }
    // ... lista completa de cartas
  ],
  "export_text": "1 Goblin Chieftain\n1 Sol Ring...", // Para copiar a Moxfield
  "excel_base64": "UEsDBBQABgAIAAAAIQ..." // Archivo .xlsx en Base64
}
```
2. Obtener Alternativas (`GET /get-alternatives`)
    
    Busca sugerencias para reemplazar una carta específica, manteniendo el rol y presupuesto.

    - **URL:** `/get-alternatives`
    - **Método:** `GET`
Parámetros (Query Params)
|Parámetro|Tipo|Descripción|
|---------|----|-----------|
|`commander_name`|string|El nombre del comandante.|
|`role`|string|El rol que debe cumplir (ej. "Ramp", "Removal").|
|`max_price`|float|Precio máximo deseado en USD.|
|`current_card_name`|string|(Opcional) Nombre de la carta a reemplazar para no repetirla.|

Ejemplo de Respuesta
```javascript
[
  {
    "name": "Chaos Warp",
    "price_usd": 0.75,
    "synergy": 0.45,
    "image_url": "https://cards.scryfall.io/..."
  }
]
```
---
## 🧠 Lógica del Sistema (DeckBuilderService)

El núcleo de la v1.0 es la clase `DeckBuilderService` en `services.py`, que opera en 3 fases secuenciales:

**Fase 1: Hechizos (Spells)**
1. **Conversión de Moneda**: Al iniciar, consulta yfinance para obtener la tasa de cambio real (USD -> Moneda Local). Si falla, usa un valor de respaldo (config.py).

2. **Staples & Quotas**: Agrega cartas esenciales (Sol Ring) y llena las cuotas de Ramp/Draw/Removal según el archetype seleccionado.

3. **Sinergia**: Rellena los espacios restantes (NON_LAND_SLOTS) con las mejores cartas de EDHRec que respeten el presupuesto y no sean tierras.

**Fase 2: Base de Maná (Lands)**
1. **Cálculo de Presupuesto**: Utiliza exclusivamente el dinero que sobró de la Fase 1.

2. **Fixing Inteligente**: Si el comandante es multicolor, prioriza tierras de corrección (Command Tower, Exotic Orchard).

3. **Tierras Utilitarias**: Busca tierras especiales en EDHRec baratas.

4. **Balanceo Matemático**: Calcula cuántas tierras básicas de cada tipo se necesitan basándose en los símbolos de maná (mana_pips) de los hechizos elegidos en la Fase 1.

**Fase 3: Salida**
1. Genera analíticas (Curva de maná y promedio CMC, excluyendo tierras para mayor precisión).

2. Crea un archivo Excel en memoria y lo codifica a Base64.

3. Genera texto plano para importación en plataformas como Moxfield o Arena.
---
## ⚙️ Configuración (`config.py`)

Puedes ajustar los ratios de los mazos editando `DECK_ARCHETYPES`.

```python
DECK_ARCHETYPES = {
    "Balanced": {"lands": 36, "creatures": 25, "ramp": 12, "draw": 10, "removal": 10},
    "Control":  {"lands": 38, "creatures": 15, "ramp": 14, "draw": 12, "removal": 15},
    "Aggro":    {"lands": 34, "creatures": 35, "ramp": 10, "draw": 10, "removal": 8},
    "Spellslinger": {"lands": 35, "creatures": 10, "ramp": 12, "draw": 15, "removal": 12},
}
```

Tambien puedes ajustar los valores de respaldo si deseas. Estos se utilizan solo si Yahoo Finance no responde

```python
EXCHANGE_RATES = {
    "USD": 1.0,
    "COP": 3600.0,  # Peso Colombiano
    "MXN": 17.23,   # Peso Mexicano
    "EUR": 0.84,    # Euro
    "CLP": 856.55,  # Peso Chileno
    "ARS": 1394.46  # Peso Argentino
}
```
