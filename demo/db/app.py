import asyncio
from contextlib import asynccontextmanager
import logging
import os
import random
import sqlite3
import sys
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

SERVICE = os.getenv("SERVICE_NAME", "db")
DB_PATH = os.getenv("SQLITE_PATH", "shop.db")
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))

# Logging format matching AGENTS.md Section 7: "LEVEL message" on stdout with PYTHONUNBUFFERED=1
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(SERVICE)

# Simulated connection pool semaphore
pool_semaphore = asyncio.Semaphore(POOL_SIZE)


@asynccontextmanager
async def db_slot():
    try:
        await asyncio.wait_for(pool_semaphore.acquire(), timeout=0.25)
    except asyncio.TimeoutError:
        logger.error("connection pool exhausted")
        raise HTTPException(status_code=503, detail="connection pool exhausted")
    try:
        # Hold slot ~20ms per specification
        await asyncio.sleep(0.02)
        yield
    finally:
        pool_semaphore.release()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                product_id INTEGER NOT NULL,
                qty INTEGER NOT NULL,
                total_price REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(product_id) REFERENCES products(id)
            );
        """)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM products")
        if cursor.fetchone()[0] == 0:
            seed_data = [
                (1, "SKU-8821", "Keychron Q1 Pro Mechanical Keyboard", "Keyboards",
                 "75% layout custom mechanical keyboard, fully CNC machined aluminum body, hot-swappable switches, double-gasket dampening.", 199.00, 14),
                (2, "SKU-4412", "Logitech MX Master 3S Mouse", "Peripherals",
                 "8,000 DPI Darkfield sensor tracks on glass. Quiet clicks, MagSpeed electromagnetic scroll wheel, USB-C fast recharging.", 99.00, 28),
                (3, "SKU-9905", "Dell UltraSharp 27\" 4K Monitor", "Displays",
                 "U2723QE IPS Black panel with 2000:1 contrast ratio. 98% DCI-P3 color gamut, 90W USB-C hub connectivity with RJ45 Ethernet.", 489.00, 6),
                (4, "SKU-2319", "Sony WH-1000XM5 Headset", "Audio",
                 "Active noise cancellation powered by dual V1/QN1 processors. 8 beamforming mics with AI noise reduction for crisp voice calls.", 279.00, 19),
                (5, "SKU-6120", "CalDigit TS4 Thunderbolt 4 Dock", "Hardware",
                 "18 input/output ports with 98W host charging, 2.5 Gigabit Ethernet, dual 4K/60Hz monitor support, and front UHS-II SD reader.", 379.00, 3),
            ]
            conn.executemany(
                "INSERT INTO products (id, sku, name, category, description, price, stock) VALUES (?, ?, ?, ?, ?, ?, ?)",
                seed_data
            )
            conn.commit()
            logger.info("seeded %d products into db", len(seed_data))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("db service started with pool size %d", POOL_SIZE)
    yield


app = FastAPI(title="ShopLite DB Service", lifespan=lifespan)


class OrderCreate(BaseModel):
    product_id: int
    qty: int
    total_price: Optional[float] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/products")
async def get_products():
    async with db_slot():
        def _query():
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT id, sku, name, category, description, price, stock FROM products"
                ).fetchall()
                return [dict(r) for r in rows]
        return await asyncio.to_thread(_query)


@app.get("/products/{product_id}")
async def get_product(product_id: int):
    async with db_slot():
        def _query():
            with get_db() as conn:
                row = conn.execute(
                    "SELECT id, sku, name, category, description, price, stock FROM products WHERE id = ?",
                    (product_id,)
                ).fetchone()
                return dict(row) if row else None
        p = await asyncio.to_thread(_query)
        if not p:
            raise HTTPException(status_code=404, detail="Product not found")
        return p


@app.post("/orders")
async def create_order(order: OrderCreate):
    async with db_slot():
        def _transact():
            with get_db() as conn:
                row = conn.execute(
                    "SELECT id, price, stock FROM products WHERE id = ?",
                    (order.product_id,)
                ).fetchone()
                if not row:
                    return None, "Product not found", 404
                if row["stock"] < order.qty:
                    return None, "Insufficient stock", 400

                total = order.total_price if order.total_price is not None else round(row["price"] * order.qty, 2)
                order_id = f"ORD-{random.randint(100000, 999999)}"
                conn.execute(
                    "UPDATE products SET stock = stock - ? WHERE id = ?",
                    (order.qty, order.product_id)
                )
                conn.execute(
                    "INSERT INTO orders (order_id, product_id, qty, total_price) VALUES (?, ?, ?, ?)",
                    (order_id, order.product_id, order.qty, total)
                )
                conn.commit()
                return {
                    "order_id": order_id,
                    "product_id": order.product_id,
                    "qty": order.qty,
                    "total_price": total,
                    "status": "created"
                }, None, 201

        res, err, status = await asyncio.to_thread(_transact)
        if err:
            raise HTTPException(status_code=status, detail=err)
        return res


@app.get("/orders")
async def get_orders():
    async with db_slot():
        def _query():
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT id, order_id, product_id, qty, total_price, created_at FROM orders ORDER BY id DESC"
                ).fetchall()
                return [dict(r) for r in rows]
        return await asyncio.to_thread(_query)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
