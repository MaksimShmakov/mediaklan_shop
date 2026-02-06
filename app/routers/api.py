import html
from typing import Optional

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


class RedeemError(Exception):
    def __init__(self, message: str, code: Optional[str] = None, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def error_response(message: str, status_code: int = 400, code: Optional[str] = None) -> JSONResponse:
    payload = {"ok": False, "message": message}
    if code:
        payload["code"] = code
    return JSONResponse(payload, status_code=status_code)


@router.post("/api/redeem")
def redeem(
    request: Request,
    payload: RedeemRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JSONResponse:
    user = get_current_user(request, db)
    if not user:
        return error_response(
            "\u041d\u0443\u0436\u043d\u0430 \u0430\u0432\u0442\u043e\u0440\u0438\u0437\u0430\u0446\u0438\u044f",
            status_code=401,
            code="unauthorized",
        )

    variant = db.get(ProductVariant, payload.variant_id)
    if not variant or not variant.active or not variant.product or not (
        variant.product.active
    ):
        return error_response(
            "\u041f\u043e\u0437\u0438\u0446\u0438\u044f \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430",
            status_code=400,
        )

    shop_type = variant.product.shop_type
    if shop_type not in SHOP_TYPES:
        return error_response("\u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u043c\u0430\u0433\u0430\u0437\u0438\u043d")
    if not has_access(db, user.tg_username, shop_type):
        return error_response(
            "\u041d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u0430",
            status_code=403,
        )

    settings = get_shop_settings(db, shop_type)
    if not is_shop_open(settings, local_now()):
        return error_response("\u041c\u0430\u0433\u0430\u0437\u0438\u043d \u0437\u0430\u043a\u0440\u044b\u0442")

    order_id = None
    product_title = None
    variant_label = None
    points_cost = None

    try:
        variant = db.get(ProductVariant, payload.variant_id)
        if not variant or not variant.active or not variant.product or not (
            variant.product.active
        ):
            raise RedeemError("\u041f\u043e\u0437\u0438\u0446\u0438\u044f \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430")

        if variant.stock is not None and variant.stock <= 0:
            raise RedeemError(
                "\u0422\u043e\u0432\u0430\u0440 \u0437\u0430\u043a\u043e\u043d\u0447\u0438\u043b\u0441\u044f",
                code="not-enough-tovar",
            )

        product_title = variant.product.title if variant.product else "Товар"
        variant_label = variant.label
        points_cost = variant.points_cost

        points_result = db.execute(
            update(User)
            .where(User.id == user.id, User.points >= variant.points_cost)
            .values(points=User.points - variant.points_cost)
        )
        if points_result.rowcount == 0:
            raise RedeemError(
                "\u041d\u0435\u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u0431\u0430\u043b\u043b\u043e\u0432",
                code="not-enough-points",
            )

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
                raise RedeemError(
                    "\u0422\u043e\u0432\u0430\u0440 \u0437\u0430\u043a\u043e\u043d\u0447\u0438\u043b\u0441\u044f",
                    code="not-enough-tovar",
                )

        order = Order(
            tg_username=user.tg_username,
            product_variant_id=variant.id,
            points_spent=variant.points_cost,
        )
        db.add(order)
        db.commit()
        order_id = order.id
    except RedeemError as exc:
        db.rollback()
        return error_response(
            exc.message,
            status_code=exc.status_code,
            code=exc.code,
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
            "code": "congrat",
        }
    )
