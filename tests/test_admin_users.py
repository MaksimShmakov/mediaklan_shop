import io
import os
import re
import tempfile

# Never use an application/production database in this suite.
_test_dir = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = 'sqlite:///' + _test_dir.name + '/test.db'
os.environ['ADMIN_PASSWORD'] = 'test-admin-only'
os.environ['SESSION_SECRET'] = 'test-session-only'

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models import AllowlistEntry, Order, Product, ProductVariant, User
from app.services.users import parse_delete_usernames


@pytest.fixture
def setup(tmp_path):
    # Optional explicit disposable PostgreSQL DB for production-dialect checks.
    engine = create_engine(os.getenv('TEST_DATABASE_URL', f'sqlite:///{tmp_path}/test.db'))
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def enable_fk(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    def override_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        client.post('/admin/login', data={'password': 'test-admin-only'})
        page = client.get('/admin')
        assert page.status_code == 200
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        yield client, factory, token
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def seed(factory):
    with factory() as db:
        db.add_all([User(tg_username='@alice', points=700), User(tg_username='@bob', points=300),
                    User(tg_username='@keep', points=50),
                    AllowlistEntry(tg_username='@alice', shop_type='regular'),
                    AllowlistEntry(tg_username='@alice', shop_type='premium'),
                    AllowlistEntry(tg_username='@invited', shop_type='premium'),
                    AllowlistEntry(tg_username='@keep', shop_type='regular')])
        product = Product(title='Test', shop_type='regular')
        db.add(product)
        db.flush()
        variant = ProductVariant(product_id=product.id, label='Test', points_cost=10, stock=5)
        db.add(variant)
        db.flush()
        db.add_all([Order(tg_username=name, product_variant_id=variant.id, points_spent=10)
                    for name in ('@alice', '@bob', '@keep')])
        db.commit()


def test_export_all_users_and_numeric_points(setup):
    client, factory, _ = setup
    seed(factory)
    with factory() as db:
        db.add_all(User(tg_username=f'@person{i}', points=i) for i in range(60))
        db.add(User(tg_username='=1+1', points=0))
        db.commit()
    response = client.get('/admin/users/export?user_search=alice&users_page=2')
    assert response.status_code == 200
    assert '.xlsx' in response.headers['content-disposition']
    sheet = load_workbook(io.BytesIO(response.content)).active
    rows = list(sheet.values)
    assert rows[0] == ('Telegram', 'Баллы')
    assert len(rows) == 66
    values = dict(rows[1:])
    assert values['@alice'] == 700 and values['@invited'] == 0
    assert isinstance(values['@alice'], int)
    assert all(cell.data_type != 'f' for row in sheet for cell in row)
    assert values['=1+1'] == 0


def test_delete_only_listed_users_and_related_data(setup):
    client, factory, token = setup
    seed(factory)
    response = client.post('/admin/users/delete-bulk', data={
        'raw': 'Alice\n@BOB, @alice; invited | missing', 'confirmed': 'yes', 'csrf_token': token,
    }, headers={'X-Requested-With': 'fetch'})
    assert response.status_code == 200
    assert response.json()['deleted'] == {'users': 2, 'orders': 2, 'allowlist': 3}
    assert response.json()['missing'] == 1
    with factory() as db:
        for model in (User, Order, AllowlistEntry):
            assert list(db.scalars(select(model.tg_username))) == ['@keep']
        assert db.scalar(select(ProductVariant.stock)) == 5
    # Repeated submission is harmless.
    response = client.post('/admin/users/delete-bulk', data={
        'raw': 'alice\nbob\ninvited', 'confirmed': 'yes', 'csrf_token': token,
    }, headers={'X-Requested-With': 'fetch'})
    assert response.json()['deleted'] == {'users': 0, 'orders': 0, 'allowlist': 0}


@pytest.mark.parametrize('raw', ['', '   ', '@alice 500', '@alice\nhttps://t.me/bob', '@alice\n*', '@', 'a'*33])
def test_invalid_input_is_atomic(setup, raw):
    client, factory, token = setup
    seed(factory)
    response = client.post('/admin/users/delete-bulk', data={
        'raw': raw, 'confirmed': 'yes', 'csrf_token': token,
    })
    assert response.status_code == 400
    with factory() as db:
        assert len(list(db.scalars(select(User)))) == 3
        assert len(list(db.scalars(select(Order)))) == 3


def test_admin_and_confirmation_required(setup):
    client, factory, token = setup
    seed(factory)
    assert client.post('/admin/users/delete-bulk', data={'raw': 'alice', 'csrf_token': token}).status_code == 400
    assert client.post('/admin/users/delete-bulk', data={'raw': 'alice', 'confirmed': 'yes'}).status_code == 403
    assert client.post('/admin/users/delete-bulk', data={'raw': 'alice', 'confirmed': 'yes', 'csrf_token': 'неверный'}).status_code == 403
    client.get('/admin/logout')
    assert client.get('/admin/users/export').status_code == 403
    assert client.post('/admin/users/delete-bulk', data={'raw': 'alice', 'confirmed': 'yes', 'csrf_token': token}).status_code == 403
    with factory() as db:
        assert len(list(db.scalars(select(User)))) == 3


def test_empty_export(setup):
    client, _, _ = setup
    sheet = load_workbook(io.BytesIO(client.get('/admin/users/export').content)).active
    assert list(sheet.values) == [('Telegram', 'Баллы')]


def test_large_list_and_non_ajax_result(setup):
    client, factory, token = setup
    with factory() as db:
        db.add_all(User(tg_username=f'@person{i}', points=i) for i in range(1000))
        db.commit()
    response = client.post('/admin/users/delete-bulk', data={
        'raw': '\n'.join(f'person{i}' for i in range(1000)), 'confirmed': 'yes', 'csrf_token': token,
    })
    assert response.status_code == 200
    assert 'Удалено ников: 1000' in response.text
    with factory() as db:
        assert list(db.scalars(select(User))) == []
    with pytest.raises(ValueError):
        parse_delete_usernames('\n'.join(f'person{i}' for i in range(1001)))


def test_transaction_rolls_back_on_failure(setup):
    client, factory, token = setup
    seed(factory)
    engine = factory.kw['bind']
    def fail_users_delete(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('DELETE FROM users'):
            raise RuntimeError('simulated database failure')
    event.listen(engine, 'before_cursor_execute', fail_users_delete)
    try:
        with pytest.raises(RuntimeError, match='simulated database failure'):
            client.post('/admin/users/delete-bulk', data={'raw': 'alice', 'confirmed': 'yes', 'csrf_token': token})
    finally:
        event.remove(engine, 'before_cursor_execute', fail_users_delete)
    with factory() as db:
        assert len(list(db.scalars(select(User)))) == 3
        assert len(list(db.scalars(select(Order)))) == 3
        assert len(list(db.scalars(select(AllowlistEntry)))) == 4


REPORTED_LIST = '''@welltyza
@werrhus
@wgliks
@wixngzaa
@wow_dasha_traveler
@wuw381
@wwilkh3
@wwwillll
@wxbhns
@xcx_1999
@xiusaq
@xmashasx
@ya._.chinese
@yan_ cheer
@yarchesnoviy
@yarwiks
@ylkaul
@youarmy_hope
@yourronyaa
@yulivast
@zla_tawq'''


def test_reported_list_deletes_exact_legacy_names_only(setup):
    client, factory, token = setup
    names = REPORTED_LIST.splitlines()
    survivors = ['@yan_', '@cheer', '@yan_cheer', '@ya__chinese']
    with factory() as db:
        db.add_all(User(tg_username=name, points=10) for name in names + survivors)
        db.add_all(AllowlistEntry(tg_username=name, shop_type='regular') for name in names + survivors)
        db.commit()
    response = client.post('/admin/users/delete-bulk', data={
        'raw': REPORTED_LIST, 'confirmed': 'yes', 'csrf_token': token,
    }, headers={'X-Requested-With': 'fetch'})
    assert response.status_code == 200
    assert response.json()['deleted'] == {'users': 21, 'orders': 0, 'allowlist': 21}
    with factory() as db:
        for model in (User, AllowlistEntry):
            assert set(db.scalars(select(model.tg_username))) == set(survivors)


def test_unknown_spaced_name_is_not_split_or_repaired(setup):
    client, factory, token = setup
    seed(factory)
    with factory() as db:
        db.add_all(User(tg_username=name, points=10) for name in ('@yan_', '@cheer', '@yan_cheer'))
        db.commit()
    response = client.post('/admin/users/delete-bulk', data={
        'raw': '@alice\n@yan_ cheer', 'confirmed': 'yes', 'csrf_token': token,
    }, headers={'X-Requested-With': 'fetch'})
    assert response.status_code == 400
    assert '@yan_ cheer' in response.json()['message']
    with factory() as db:
        assert len(list(db.scalars(select(User)))) == 6
        assert len(list(db.scalars(select(Order)))) == 3


def test_dot_names_and_explicit_separators():
    assert parse_delete_usernames('@ya._.chinese\r\n@ALICE; bob,\t@alice|@missing') == [
        '@ya._.chinese', '@alice', '@bob', '@missing',
    ]
    with pytest.raises(ValueError, match='@alice @bob'):
        parse_delete_usernames('@alice @bob')
