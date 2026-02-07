import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile)
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import (ADMIN_PASSWORD, ORDER_STATUS_LABELS,
                             ORDER_STATUSES, SHOP_TYPES)
from app.core.database import get_db
from app.core.templates import templates
from app.models import (AllowlistEntry, Order, Product, ProductVariant,
                        ShopSettings, User)
from app.services.auth import normalize_tg_username, require_admin
from app.services.orders import build_export_url, build_order_filters
from app.services.products import parse_optional_int, parse_variants_raw
from app.services.shops import get_shop_settings
from app.services.uploads import delete_image_file, save_image_upload

router = APIRouter()


@router.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("admin_login.html", {"request": request})


@router.post("/admin/login")
def admin_login(request: Request, password: str = Form(...)) -> HTMLResponse:
    if password != ADMIN_PASSWORD:
        return templates.TemplateResponse(
            "admin_login.html",
            {"request": request, "error": "Неверный пароль"},
            status_code=401,
        )
    request.session["is_admin"] = True
    return RedirectResponse("/admin", status_code=303)


@router.get("/admin/logout")
def admin_logout(request: Request) -> RedirectResponse:
    request.session.pop("is_admin", None)
    return RedirectResponse("/admin/login", status_code=303)


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    users_page: int = 1,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    require_admin(request)
    users_page = max(1, users_page)
    users_per_page = 50
    allowlist_by_shop = {shop_type: [] for shop_type in SHOP_TYPES}
    for entry in db.execute(
        select(AllowlistEntry).order_by(AllowlistEntry.created_at)
    ).scalars():
        if entry.shop_type in allowlist_by_shop:
            allowlist_by_shop[entry.shop_type].append(entry)

    settings_by_shop = {
        shop_type: get_shop_settings(db, shop_type) for shop_type in SHOP_TYPES
    }

    products_by_shop = {shop_type: [] for shop_type in SHOP_TYPES}
    products = db.execute(
        select(Product).order_by(Product.shop_type, Product.position)
    ).scalars().all()
    for product in products:
        products_by_shop[product.shop_type].append(product)

    total_users = db.execute(select(func.count(User.id))).scalar_one()
    total_pages = max(1, (total_users + users_per_page - 1) // users_per_page)
    if users_page > total_pages:
        users_page = total_pages
    users = db.execute(
        select(User)
        .order_by(User.points.desc())
        .offset((users_page - 1) * users_per_page)
        .limit(users_per_page)
    ).scalars().all()
    filters, resolved_status, _, _ = build_order_filters(
        status, date_from, date_to
    )
    orders_query = (
        select(Order, ProductVariant, Product)
        .join(
            ProductVariant, Order.product_variant_id == ProductVariant.id,
            isouter=True
        )
        .join(Product, ProductVariant.product_id == Product.id, isouter=True)
        .order_by(Order.created_at.desc())
        .limit(60)
    )
    if filters:
        orders_query = orders_query.where(*filters)
    orders_raw = db.execute(orders_query).all()
    orders = []
    for order, variant, product in orders_raw:
        orders.append(
            {
                "order": order,
                "variant_label": variant.label if variant else "",
                "product_title": product.title if product else "",
                "shop_type": product.shop_type if product else "",
            }
        )

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "allowlist_by_shop": allowlist_by_shop,
            "settings_by_shop": settings_by_shop,
            "products_by_shop": products_by_shop,
            "users": users,
            "users_page": users_page,
            "users_pages_total": total_pages,
            "users_has_prev": users_page > 1,
            "users_has_next": users_page < total_pages,
            "orders": orders,
            "order_statuses": ORDER_STATUSES,
            "order_status_labels": ORDER_STATUS_LABELS,
            "status_filter": resolved_status or "",
            "date_from": date_from or "",
            "date_to": date_to or "",
            "export_url": build_export_url(
                resolved_status, date_from, date_to
            ),
        },
    )


@router.get("/admin/orders/export")
def admin_orders_export(
    request: Request,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    require_admin(request)
    filters, _, _, _ = build_order_filters(status, date_from, date_to)
    query = (
        select(Order, ProductVariant, Product)
        .join(
            ProductVariant, Order.product_variant_id == ProductVariant.id,
            isouter=True
        )
        .join(Product, ProductVariant.product_id == Product.id, isouter=True)
        .order_by(Order.created_at.desc())
    )
    if filters:
        query = query.where(*filters)
    rows = db.execute(query).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "order_id",
            "created_at",
            "tg_username",
            "shop_type",
            "product_title",
            "variant_label",
            "points_spent",
            "status",
        ]
    )
    for order, variant, product in rows:
        writer.writerow(
            [
                order.id,
                order.created_at.isoformat() if order.created_at else "",
                order.tg_username,
                product.shop_type if product else "",
                product.title if product else "",
                variant.label if variant else "",
                order.points_spent,
                ORDER_STATUS_LABELS.get(order.status, order.status),
            ]
        )
    output.seek(0)
    filename = f"orders_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(output, media_type="text/csv", headers=headers)


@router.post("/admin/allowlist/add")
def admin_allowlist_add(
    request: Request,
    shop_type: str = Form(...),
    tg_username: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    require_admin(request)
    if shop_type not in SHOP_TYPES:
        raise HTTPException(status_code=400)
    normalized = normalize_tg_username(tg_username)
    if not normalized:
        raise HTTPException(status_code=400)
    exists = db.execute(
        select(AllowlistEntry).where(
            AllowlistEntry.tg_username == normalized,
            AllowlistEntry.shop_type == shop_type,
        )
    ).scalar_one_or_none()
    if not exists:
        db.add(AllowlistEntry(tg_username=normalized, shop_type=shop_type))
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/allowlist/remove")
def admin_allowlist_remove(
    request: Request,
    entry_id: int = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    require_admin(request)
    entry = db.get(AllowlistEntry, entry_id)
    if entry:
        db.delete(entry)
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/allowlist/add-all")
def admin_allowlist_add_all(
    request: Request,
    shop_type: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    require_admin(request)
    if shop_type not in SHOP_TYPES:
        raise HTTPException(status_code=400)
    existing_usernames = set(
        db.execute(
            select(AllowlistEntry.tg_username).where(
                AllowlistEntry.shop_type == shop_type
            )
        ).scalars().all()
    )
    usernames = db.execute(select(User.tg_username)).scalars().all()
    entries = [
        AllowlistEntry(tg_username=username, shop_type=shop_type)
        for username in usernames
        if username not in existing_usernames
    ]
    if entries:
        db.add_all(entries)
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/allowlist/remove-all")
def admin_allowlist_remove_all(
    request: Request,
    shop_type: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    require_admin(request)
    if shop_type not in SHOP_TYPES:
        raise HTTPException(status_code=400)
    db.execute(
        delete(AllowlistEntry).where(AllowlistEntry.shop_type == shop_type)
    )
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/points/set")
def admin_points_set(
    request: Request,
    tg_username: str = Form(...),
    points: int = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    require_admin(request)
    normalized = normalize_tg_username(tg_username)
    if not normalized:
        raise HTTPException(status_code=400)
    user = db.execute(
        select(User).where(User.tg_username == normalized)
    ).scalar_one_or_none()
    if not user:
        user = User(tg_username=normalized, points=points)
        db.add(user)
    else:
        user.points = points
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/settings/set")
def admin_settings_set(
    request: Request,
    shop_type: str = Form(...),
    opens_at: str = Form(""),
    closes_at: str = Form(""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    require_admin(request)
    if shop_type not in SHOP_TYPES:
        raise HTTPException(status_code=400)
    settings = get_shop_settings(db, shop_type)
    if not settings:
        settings = ShopSettings(shop_type=shop_type)
        db.add(settings)
    settings.opens_at = datetime.fromisoformat(opens_at) if opens_at else None
    settings.closes_at = datetime.fromisoformat(
        closes_at
    ) if closes_at else None
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/product/add")
def admin_product_add(
    request: Request,
    shop_type: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    image_url: Optional[str] = Form(None),
    image_file: Optional[UploadFile] = File(None),
    variants_raw: str = Form(""),
    position: int = Form(0),
    active: Optional[str] = Form(None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    require_admin(request)
    if shop_type not in SHOP_TYPES:
        raise HTTPException(status_code=400)
    upload_url = save_image_upload(image_file)
    final_image_url = upload_url or (image_url.strip() if image_url else None)
    product = Product(
        shop_type=shop_type,
        title=title.strip(),
        description=description.strip() or None,
        image_url=final_image_url,
        position=position,
        active=active == "on",
    )
    db.add(product)
    db.flush()
    for variant_data in parse_variants_raw(variants_raw):
        variant = ProductVariant(
            product_id=product.id,
            label=variant_data["label"],
            points_cost=variant_data["points_cost"],
            stock=variant_data["stock"],
            position=variant_data["position"],
            active=True,
        )
        db.add(variant)
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/product/update")
def admin_product_update(
    request: Request,
    product_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    image_url: Optional[str] = Form(None),
    image_file: Optional[UploadFile] = File(None),
    position: int = Form(0),
    active: Optional[str] = Form(None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    require_admin(request)
    product = db.get(Product, product_id)
    if product:
        upload_url = save_image_upload(image_file)
        product.title = title.strip()
        product.description = description.strip() or None
        if upload_url:
            product.image_url = upload_url
        elif image_url is not None:
            product.image_url = image_url.strip() or None
        product.position = position
        product.active = active == "on"
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/product/photo/delete")
def admin_product_photo_delete(
    request: Request,
    product_id: int = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    require_admin(request)
    product = db.get(Product, product_id)
    if product and product.image_url:
        delete_image_file(product.image_url)
        product.image_url = None
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/product/delete")
def admin_product_delete(
    request: Request,
    product_id: int = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    require_admin(request)
    product = db.get(Product, product_id)
    if product:
        db.delete(product)
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/order/status")
def admin_order_status(
    request: Request,
    order_id: int = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    require_admin(request)
    if status not in ORDER_STATUSES:
        raise HTTPException(status_code=400)
    order = db.get(Order, order_id)
    if order:
        order.status = status
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/variant/add")
def admin_variant_add(
    request: Request,
    product_id: int = Form(...),
    label: str = Form(...),
    points_cost: int = Form(...),
    stock: Optional[str] = Form(None),
    position: Optional[int] = Form(None),
    active: Optional[str] = Form(None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    require_admin(request)
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404)
    final_position = position if position is not None else 0
    variant = ProductVariant(
        product_id=product_id,
        label=label.strip(),
        points_cost=points_cost,
        stock=parse_optional_int(stock),
        position=final_position,
        active=active == "on",
    )
    db.add(variant)
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/variant/update")
def admin_variant_update(
    request: Request,
    variant_id: int = Form(...),
    label: str = Form(...),
    points_cost: int = Form(...),
    stock: Optional[str] = Form(None),
    position: Optional[int] = Form(None),
    active: Optional[str] = Form(None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    require_admin(request)
    variant = db.get(ProductVariant, variant_id)
    if variant:
        variant.label = label.strip()
        variant.points_cost = points_cost
        variant.stock = parse_optional_int(stock)
        if position is not None:
            variant.position = position
        variant.active = active == "on"
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/variant/delete")
def admin_variant_delete(
    request: Request,
    variant_id: int = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    require_admin(request)
    variant = db.get(ProductVariant, variant_id)
    if variant:
        db.delete(variant)
        db.commit()
    return RedirectResponse("/admin", status_code=303)
