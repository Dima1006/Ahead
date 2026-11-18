"""Demo data: three ready venues (coffee shop, pizzeria, sushi bar), so a fresh demo is never empty
and every kind of venue can be shown to an owner without setting it up by hand.

Each venue is created only if its e-mail is not in the database yet, so restarting is safe
and new demo venues are added to an existing database too."""
import os
import secrets

from .db import connect
from .utils import hash_password

DEMO_EMAIL = "demo@woodcoffee.pl"   # the coffee shop; kept for the tests and the README

# menu: category -> item -> {size label: price in zł}; a plain number means a single price
# options: add-on group -> {"required", "multi", "options": {name: extra zł}, "categories": [...]}
DEMO_VENUES = [
    {
        "slug": "wood-coffee",
        "name": "Wood Coffee",
        "email": DEMO_EMAIL,
        "address": "ul. Przykładowa 1",
        "description": "Demo venue: coffee, tea and desserts for pickup.",
        "prep_minutes": 5,
        "loyalty_categories": ["Coffee"],          # ready for Settings → Loyalty
        "menu": {
            "Coffee": {
                "Cappuccino": {"Small": 12, "Medium": 14, "Large": 16},
                "Latte": {"Small": 13, "Medium": 15, "Large": 17},
                "Americano": {"Small": 9, "Medium": 11, "Large": 13},
            },
            "Tea": {
                "Black Tea": {"Small": 8, "Medium": 10, "Large": 12},
                "Green Tea": {"Small": 8, "Medium": 10, "Large": 12},
            },
            "Milk drinks": {
                "Cocoa": {"Medium": 11, "Large": 13},
                "Milkshake": {"Strawberry": 15, "Chocolate": 15},
            },
            "Desserts": {"Croissant": 9, "Cheesecake": 15},
        },
        "options": {},
    },
    {
        "slug": "bella-napoli",
        "name": "Bella Napoli",
        "email": "demo-pizza@woodcoffee.pl",
        "address": "ul. Przykładowa 2",
        "description": "Demo venue: Neapolitan pizza from a wood-fired oven, for pickup.",
        "prep_minutes": 20,
        "loyalty_categories": ["Pizza"],
        "menu": {
            "Pizza": {
                "Margherita": {"32 cm": 32, "40 cm": 42},
                "Marinara": {"32 cm": 29, "40 cm": 38},
                "Diavola": {"32 cm": 39, "40 cm": 49},
                "Capricciosa": {"32 cm": 41, "40 cm": 52},
                "Quattro Formaggi": {"32 cm": 42, "40 cm": 54},
                "Prosciutto e Rucola": {"32 cm": 45, "40 cm": 57},
            },
            "Starters": {"Focaccia": 16, "Bruschetta": 19},
            "Drinks": {"Lemonade 0.5 l": 14, "Coca-Cola 0.33 l": 9, "Water 0.5 l": 7},
            "Desserts": {"Tiramisu": 22, "Panna cotta": 19},
        },
        "options": {
            "Extra toppings": {
                "required": False, "multi": True, "categories": ["Pizza"],
                "options": {"Extra mozzarella": 6, "Salami": 7, "Mushrooms": 5, "Jalapeño": 4, "Burrata": 14},
            },
        },
    },
    {
        "slug": "sushi-hana",
        "name": "Sushi Hana",
        "email": "demo-sushi@woodcoffee.pl",
        "address": "ul. Przykładowa 3",
        "description": "Demo venue: sushi sets and rolls for pickup.",
        "prep_minutes": 30,
        "loyalty_categories": ["Sets"],
        "menu": {
            "Sets": {
                "Classic Set (16 pcs)": 69,
                "Salmon Lover (24 pcs)": 99,
                "Veggie Set (16 pcs)": 55,
                "Party Set (40 pcs)": 159,
            },
            "Rolls (8 pcs)": {
                "California": 36,
                "Philadelphia": 39,
                "Futomaki Salmon": 42,
                "Ebi Tempura Roll": 41,
            },
            "Nigiri (2 pcs)": {"Salmon": 16, "Tuna": 19, "Eel": 21},
            "Sides": {"Miso Soup": 14, "Edamame": 15, "Gyoza (5 pcs)": 22},
            "Drinks": {"Green Tea": 9, "Ramune": 14},
        },
        "options": {
            "Chopsticks": {
                "required": True, "multi": False, "categories": ["Sets"],
                "options": {"No chopsticks": 0, "1 pair": 0, "2 pairs": 0, "4 pairs": 0},
            },
            "Sauces": {
                "required": False, "multi": True, "categories": ["Sets", "Rolls (8 pcs)"],
                "options": {"Extra soy sauce": 0, "Spicy mayo": 3, "Unagi sauce": 3},
            },
        },
    },
]


def _create_venue(conn, venue: dict, password: str) -> None:
    venue_id = conn.execute(
        "INSERT INTO venues (slug, name, city, address, description, email, password_hash, status, prep_minutes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'approved', ?)",
        (venue["slug"], venue["name"], "Warszawa", venue["address"], venue["description"],
         venue["email"], hash_password(password), venue["prep_minutes"]),
    ).lastrowid

    items_by_category = {}
    for category, items in venue["menu"].items():
        cat_id = conn.execute(
            "INSERT INTO categories (venue_id, name) VALUES (?, ?)", (venue_id, category)
        ).lastrowid
        for name, prices in items.items():
            item_id = conn.execute(
                "INSERT INTO items (venue_id, category_id, name, loyalty) VALUES (?, ?, ?, ?)",
                (venue_id, cat_id, name, int(category in venue["loyalty_categories"])),
            ).lastrowid
            items_by_category.setdefault(category, []).append(item_id)
            variants = prices.items() if isinstance(prices, dict) else [("", prices)]
            for label, zl in variants:
                conn.execute(
                    "INSERT INTO variants (item_id, label, price) VALUES (?, ?, ?)",
                    (item_id, label, zl * 100),
                )

    for group, spec in venue["options"].items():
        group_id = conn.execute(
            "INSERT INTO option_groups (venue_id, name, required, multi) VALUES (?, ?, ?, ?)",
            (venue_id, group, int(spec["required"]), int(spec["multi"])),
        ).lastrowid
        for name, zl in spec["options"].items():
            conn.execute(
                "INSERT INTO options (group_id, name, price) VALUES (?, ?, ?)", (group_id, name, zl * 100)
            )
        for category in spec["categories"]:
            for item_id in items_by_category.get(category, []):
                conn.execute(
                    "INSERT INTO item_option_groups (item_id, group_id) VALUES (?, ?)", (item_id, group_id)
                )


def seed_demo() -> None:
    conn = connect()
    try:
        password = os.getenv("DEMO_PASSWORD") or secrets.token_urlsafe(9)
        created = []
        for venue in DEMO_VENUES:
            if conn.execute("SELECT 1 FROM venues WHERE email = ?", (venue["email"],)).fetchone():
                continue
            _create_venue(conn, venue, password)
            created.append(venue["email"])
        conn.commit()
        for email in created:
            print(f"[demo] venue login: {email} / {password}", flush=True)
    finally:
        conn.close()
