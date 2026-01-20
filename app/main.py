from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import SESSION_SECRET, SHOP_TYPES
from app.core.database import SessionLocal, init_db
from app.models import ShopSettings
from app.routers import admin, api, auth, shops

app = FastAPI()
app.add_middleware(
    SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax"
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(shops.router)
app.include_router(api.router)
app.include_router(admin.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    with SessionLocal() as db:
        existing = {
            row.shop_type for row in db.execute(
                select(ShopSettings)
            ).scalars().all()
        }
        for shop_type in SHOP_TYPES:
            if shop_type not in existing:
                db.add(ShopSettings(shop_type=shop_type))
        db.commit()
