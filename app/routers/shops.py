from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import SHOP_TYPES
from app.core.database import get_db
from app.core.templates import templates
from app.core.time import local_now
from app.models import Product
from app.services.auth import get_current_user
from app.services.shops import get_shop_settings, has_access, is_shop_open

router = APIRouter()


@router.get("/shops", response_class=HTMLResponse)
def shops(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    now = local_now()
    status_map = {}
    for shop_type in SHOP_TYPES:
        settings = get_shop_settings(db, shop_type)
        status_map[shop_type] = {
            "allowed": has_access(db, user.tg_username, shop_type),
            "open": is_shop_open(settings, now),
            "opens_at": settings.opens_at if settings else None,
            "closes_at": settings.closes_at if settings else None,
        }
    return templates.TemplateResponse(
        "shops.html",
        {
            "request": request,
            "user": user,
            "status_map": status_map,
        },
    )


@router.get("/shop/{shop_type}", response_class=HTMLResponse)
def shop_view(
    shop_type: str,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    if shop_type not in SHOP_TYPES:
        raise HTTPException(status_code=404)
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    allowed = has_access(db, user.tg_username, shop_type)
    settings = get_shop_settings(db, shop_type)
    open_now = is_shop_open(settings, local_now())

    products = []
    if allowed and open_now:
        products = (
            db.execute(
                select(Product)
                .where(
                    Product.shop_type == shop_type, Product.active.is_(True)
                )
                .order_by(Product.position, Product.created_at)
            )
            .scalars()
            .all()
        )

    return templates.TemplateResponse(
        "shop.html",
        {
            "request": request,
            "user": user,
            "shop_type": shop_type,
            "allowed": allowed,
            "open_now": open_now,
            "settings": settings,
            "products": products,
        },
    )


@router.get(
    "/shop/{shop_type}/product/{product_id}", response_class=HTMLResponse
)
def product_detail(
    shop_type: str,
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    if shop_type not in SHOP_TYPES:
        raise HTTPException(status_code=404)
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    allowed = has_access(db, user.tg_username, shop_type)
    settings = get_shop_settings(db, shop_type)
    open_now = is_shop_open(settings, local_now())

    product = None
    if allowed and open_now:
        product = (
            db.execute(
                select(Product).where(
                    Product.id == product_id,
                    Product.shop_type == shop_type,
                    Product.active.is_(True),
                )
            )
            .scalars()
            .first()
        )

    return templates.TemplateResponse(
        "product.html",
        {
            "request": request,
            "user": user,
            "shop_type": shop_type,
            "allowed": allowed,
            "open_now": open_now,
            "settings": settings,
            "product": product,
        },
    )
