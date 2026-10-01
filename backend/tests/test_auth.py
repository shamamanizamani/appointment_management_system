from datetime import timedelta

from app.core import time
from app.models import AccountStatus, Role

REGISTER = {"name": "Ali Khan", "email": "Ali@Example.com", "password": "Secret@123"}


def assert_error(r, status: int, code: str):
    assert r.status_code == status, r.text
    body = r.json()
    assert body["error"]["code"] == code
    assert body["error"]["message"]


async def test_register_creates_customer_and_logs_in(client):
    r = await client.post("/api/v1/auth/register", json={**REGISTER, "role": "admin"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["role"] == "customer"  # role in the body is ignored
    assert body["user"]["email"] == "ali@example.com"  # stored lowercase
    assert body["token_type"] == "bearer"

    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["email"] == "ali@example.com"


async def test_register_duplicate_email(client):
    await client.post("/api/v1/auth/register", json=REGISTER)
    r = await client.post("/api/v1/auth/register", json={**REGISTER, "email": "ALI@example.com"})
    assert_error(r, 409, "EMAIL_TAKEN")


async def test_register_validation_error_shape(client):
    r = await client.post("/api/v1/auth/register", json={**REGISTER, "password": "short"})
    assert_error(r, 422, "VALIDATION_ERROR")
    assert r.json()["error"]["fields"][0]["field"] == "password"


async def test_login_and_me(client, make_user, login):
    await make_user(Role.staff)
    r = await client.get("/api/v1/me", headers=await login("staff@example.com"))
    assert r.status_code == 200
    assert r.json()["role"] == "staff"


async def test_login_form_for_swagger(client, make_user):
    await make_user(Role.manager)
    r = await client.post(
        "/api/v1/auth/token", data={"username": "manager@example.com", "password": "Secret@123"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["role"] == "manager"


async def test_wrong_password_and_unknown_email(client, make_user):
    await make_user()
    for email, pw in [("customer@example.com", "Wrong@123"), ("nobody@example.com", "Secret@123")]:
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": pw})
        assert_error(r, 401, "INVALID_CREDENTIALS")


async def test_suspended_user_cannot_log_in(client, make_user):
    await make_user(account_status=AccountStatus.suspended)
    r = await client.post(
        "/api/v1/auth/login", json={"email": "customer@example.com", "password": "Secret@123"}
    )
    assert_error(r, 403, "ACCOUNT_SUSPENDED")


async def test_missing_and_garbage_token(client):
    assert_error(await client.get("/api/v1/me"), 401, "NOT_AUTHENTICATED")
    r = await client.get("/api/v1/me", headers={"Authorization": "Bearer nope"})
    assert_error(r, 401, "INVALID_TOKEN")


async def test_expired_access_token(client, make_user, login):
    await make_user()
    time._frozen = time.now() - timedelta(minutes=31)  # token issued 31 min ago, lives 30
    headers = await login("customer@example.com")
    time._frozen = None
    assert_error(await client.get("/api/v1/me", headers=headers), 401, "TOKEN_EXPIRED")


async def test_refresh(client, make_user):
    await make_user()
    tokens = (
        await client.post(
            "/api/v1/auth/login", json={"email": "customer@example.com", "password": "Secret@123"}
        )
    ).json()

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == "customer@example.com"

    # an access token is not accepted as a refresh token
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert_error(r, 401, "INVALID_TOKEN")


async def test_update_me(client, make_user, login):
    await make_user(phone="03001234567")
    headers = await login("customer@example.com")

    r = await client.patch("/api/v1/me", headers=headers, json={"name": "  New Name  "})
    assert r.json()["name"] == "New Name"
    assert r.json()["phone"] == "03001234567"  # untouched

    r = await client.patch("/api/v1/me", headers=headers, json={"phone": None})
    assert r.json()["phone"] is None

    r = await client.patch("/api/v1/me", headers=headers, json={"phone": "abc"})
    assert_error(r, 422, "VALIDATION_ERROR")


async def test_customer_blocked_from_admin_route(client, make_user, login):
    await make_user(Role.customer)
    await make_user(Role.admin)

    r = await client.get("/api/v1/admin/users", headers=await login("customer@example.com"))
    assert_error(r, 403, "FORBIDDEN")

    r = await client.get("/api/v1/admin/users", headers=await login("admin@example.com"))
    assert r.status_code == 200
    assert r.json()["total"] == 2


async def test_health_and_unknown_route(client):
    assert (await client.get("/health")).json()["status"] == "ok"
    assert_error(await client.get("/nope"), 404, "NOT_FOUND")
