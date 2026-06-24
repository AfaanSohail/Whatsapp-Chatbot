"""
Menu Data Extractor for WhatsApp Chatbot Training  — v4
========================================================
Uses LangChain + Groq (llama-3.3-70b) to parse a raw menu text and return
a strict JSON schema suitable for a WhatsApp food-ordering chatbot database.

Fixes applied vs v3:
  1. Base Prices: Enforced a base `price` for ALL items (lowest size price) 
     so WhatsApp Catalog API doesn't crash on null prices.
  2. Required Choices: Updated to an array of objects with `min_selections` 
     and `max_selections` boundaries.
  3. Half-and-Half: Added `pricing_logic` field to flag mathematical 
     transformations for the backend.

Requirements:
    pip install langchain langchain-groq langchain-core pydantic

Usage:
    export GROQ_API_KEY="gsk_..."
    python extract_menu_schema.py
"""

import json
import os
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import Optional

# ─────────────────────────────────────────────
# 1.  UPDATED RAW MENU TEXT
# ─────────────────────────────────────────────
RAW_MENU = """
BUSINESS PROFILE & SETTINGS
- Restaurant Name: The Rustic Slice Pizza & Wings
- Address: 123 Main Street, Downtown Food District
- Timezone: EST (Eastern Standard Time)
- Tax Rate: 8.5% applied to the final subtotal
- Payment Methods: Online Credit Card (via Stripe link sent in chat), Cash on Delivery (COD)

OPERATIONAL HOURS
- Monday - Thursday: 11:00 AM to 10:00 PM
- Friday - Saturday: 11:00 AM to 11:30 PM
- Sunday: 12:00 PM to 9:00 PM

DELIVERY & PICKUP LOGIC
- Order Types: Delivery and Pickup
- Delivery Radius: Maximum 5 miles from the restaurant
- Minimum Order for Delivery: $15.00
- Delivery Fee: $3.99 flat rate
- Free Delivery Threshold: Orders over $50.00 get delivery fee waived

MENU: PIZZAS
All pizzas come in Medium (12") or Large (16").
Pizza Customizations (apply to ANY pizza):
- Extra Cheese: +$2.00 (any size)
- Gluten-Free Crust: +$3.00 (Medium only)
- Half-and-Half: +$2.00 flat fee on the highest-priced half (Large only)

* Classic Margherita
  Description: Fresh mozzarella, house-made tomato sauce, and fresh basil leaves.
  Prices: Medium $14.00 | Large $18.00

* The Meat Lover
  Description: Loaded with premium pepperoni, Italian sausage, and crispy bacon.
  Prices: Medium $17.00 | Large $22.00

* Spicy BBQ Chicken
  Description: Grilled chicken in spicy BBQ sauce, topped with red onions and fresh cilantro.
  Prices: Medium $16.00 | Large $20.00

MENU: WINGS & SIDES

* Bone-in Wings
  Description: Crispy fried bone-in wings tossed in your choice of sauce.
  Sizes: 6 pieces for $10.99 | 12 pieces for $18.99
  Sauce Flavors (must pick 1): Buffalo, Lemon Pepper, Garlic Parmesan
  Included: 1 free dip per order (must pick 1: Ranch or Blue Cheese)
  Extra Dips: +$0.50 each (choices: Ranch, Blue Cheese)

* Garlic Knots
  Description: Baked fresh daily, brushed with garlic butter and herbs.
  Size: 5 knots for $5.99
  Included: 1 free side of marinara sauce

MENU: DRINKS
Description: Ice cold canned sodas and house-made specialties.

* Coke (Can) - $2.50
* Diet Coke (Can) - $2.50
* Sprite (Can) - $2.50
* House Artisan Lemonade - $3.50
  Description: Freshly squeezed in-house with a hint of mint.
"""

# ─────────────────────────────────────────────
# 2.  PYDANTIC SCHEMA  (v4 — WhatsApp UI fixes baked in)
# ─────────────────────────────────────────────

class SizePrice(BaseModel):
    size: str        # "Medium" | "Large" | "6pc" | "12pc" | "5pc"
    price: float

class RequiredChoiceGroup(BaseModel):
    """Defines boundaries for options users must pick (e.g., sauces, free dips)"""
    name: str
    options: list[str]
    min_selections: int
    max_selections: int

class Modifier(BaseModel):
    name: str
    price: float                                   # 0.0 if free
    constraint: Optional[str] = None               # e.g. "Medium only", "Large only"
    requires_secondary_item_selection: bool = False # true only for Half-and-Half
    secondary_item_category: Optional[str] = None  # e.g. "pizzas"
    pricing_logic: Optional[str] = None            # Math flag e.g. "highest_half_base_plus_flat_fee"

class Category(BaseModel):
    id: str           # snake_case, matches MenuItem.category
    display_name: str # human-readable label shown on WhatsApp

class MenuItem(BaseModel):
    id: str                             # unique snake_case slug
    category: str                       # must match a Category.id
    name: str
    description: str                    # always non-null — required for WhatsApp subtitle
    image_url: Optional[str] = None     # placeholder for WhatsApp catalog image
    price: float                        # WhatsApp Catalog requires a base price (use lowest size price if variants exist)
    sizes: list[SizePrice] = Field(default_factory=list)
    required_choices: list[RequiredChoiceGroup] = Field(default_factory=list)
    included_items: list[str] = Field(default_factory=list)
    modifiers: list[Modifier] = Field(default_factory=list)

class OperationalHours(BaseModel):
    timezone: str                # IANA format e.g. "America/New_York"
    monday_thursday_open: str    # 24hr "HH:MM"
    monday_thursday_close: str
    friday_saturday_open: str
    friday_saturday_close: str
    sunday_open: str
    sunday_close: str

class DeliveryPolicy(BaseModel):
    fee: float
    minimum_order: float
    free_delivery_threshold: float
    max_delivery_radius_miles: float
    supported_order_types: list[str]
    pickup_address: str

class BusinessProfile(BaseModel):
    restaurant_name: str
    address: str
    timezone: str
    tax_rate_percent: float
    payment_methods: list[str]

class MenuSchema(BaseModel):
    business: BusinessProfile
    hours: OperationalHours
    delivery_policy: DeliveryPolicy
    categories: list[Category]          
    menu_items: list[MenuItem]

# ─────────────────────────────────────────────
# 3.  PROMPT
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """You are a precise data-extraction engine for a WhatsApp restaurant ordering chatbot.

Extract ALL information from the menu text and return ONLY a valid JSON object
that conforms EXACTLY to this schema:

{schema}

Critical rules — read carefully:

RULE 1  — JSON only. No markdown fences, no commentary, no extra keys.
RULE 2  — All prices must be floats (14.00 not "$14" or "14 bucks").
RULE 3  — All times must be 24-hour "HH:MM" strings (e.g. "22:00", "11:00").
RULE 4  — PIZZA MODIFIERS: Extra Cheese, Gluten-Free Crust, and Half-and-Half
           must appear in the "modifiers" array of EVERY pizza item individually.
           Do NOT create a separate menu item for pizza extras.
RULE 5  — HALF-AND-HALF MODIFIER: Set requires_secondary_item_selection=true,
           secondary_item_category="pizzas", and pricing_logic="highest_half_base_plus_flat_fee". 
           All other modifiers get false/null for these flags.
RULE 6  — WINGS DIPS: a) Add an object to required_choices for the free dip: 
           {{"name": "Free Dip", "options": ["Ranch", "Blue Cheese"], "min_selections": 1, "max_selections": 1}}.
           b) Add individual modifiers for each extra dip option at $0.50 each.
RULE 7  — REQUIRED CHOICES: If a customer MUST pick something (sauce, free dip),
           capture it in "required_choices" as an array of objects specifying min/max selections.
           Example: [{{"name": "Sauce Flavor", "options": ["Buffalo", "Lemon Pepper", "Garlic Parmesan"], "min_selections": 1, "max_selections": 1}}]
RULE 8  — CATEGORIES: Build a top-level "categories" array with one entry per
           category using snake_case IDs. Every menu item's "category" field must
           exactly match one of those IDs.
RULE 9  — DESCRIPTIONS: Every item must have a non-null, human-readable description
           of 1-2 sentences. Never set description to null.
RULE 10 — IMAGE URLs: Set image_url to null for all items (placeholder for later).
RULE 11 — WHATSAPP PRICING: Every menu item MUST have a base "price" (float). 
           For items with multiple sizes, set "price" to the LOWEST starting price among its sizes.
RULE 12 — IDs must be unique lowercase snake_case slugs.
RULE 13 — Do NOT invent any item, price, or field not present in the text.
RULE 14 — Timezone: use IANA format (e.g. "America/New_York" for EST).
"""

USER_PROMPT = """Extract the full structured menu and business data from the text below:

{menu_text}
"""

# ─────────────────────────────────────────────
# 4.  CHAIN
# ─────────────────────────────────────────────
def build_chain():
    schema_str = json.dumps(MenuSchema.model_json_schema(), indent=2)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human",  USER_PROMPT),
    ])

    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        model_kwargs={"response_format": {"type": "json_object"}},
    )

    parser = JsonOutputParser(pydantic_object=MenuSchema)

    chain = prompt | llm | parser
    return chain, schema_str


# ─────────────────────────────────────────────
# 5.  RUNNER
# ─────────────────────────────────────────────
def extract_menu(menu_text: str = RAW_MENU) -> dict:
    chain, schema_str = build_chain()

    print("⏳  Sending menu (v4 schema) to Groq (llama-3.3-70b) for extraction …\n")
    result = chain.invoke({
        "schema":    schema_str,
        "menu_text": menu_text,
    })

    return result


def main():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY environment variable is not set.\n"
            "  export GROQ_API_KEY='gsk_...'"
        )

    menu_data = extract_menu()

    output_path = "menu_schema_output.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(menu_data, f, indent=2, ensure_ascii=False)

    print("✅  Extraction complete!")
    print(f"📄  Saved to: {output_path}\n")


if __name__ == "__main__":
    main()