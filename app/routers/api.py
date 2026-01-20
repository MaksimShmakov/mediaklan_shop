import html

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import SHOP_TYPES, TG_BOT_TOKEN, TG_GROUP_CHAT_ID
from app.core.database import get_db
from app.core.time import local_now
from app.integrations.telegram import send_telegram_message
from app.models import Order, ProductVariant, User
from app.schemas.orders import RedeemRequest
from app.services.auth import get_current_user
from app.services.shops import get_shop_settings, has_access, is_shop_open

router = APIRouter()


@router.post("/api/redeem")
def redeem(
    request: Request,
    payload: RedeemRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JSONResponse:
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(
            {"ok": False, "message": "Нужна авторизация"},
            status_code=401
        )

    variant = db.get(ProductVariant, payload.variant_id)
    if not variant or not variant.active or not variant.product or not (
        variant.product.active
    ):
        return JSONResponse(
            {"ok": False, "message": "Позиция недоступна"},
            status_code=400
        )

    shop_type = variant.product.shop_type
    if shop_type not in SHOP_TYPES:
        return JSONResponse(
            {"ok": False, "message": "Неверный магазин"},
            status_code=400
        )
    if not has_access(db, user.tg_username, shop_type):
        return JSONResponse(
            {"ok": False, "message": "Нет доступа"},
            status_code=403
        )

    settings = get_shop_settings(db, shop_type)
    if not is_shop_open(settings, local_now()):
        return JSONResponse(
            {"ok": False, "message": "Магазин закрыт"},
            status_code=400
        )

    order_id = None
    product_title = None
    variant_label = None
    points_cost = None

    try:
        variant = db.get(ProductVariant, payload.variant_id)
        if not variant or not variant.active or not variant.product or not (
            variant.product.active
        ):
            raise ValueError("Позиция недоступна")

        if variant.stock is not None and variant.stock <= 0:
            raise ValueError("Товар закончился")

        product_title = variant.product.title if variant.product else "Товар"
        variant_label = variant.label
        points_cost = variant.points_cost

        points_result = db.execute(
            update(User)
            .where(User.id == user.id, User.points >= variant.points_cost)
            .values(points=User.points - variant.points_cost)
        )
        if points_result.rowcount == 0:
            raise ValueError("Недостаточно баллов")

        if variant.stock is not None:
            stock_result = db.execute(
                update(ProductVariant)
                .where(
                    ProductVariant.id == variant.id,
                    ProductVariant.stock > 0
                )
                .values(stock=ProductVariant.stock - 1)
            )
            if stock_result.rowcount == 0:
                raise ValueError("Товар закончился")

        order = Order(
            tg_username=user.tg_username,
            product_variant_id=variant.id,
            points_spent=variant.points_cost,
        )
        db.add(order)
        db.commit()
        order_id = order.id
    except ValueError as exc:
        db.rollback()
        return JSONResponse(
            {"ok": False, "message": str(exc)},
            status_code=400
        )
    except Exception:
        db.rollback()
        return JSONResponse(
            {"ok": False, "message": "Ошибка сервера. Попробуйте позже."},
            status_code=500,
        )

    if order_id and TG_BOT_TOKEN and TG_GROUP_CHAT_ID:
        shop_label = "Премиум" if shop_type == "premium" else "Обычный"
        message = (
            "<b>Новый заказ</b>\n"
            f"Пользователь: {html.escape(user.tg_username)}\n"
            f"Магазин: {shop_label}\n"
            f"Товар: {html.escape(product_title or '')}\n"
            f"Вариант: {html.escape(variant_label or '')}\n"
            f"Списано: {points_cost or 0} баллов\n"
            f"ID заказа: {order_id}"
        )
        background_tasks.add_task(send_telegram_message, message)

    new_points = db.execute(
        select(User.points).where(User.id == user.id)
    ).scalar_one()
    return JSONResponse(
        {
            "ok": True,
            "message": "Заказ оформлен. Мы свяжемся с вами в Telegram.",
            "points": new_points,
        }
    )
