from typing import Optional


def parse_optional_int(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    return int(value)


def prepare_single_product_catalog(db) -> None:
    """Idempotently split legacy variants without changing order references."""
    from sqlalchemy import select, text
    from sqlalchemy.orm import selectinload
    from app.models import Product, ProductVariant

    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(74192631)"))
    products = db.scalars(select(Product).options(selectinload(Product.variants))).all()
    for product in products:
        variants = list(product.variants)
        if not variants:
            # An unconfigured old product must never become a free unlimited item.
            product.variants.append(ProductVariant(label="", points_cost=0, stock=0))
        elif len(variants) > 1:
            title = product.title
            active = product.active
            for index, variant in enumerate(variants):
                item_title = f"{title} — {variant.label or index + 1}"[:200]
                if index == 0:
                    product.title = item_title
                    product.active = active and variant.active
                else:
                    item = Product(
                        shop_type=product.shop_type, title=item_title,
                        description=product.description, image_url=product.image_url,
                        position=product.position, active=active and variant.active,
                        created_at=product.created_at,
                    )
                    db.add(item)
                    variant.product = item
        elif not variants[0].active:
            product.active = False
    db.flush()


def validate_product_fields(title: str, points_cost: int, stock: Optional[str], position: int) -> Optional[int]:
    from fastapi import HTTPException
    if not title.strip() or len(title.strip()) > 200:
        raise HTTPException(400, "Название должно содержать от 1 до 200 символов")
    try:
        quantity = parse_optional_int(stock)
    except ValueError:
        raise HTTPException(400, "Количество должно быть целым неотрицательным числом")
    if not 0 <= points_cost <= 2147483647 or not 0 <= position <= 2147483647:
        raise HTTPException(400, "Стоимость и позиция должны быть от 0 до 2147483647")
    if quantity is not None and not 0 <= quantity <= 2147483647:
        raise HTTPException(400, "Количество должно быть от 0 до 2147483647; пусто — без ограничений")
    return quantity
