import io
from datetime import timedelta

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from sqlalchemy import select
from starlette.datastructures import Headers

from test_admin_users import setup
from app.core.time import local_now
from app.models import AllowlistEntry, Order, Product, ProductVariant, ShopSettings, User
from app.services.products import prepare_single_product_catalog
from app.services import uploads


def create(client, **changes):
    data = dict(shop_type='regular', title='Кружка', description='Описание', points_cost='100', stock='2', position='3', active='on')
    data.update(changes)
    return client.post('/admin/product/add', data=data, headers={'X-Requested-With': 'fetch'})


@pytest.mark.parametrize('shop', ['regular', 'premium'])
def test_product_lifecycle_and_purchase(setup, shop):
    client, factory, _ = setup
    assert create(client, shop_type=shop).status_code == 200
    with factory() as db:
        product = db.scalar(select(Product))
        pid, vid = product.id, product.variants[0].id
        assert product.variants[0].points_cost == 100
        assert product.variants[0].stock == 2
        assert len(product.variants) == 1
        db.add(ShopSettings(shop_type=shop, opens_at=local_now() - timedelta(hours=1), closes_at=local_now() + timedelta(hours=1)))
        db.add(AllowlistEntry(tg_username='@buyer', shop_type=shop))
        db.commit()
    assert 'store-row' in client.get(f'/shop/{shop}').text
    assert 'store-grid' not in client.get(f'/shop/{shop}').text
    page = client.get('/admin').text
    assert 'catalog-summary' in page and 'name="variants_raw"' not in page
    assert 'action="/admin/variant/' not in page
    assert client.post('/register', data={'tg_username': 'buyer', 'password': 'buyer-test', 'password_confirm': 'buyer-test'}).status_code == 200
    client.post('/admin/points/set', data={'tg_username': 'buyer', 'points': 500})
    # Edit all business fields through the single product form.
    assert client.post('/admin/product/update', data={'product_id': pid, 'title': 'Новая кружка', 'description': 'Новое описание', 'points_cost': 120, 'stock': 1, 'position': 7, 'active': 'on'}).status_code == 200
    assert client.post('/api/redeem', json={'variant_id': vid}).json()['ok'] is True
    assert client.post('/api/redeem', json={'variant_id': vid}).json()['code'] == 'not-enough-tovar'
    with factory() as db:
        product = db.get(Product, pid)
        assert (product.title, product.position, product.description) == ('Новая кружка', 7, 'Новое описание')
        assert product.variants[0].stock == 0
        assert db.scalar(select(User.points).where(User.tg_username == '@buyer')) == 380
        assert db.scalar(select(Order.product_variant_id)) == vid
    # Sold products are deactivated, not erased along with their order references.
    assert client.post('/admin/product/delete', data={'product_id': pid}).status_code == 200
    with factory() as db:
        assert not db.get(Product, pid).active
        assert db.scalar(select(Order.product_variant_id)) == vid
    assert 'Новая кружка' not in client.get(f'/shop/{shop}').text
    assert client.get('/admin/orders/export').status_code == 200


@pytest.mark.parametrize('fields', [dict(points_cost=-1), dict(stock=-1), dict(stock='1.5'), dict(position=-1), dict(title='  '), dict(points_cost=2147483648)])
def test_invalid_fields_do_not_create_products(setup, fields):
    client, factory, _ = setup
    assert create(client, **fields).status_code == 400
    with factory() as db:
        assert list(db.scalars(select(Product))) == []


def test_unlimited_stock_and_inactive_products(setup):
    client, factory, _ = setup
    assert create(client, stock='', active='').status_code == 200
    with factory() as db:
        product = db.scalar(select(Product))
        assert product.variants[0].stock is None
        assert not product.active
    assert 'Кружка' not in client.get('/shop/regular').text
    client.get('/admin/logout')
    assert create(client).status_code == 403


def test_legacy_variants_split_idempotently_preserving_orders(setup):
    _, factory, _ = setup
    with factory() as db:
        product = Product(title='Сертификат', shop_type='premium', position=4, active=True, image_url='/static/uploads/shared.jpg', description='Описание')
        product.variants = [ProductVariant(label='1000', points_cost=150, stock=2, active=True), ProductVariant(label='2000', points_cost=300, stock=None, active=False)]
        empty = Product(title='Пустой', shop_type='regular', active=True)
        db.add_all([product, empty])
        db.flush()
        ids = [v.id for v in product.variants]
        db.add_all(Order(tg_username='@buyer', product_variant_id=vid, points_spent=50) for vid in ids)
        db.commit()
        prepare_single_product_catalog(db)
        db.commit()
    with factory() as db:
        prepare_single_product_catalog(db)
        db.commit()
        products = list(db.scalars(select(Product)))
        assert len(products) == 3
        assert all(len(p.variants) == 1 for p in products)
        assert set(db.scalars(select(Order.product_variant_id))) == set(ids)
        for vid, title, active, cost, stock in [(ids[0], 'Сертификат — 1000', True, 150, 2), (ids[1], 'Сертификат — 2000', False, 300, None)]:
            variant = db.get(ProductVariant, vid)
            assert (variant.product.title, variant.product.active, variant.points_cost, variant.stock) == (title, active, cost, stock)
            assert variant.product.image_url == '/static/uploads/shared.jpg'
        assert next(p for p in products if p.title == 'Пустой').variants[0].stock == 0


def test_shared_photo_and_retired_variant_endpoints(setup, tmp_path, monkeypatch):
    client, factory, _ = setup
    monkeypatch.setattr(uploads, 'UPLOAD_DIR', tmp_path)
    (tmp_path / 'shared.jpg').write_bytes(b'photo')
    with factory() as db:
        products = [Product(title=name, shop_type='regular', image_url='/static/uploads/shared.jpg') for name in ('A', 'B')]
        db.add_all(products)
        db.commit()
        ids = [p.id for p in products]
    assert client.post('/admin/product/photo/delete', data={'product_id': ids[0]}).status_code == 200
    assert (tmp_path / 'shared.jpg').exists()
    assert client.post('/admin/product/photo/delete', data={'product_id': ids[1]}).status_code == 200
    assert not (tmp_path / 'shared.jpg').exists()
    assert client.post('/admin/variant/add').status_code == 410


@pytest.mark.parametrize('fmt', ['JPEG', 'PNG', 'WEBP', 'GIF', 'AVIF', 'HEIF', 'BMP', 'TIFF'])
def test_photo_formats_are_decoded_even_with_generic_mime(fmt, tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, 'UPLOAD_DIR', tmp_path)
    content = io.BytesIO()
    Image.new('RGB', (20, 10), 'red').save(content, format=fmt)
    upload = UploadFile(io.BytesIO(content.getvalue()), filename='PHOTO.UNKNOWN', headers=Headers({'content-type': 'application/octet-stream'}))
    url = uploads.save_image_upload(upload)
    with Image.open(tmp_path / url.split('/')[-1]) as result:
        assert result.format == 'JPEG' and result.size == (20, 10)


def test_transparency_rotation_and_invalid_photo(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, 'UPLOAD_DIR', tmp_path)
    content = io.BytesIO()
    Image.new('RGBA', (20, 10), (255, 0, 0, 0)).save(content, format='PNG')
    url = uploads.save_image_upload(UploadFile(io.BytesIO(content.getvalue()), filename='PHOTO.PNG'))
    with Image.open(tmp_path / url.split('/')[-1]) as result:
        assert result.mode == 'RGBA' and result.getpixel((0, 0))[3] == 0
    content = io.BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    Image.new('RGB', (20, 10)).save(content, format='JPEG', exif=exif)
    url = uploads.save_image_upload(UploadFile(io.BytesIO(content.getvalue()), filename='photo.jpg'))
    with Image.open(tmp_path / url.split('/')[-1]) as result:
        assert result.size == (10, 20)
    before = set(tmp_path.iterdir())
    for content in (b'not an image', b'<svg></svg>'):
        with pytest.raises(HTTPException) as error:
            uploads.save_image_upload(UploadFile(io.BytesIO(content), filename='fake.jpg'))
        assert error.value.status_code == 400
    monkeypatch.setattr(uploads, 'MAX_IMAGE_BYTES', 4)
    with pytest.raises(HTTPException, match='15 МБ'):
        uploads.save_image_upload(UploadFile(io.BytesIO(b'12345'), filename='big.jpg'))
    assert set(tmp_path.iterdir()) == before


def test_http_upload_and_update_errors(setup, tmp_path, monkeypatch):
    client, factory, _ = setup
    monkeypatch.setattr(uploads, 'UPLOAD_DIR', tmp_path)
    data = dict(shop_type='regular', title='Фото', points_cost=20, stock=2)
    assert client.post('/admin/product/add', data=data, files={'image_file': ('file.jpg', b'bad', 'image/jpeg')}).status_code == 400
    content = io.BytesIO()
    Image.new('RGB', (10, 10)).save(content, format='PNG')
    assert client.post('/admin/product/add', data=data, files={'image_file': ('PHOTO.PNG', content.getvalue(), 'application/octet-stream')}).status_code == 200
    with factory() as db:
        product = db.scalar(select(Product))
        pid, original = product.id, product.image_url
        assert (tmp_path / original.split('/')[-1]).exists()
    assert client.post('/admin/product/update', data=dict(product_id=pid, title='Changed', points_cost=20, stock=-1)).status_code == 400
    with factory() as db:
        assert db.get(Product, pid).title == 'Фото'
        assert db.get(Product, pid).image_url == original


def test_catalog_pagination_and_zero_stock(setup):
    client, factory, _ = setup
    with factory() as db:
        for shop in ('regular', 'premium'):
            for i in range(31):
                product = Product(title=f'{shop}-{i:02}', shop_type=shop, position=i)
                product.variants = [ProductVariant(label='', points_cost=10, stock=0)]
                db.add(product)
        db.commit()
    page = client.get('/admin').text
    assert page.count('class="catalog-item"') == 60
    assert 'regular-30' not in page and 'premium-30' not in page
    page = client.get('/admin?products_page_regular=2&products_page_premium=2').text
    assert page.count('class="catalog-item"') == 2
    assert 'regular-30' in page and 'premium-30' in page
    with factory() as db:
        product = db.scalar(select(Product).where(Product.title == 'regular-00'))
        pid = product.id
    assert 'Закончился' in client.get('/shop/regular').text
    detail = client.get(f'/shop/regular/product/{pid}').text
    assert 'Купить' in detail and 'Подберите вариант' not in detail


def test_catalog_migration_rolls_back_on_failure(setup):
    from sqlalchemy import event
    _, factory, _ = setup
    with factory() as db:
        product = Product(title='Original', shop_type='regular')
        product.variants = [ProductVariant(label=str(i), points_cost=i, stock=i) for i in (1, 2)]
        db.add(product)
        db.commit()
        pid = product.id
    engine = factory.kw['bind']
    def fail_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO products'):
            raise RuntimeError('migration test failure')
    event.listen(engine, 'before_cursor_execute', fail_insert)
    try:
        with factory() as db, pytest.raises(RuntimeError, match='migration test failure'):
            prepare_single_product_catalog(db)
    finally:
        event.remove(engine, 'before_cursor_execute', fail_insert)
    with factory() as db:
        product = db.get(Product, pid)
        assert product.title == 'Original' and len(product.variants) == 2
        assert len(list(db.scalars(select(Product)))) == 1


def test_photo_pixel_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, 'UPLOAD_DIR', tmp_path)
    monkeypatch.setattr(uploads, 'MAX_IMAGE_PIXELS', 10)
    content = io.BytesIO()
    Image.new('RGB', (4, 4)).save(content, format='PNG')
    with pytest.raises(HTTPException, match='40 мегапикселей'):
        uploads.save_image_upload(UploadFile(io.BytesIO(content.getvalue()), filename='photo.png'))
    assert not list(tmp_path.iterdir())
