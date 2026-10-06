"""Health, registration, login and token handling."""

from tests.conftest import TEST_PASSWORD, make_user


def test_health_needs_no_token(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"


def test_register_then_use_the_returned_token(client):
    response = client.post(
        "/api/auth/register",
        json={"name": "New User", "email": "New.User@Test.local", "password": "longenough123"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    # Email is normalised to lower case on the way in.
    assert body["user"]["email"] == "new.user@test.local"

    me = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "new.user@test.local"


def test_register_rejects_a_duplicate_email(client, owner):
    response = client.post(
        "/api/auth/register",
        json={"name": "Impostor", "email": owner.email, "password": "longenough123"},
    )
    assert response.status_code == 409


def test_register_rejects_a_bad_email(client):
    response = client.post(
        "/api/auth/register",
        json={"name": "No At Sign", "email": "not-an-email", "password": "longenough123"},
    )
    assert response.status_code == 422


def test_register_rejects_a_password_over_72_bytes(client):
    """bcrypt truncates silently at 72 bytes, so the API refuses instead."""
    response = client.post(
        "/api/auth/register",
        json={"name": "Long", "email": "long@test.local", "password": "a" * 73},
    )
    assert response.status_code == 422


def test_validation_error_does_not_echo_the_password(client):
    secret = "supersecret-password"
    response = client.post(
        "/api/auth/register",
        json={"name": "", "email": "bad", "password": secret},
    )
    assert response.status_code == 422
    assert secret not in response.text


def test_login_with_the_wrong_password_is_401(client, owner):
    response = client.post(
        "/api/auth/login", json={"email": owner.email, "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_login_for_an_unknown_email_gives_the_same_message(client, owner):
    """Identical response, so the endpoint cannot enumerate registered addresses."""
    unknown = client.post(
        "/api/auth/login",
        json={"email": "nobody@test.local", "password": TEST_PASSWORD},
    )
    wrong = client.post(
        "/api/auth/login", json={"email": owner.email, "password": "wrong-password"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_me_without_a_token_is_401(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_a_garbage_token_is_401(client):
    response = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"}
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_token_for_a_deleted_user_is_rejected(client, db):
    """A valid signature for an account that no longer exists is not a login."""
    doomed = make_user(db, "doomed@test.local")
    token = client.post(
        "/api/auth/login", json={"email": doomed.email, "password": TEST_PASSWORD}
    ).json()["access_token"]

    db.delete(doomed)
    db.flush()

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
