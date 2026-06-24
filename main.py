from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from groq import AsyncGroq
import requests
import sqlite3
import json

app = FastAPI()

# ---------------------------------------------------------
# CREDENTIALS
# ---------------------------------------------------------
VERIFY_TOKEN = "my_super_secret_token_123"
WHATSAPP_TOKEN = "PASTE_YOUR_META_ACCESS_TOKEN_HERE"
PHONE_NUMBER_ID = "PASTE_YOUR_PHONE_NUMBER_ID_HERE"
GROQ_API_KEY = "PASTE_YOUR_GROQ_API_KEY_HERE"

groq_client = AsyncGroq(api_key=GROQ_API_KEY)
USER_SESSIONS = {}

# ---------------------------------------------------------
# DATABASE SETUP
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect("restaurant.db")
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS menu_items")
    cursor.execute("""
    CREATE TABLE menu_items (
        id TEXT PRIMARY KEY,
        category TEXT,
        name TEXT,
        price REAL,
        description TEXT,
        is_available BOOLEAN,
        image_url TEXT
    )
    """)
    items = [
        ("classic_margherita", "pizzas", "Classic Margherita", 14.0, "Fresh mozzarella and house-made tomato sauce.", True, "https://images.unsplash.com/photo-1574071318508-1cdbab80d002?q=80&w=800"),
        ("the_meat_lover", "pizzas", "The Meat Lover", 17.0, "Loaded with premium pepperoni, sausage, and bacon.", True, "https://images.unsplash.com/photo-1628840042765-356cda07504e?q=80&w=800"),
        ("spicy_bbq_chicken", "pizzas", "Spicy BBQ Chicken", 16.0, "Grilled chicken in spicy BBQ sauce with red onions.", True, "https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?q=80&w=800"),
        ("bone_in_wings", "wings_and_sides", "Bone-in Wings", 10.99, "Crispy wings. Don't forget to add your sauces!", True, "https://images.unsplash.com/photo-1608039829572-78524f79c4c7?q=80&w=800"),
        ("garlic_knots", "wings_and_sides", "Garlic Knots", 5.99, "Baked fresh daily, brushed with garlic butter.", True, "https://images.unsplash.com/photo-1573140247632-f8fd74997d5c?q=80&w=800"),
        ("coke", "drinks", "Coke", 2.5, "Ice cold canned soda.", True, "https://images.unsplash.com/photo-1622483767028-3f66f32aef97?q=80&w=800"),
        ("diet_coke", "drinks", "Diet Coke", 2.5, "Ice cold zero-calorie soda.", True, "https://images.unsplash.com/photo-1622483767028-3f66f32aef97?q=80&w=800"),
        ("sprite", "drinks", "Sprite", 2.5, "Ice cold lemon-lime soda.", True, "https://images.unsplash.com/photo-1625772299848-391b6a87d7b3?q=80&w=800"),
        ("house_artisan_lemonade", "drinks", "House Artisan Lemonade", 3.5, "Freshly squeezed in-house with mint.", True, "https://images.unsplash.com/photo-1513379733131-47fc74b45fc7?q=80&w=800"),
        ("buffalo_sauce", "sauces", "Buffalo Sauce", 0.5, "Classic spicy buffalo sauce.", True, "https://images.unsplash.com/photo-1626079457814-aa2f0d9c490a?q=80&w=800"),
        ("lemon_pepper_sauce", "sauces", "Lemon Pepper Sauce", 0.5, "Zesty lemon pepper rub.", True, "https://images.unsplash.com/photo-1626079457814-aa2f0d9c490a?q=80&w=800"),
        ("ranch_dip", "sauces", "Ranch Dip", 0.5, "Creamy house-made ranch.", True, "https://images.unsplash.com/photo-1594312180905-1a8eb85474a5?q=80&w=800"),
        ("blue_cheese_dip", "sauces", "Blue Cheese Dip", 0.5, "Chunky blue cheese dip.", True, "https://images.unsplash.com/photo-1594312180905-1a8eb85474a5?q=80&w=800")
    ]
    cursor.executemany("INSERT INTO menu_items VALUES (?, ?, ?, ?, ?, ?, ?)", items)
    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------------
# DATABASE & FORMATTING HELPERS
# ---------------------------------------------------------
def get_available_menu_text():
    conn = sqlite3.connect("restaurant.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM menu_items WHERE is_available = 1")
    items = cursor.fetchall()
    conn.close()
    return "".join([f"- {i[1]} (ID: {i[0]}): ${i[2]:.2f}\n" for i in items])

def get_item_details(item_id):
    conn = sqlite3.connect("restaurant.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, description, image_url FROM menu_items WHERE id = ?", (item_id,))
    item = cursor.fetchone()
    conn.close()
    return item

def get_formatted_cart(cart, is_checkout=False):
    if not cart:
        return "🛒 *Your cart is currently empty.*"
    
    title = "🧾 *YOUR FINAL RECEIPT*" if is_checkout else "📝 *YOUR CURRENT ORDER*"
    receipt = f"{title}\n"
    receipt += "—" * 15 + "\n"
    total = 0.0
    
    wings_qty = sum(item["qty"] for item in cart if item["item_id"] == "bone_in_wings")
    free_sauces_remaining = wings_qty
    
    conn = sqlite3.connect("restaurant.db")
    cursor = conn.cursor()
    
    for item in cart:
        cursor.execute("SELECT name, price, category FROM menu_items WHERE id = ?", (item["item_id"],))
        db_item = cursor.fetchone()
        if db_item:
            name, price, category = db_item
            qty = item["qty"]
            
            if category == "sauces":
                free_qty = min(free_sauces_remaining, qty)
                paid_qty = qty - free_qty
                free_sauces_remaining -= free_qty 
                
                if free_qty > 0:
                    receipt += f"🔹 *{free_qty}x* {name} (Free with Wings!)\n"
                if paid_qty > 0:
                    subtotal = price * paid_qty
                    total += subtotal
                    receipt += f"🥣 *{paid_qty}x* {name}\n     ↳ Subtotal: `${subtotal:.2f}`\n"
            else:
                subtotal = price * qty
                total += subtotal
                emoji = "🥤" if category == 'drinks' else "🍗" if category == 'wings_and_sides' else "🍕"
                receipt += f"{emoji} *{qty}x* {name}\n     ↳ Subtotal: `${subtotal:.2f}`\n"
            
    conn.close()
    receipt += "—" * 15 + "\n"
    receipt += f"💰 *Total Bill:* `${total:.2f}`\n\n"
    
    if is_checkout:
        receipt += "✅ *Order Confirmed!* We'll start preparing it right away."
    else:
        receipt += "💡 _Type 'Checkout' to finalize your order, or ask to remove an item!_"
        
    return receipt

# ---------------------------------------------------------
# WHATSAPP SENDERS
# ---------------------------------------------------------
def send_message(payload):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code not in [200, 201]:
        print(f"❌ META API ERROR: Status {response.status_code} | {response.text}")

def send_text(phone, text):
    send_message({"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": text}})

def show_native_categories(phone):
    sections = [{"title": "Our Menu", "rows": [
        {"id": "cat_pizzas", "title": "🍕 Pizzas"},
        {"id": "cat_wings_and_sides", "title": "🍗 Wings & Sides"},
        {"id": "cat_drinks", "title": "🥤 Drinks"},
        {"id": "cat_sauces", "title": "🥣 Sauces & Dips"}
    ]}]
    send_message({
        "messaging_product": "whatsapp", "to": phone, "type": "interactive",
        "interactive": {"type": "list", "body": {"text": "What are you craving today?"}, "action": {"button": "View Menu", "sections": sections}}
    })

def show_native_items(phone, category):
    conn = sqlite3.connect("restaurant.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM menu_items WHERE category = ? AND is_available = 1", (category,))
    items = cursor.fetchall()
    conn.close()
    
    rows = []
    for i in items:
        desc = f"${i[2]:.2f} (1 Free per Wing order!)" if category == "sauces" else f"${i[2]:.2f}"
        rows.append({"id": f"item_{i[0]}", "title": i[1][:24], "description": desc[:72]})
        
    sections = [{"title": "Select an item", "rows": rows[:10]}]
    send_message({
        "messaging_product": "whatsapp", "to": phone, "type": "interactive",
        "interactive": {"type": "list", "body": {"text": "Tap an item to see details and order!"}, "action": {"button": "View Items", "sections": sections}}
    })

# ---------------------------------------------------------
# THE STRICT AI CASHIER BRAIN
# ---------------------------------------------------------
async def process_with_ai(phone, user_message):
    session = USER_SESSIONS[phone]
    live_menu = get_available_menu_text()
    current_cart = json.dumps(session["cart"])

    system_prompt = f"""
    You are a STRICT AI cashier for 'The Rustic Slice Pizza'. Do not be overly creative.
    
    Available Menu Items:
    {live_menu}
    
    User's Current Cart:
    {current_cart}
    
    STRICT ROUTING RULES (MUST FOLLOW EXACTLY):
    0. LATEST MESSAGE ONLY (CRITICAL): You have access to chat history for context, but you MUST process ONLY the VERY LAST (newest) message from the user. NEVER repeat a past action (like adding or removing) just because it happened previously in the conversation history.
    1. "add_to_cart": Use ONLY if the user explicitly asks for a new item. 
       -> DELTA RULE: ONLY output the exact item they just asked for. NEVER repeat items already in the cart. NEVER automatically add wings or sauces just because they are free.
    2. "remove_from_cart": Use this IMMEDIATELY if the user says "take off", "remove", "subtract", "cancel", "drop", or "delete". Look at the User's Current Cart and select the exact ID to remove.
    3. "clear_cart": Use if the user says "empty cart", "clear out all", "start over", or "clear my order".
    4. "show_cart": Use if the user asks "what is my total?", "show my order", or "what do I have?". -> CRITICAL: When using show_cart, the `action_items` array MUST BE COMPLETELY EMPTY.
    5. "checkout": Use ONLY when the user is completely done and finalizing the payment.
    6. "show_menu": Use if the user wants to see what you sell.

    7. CRITICAL REMOVAL RULE: If the user asks to remove or subtract an item, look at the "User's Current Cart" to find the exact `item_id`. Set the action to "remove_from_cart". In the `action_items` array, output the EXACT quantity the user explicitly asked to remove. If they do not specify a number, assume the quantity to remove is 1. DO NOT calculate the remaining total yourself.
    
    8. ISOLATION RULE: When the user asks to add a single sauce after already adding wings and sauces, add ONLY that specific sauce to the `action_items` array.
    
    NEVER DO MATH. NEVER CALCULATE TOTALS.
    
    OUTPUT STRICT JSON ONLY:
    {{
        "reply_message": "Short conversational response WITHOUT ANY MATH OR TOTALS",
        "action": "none" | "add_to_cart" | "remove_from_cart" | "clear_cart" | "checkout" | "show_menu" | "show_cart",
        "action_items": [
            {{"id": "exact_item_id", "qty": 1}} 
        ] // LEAVE EMPTY IF ACTION IS NOT ADD OR REMOVE
    }}
    """

    session["history"].append({"role": "user", "content": user_message})
    messages = [{"role": "system", "content": system_prompt}] + session["history"][-6:]

    try:
        # TEMPERATURE SET TO 0.0 TO PREVENT HALLUCINATIONS AND IMPROVISING
        completion = await groq_client.chat.completions.create(
            model="llama-3.1-8b-instant", messages=messages, response_format={"type": "json_object"}, temperature=0.0
        )
        ai_response = json.loads(completion.choices[0].message.content)
        action = ai_response.get("action")
        reply_message = ai_response.get("reply_message")

        if action == "show_menu":
            send_text(phone, reply_message)
            show_native_categories(phone)
            return

        elif action == "show_cart":
            send_text(phone, reply_message)
            send_text(phone, get_formatted_cart(session["cart"]))
            return

        elif action == "clear_cart":
            session["cart"] = []
            send_text(phone, reply_message)
            send_text(phone, "🛒 *Your cart has been completely emptied. Let's start fresh!*")
            return

        elif action == "add_to_cart":
            items_to_add = ai_response.get("action_items", [])
            for item in items_to_add:
                item_id = item.get("id")
                qty = item.get("qty")
                if item_id and qty:
                    existing = next((i for i in session["cart"] if i["item_id"] == item_id), None)
                    if existing:
                        existing["qty"] += qty
                    else:
                        session["cart"].append({"item_id": item_id, "qty": qty})
            
            send_text(phone, reply_message)
            send_text(phone, get_formatted_cart(session["cart"]))
            return

        elif action == "remove_from_cart":
            items_to_remove = ai_response.get("action_items", [])
            for item in items_to_remove:
                item_id = item.get("id")
                qty = item.get("qty")
                if item_id and qty:
                    existing = next((i for i in session["cart"] if i["item_id"] == item_id), None)
                    if existing:
                        existing["qty"] -= qty
                        if existing["qty"] <= 0:
                            session["cart"].remove(existing)
            
            send_text(phone, reply_message)
            send_text(phone, get_formatted_cart(session["cart"]))
            return

        elif action == "checkout":
            send_text(phone, reply_message)
            final_receipt = get_formatted_cart(session["cart"], is_checkout=True)
            send_text(phone, final_receipt)
            
            print(f"\n🚨 FINAL ORDER RECEIVED:\nCustomer: {phone}\n{final_receipt}\n")
            session["cart"] = []
            session["history"] = []
            return

        send_text(phone, reply_message)
        session["history"].append({"role": "assistant", "content": reply_message})
        
    except Exception as e:
        print(f"❌ AI Error: {e}")
        send_text(phone, "Whoops! Let's try that again.")

# ---------------------------------------------------------
# WEBHOOK ENDPOINTS
# ---------------------------------------------------------
@app.get("/webhook")
async def verify(request: Request):
    if request.query_params.get("hub.mode") == "subscribe" and request.query_params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(request.query_params.get("hub.challenge"))
    raise HTTPException(status_code=403)

@app.post("/webhook")
async def receive(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if "messages" in value:
                    msg = value["messages"][0]
                    phone = msg["from"]
                    msg_type = msg.get("type")

                    if phone not in USER_SESSIONS:
                        USER_SESSIONS[phone] = {"cart": [], "history": [], "current_item_id": None}
                    session = USER_SESSIONS[phone]

                    if msg_type == "text":
                        text_body = msg["text"]["body"].strip()
                        
                        if text_body.isdigit() and session.get("current_item_id"):
                            qty = int(text_body)
                            item_id = session["current_item_id"]
                            
                            existing_item = next((i for i in session["cart"] if i["item_id"] == item_id), None)
                            if existing_item:
                                existing_item["qty"] += qty
                            else:
                                session["cart"].append({"item_id": item_id, "qty": qty})
                            
                            session["current_item_id"] = None
                            item_info = get_item_details(item_id)
                            item_name = item_info[0] if item_info else item_id
                            
                            send_text(phone, f"✅ Added {qty}x *{item_name}* to your order summary!")
                            send_text(phone, get_formatted_cart(session["cart"]))
                        else:
                            background_tasks.add_task(process_with_ai, phone, text_body)
                        
                    elif msg_type == "interactive":
                        interactive = msg["interactive"]
                        inter_id = interactive.get("list_reply", {}).get("id") or interactive.get("button_reply", {}).get("id")
                        
                        if inter_id.startswith("cat_"):
                            cat_name = inter_id.replace("cat_", "")
                            show_native_items(phone, cat_name)
                            
                        elif inter_id.startswith("item_"):
                            item_id = inter_id.replace("item_", "")
                            item = get_item_details(item_id)
                            if item:
                                session["current_item_id"] = item_id
                                caption = f"🍕 *{item[0]}* - ${item[1]}\n_{item[2]}_\n\n👉 *Please reply with the quantity you want to order (e.g. 1, 2, 3):*"
                                send_text(phone, caption)

    except Exception as e:
        print(f"❌ Webhook Processing Error: {e}")
    return {"status": "ok"}
