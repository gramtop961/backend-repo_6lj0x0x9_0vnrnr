import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from database import db, create_document, get_documents
from schemas import Product, Order

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "E-commerce backend is running"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

# ------- Schemas exposure (for tooling/inspectors) -------
@app.get("/schema")
def get_schema():
    """Return JSON schema for known collections"""
    return {
        "product": Product.model_json_schema(),
        "order": Order.model_json_schema(),
    }

# ---------------- Products ----------------
@app.get("/api/products")
def list_products(category: Optional[str] = None, q: Optional[str] = None, limit: int = 50):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    filter_dict = {}
    if category:
        filter_dict["category"] = category
    if q:
        filter_dict["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"category": {"$regex": q, "$options": "i"}},
        ]
    docs = get_documents("product", filter_dict=filter_dict, limit=limit)
    result = []
    for d in docs:
        item = {
            "id": str(d.get("_id")),
            "title": d.get("title"),
            "description": d.get("description"),
            "price": float(d.get("price", 0)),
            "category": d.get("category", "Other"),
            "image": d.get("image"),
            "rating": float(d.get("rating", 4.5)),
            "in_stock": bool(d.get("in_stock", True)),
        }
        result.append(item)
    return result

@app.get("/api/products/{product_id}")
def get_product(product_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    from bson import ObjectId
    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product id")
    doc = db["product"].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    doc["id"] = str(doc.pop("_id"))
    return doc

# Seed sample products for demo
@app.post("/api/products/seed")
def seed_products():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    samples = [
        {
            "title": "Wireless Noise-Cancelling Headphones",
            "description": "Immersive sound with active noise cancellation and 30h battery.",
            "price": 199.99,
            "category": "Electronics",
            "image": "https://images.unsplash.com/photo-1518443895914-6df8ccca9fd8?q=80&w=1200&auto=format&fit=crop",
            "rating": 4.6,
            "in_stock": True,
        },
        {
            "title": "Ergonomic Office Chair",
            "description": "Lumbar support, breathable mesh, adjustable height and tilt.",
            "price": 129.0,
            "category": "Home",
            "image": "https://images.unsplash.com/photo-1582582429416-2f6b24fd4a62?q=80&w=1200&auto=format&fit=crop",
            "rating": 4.4,
            "in_stock": True,
        },
        {
            "title": "Stainless Steel Water Bottle 1L",
            "description": "Keeps drinks cold 24h or hot 12h, leak-proof design.",
            "price": 24.99,
            "category": "Outdoors",
            "image": "https://images.unsplash.com/photo-1519681393784-d120267933ba?q=80&w=1200&auto=format&fit=crop",
            "rating": 4.8,
            "in_stock": True,
        },
        {
            "title": "Smart LED Light Bulb (4-pack)",
            "description": "16M colors, app control, works with Alexa and Google.",
            "price": 39.99,
            "category": "Electronics",
            "image": "https://images.unsplash.com/photo-1482192596544-9eb780fc7f66?q=80&w=1200&auto=format&fit=crop",
            "rating": 4.3,
            "in_stock": True,
        },
    ]
    inserted = 0
    for s in samples:
        try:
            create_document("product", s)
            inserted += 1
        except Exception:
            pass
    return {"inserted": inserted}

# ---------------- Orders ----------------
class CreateOrderRequest(BaseModel):
    items: List[dict]
    customer_name: str
    customer_email: str
    customer_address: str

@app.post("/api/orders")
def create_order(payload: CreateOrderRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    # Calculate totals safely on backend
    subtotal = sum(float(i.get("price", 0)) * int(i.get("quantity", 1)) for i in payload.items)
    shipping = 0 if subtotal >= 50 else 6.99
    taxes = round(subtotal * 0.07, 2)
    total = round(subtotal + shipping + taxes, 2)

    order_doc = Order(
        items=[
            {
                "product_id": str(i.get("product_id", "")),
                "title": str(i.get("title", "")),
                "price": float(i.get("price", 0)),
                "quantity": int(i.get("quantity", 1)),
                "image": i.get("image"),
            }
            for i in payload.items
        ],
        subtotal=round(subtotal, 2),
        shipping=round(shipping, 2),
        taxes=taxes,
        total=total,
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        customer_address=payload.customer_address,
    )

    order_id = create_document("order", order_doc)
    return {"order_id": order_id, "total": total}
