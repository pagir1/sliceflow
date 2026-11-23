import tracking


def login(client, user_id, pin):
    return client.post("/login", data={"user_id": user_id, "pin": pin}, follow_redirects=False)


def test_pages_need_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    r = client.get("/kitchen", follow_redirects=False)
    assert r.headers["location"] == "/login"


def test_htmx_request_without_login_gets_hx_redirect(client):
    r = client.post("/cart/add/1", headers={"HX-Request": "true"})
    assert r.headers["HX-Redirect"] == "/login"


def test_cashier_can_use_cashier_screen_but_not_kitchen(client):
    r = login(client, 1, "1111")
    assert r.headers["location"] == "/"
    assert client.get("/").status_code == 200
    assert client.get("/kitchen").status_code == 403          # NFR-07


def test_kitchen_can_use_kitchen_screen_but_not_cashier(client):
    r = login(client, 2, "2222")
    assert r.headers["location"] == "/kitchen"
    assert client.get("/kitchen").status_code == 200
    assert client.get("/").status_code == 403


def test_manager_can_open_both(client):
    r = login(client, 3, "9999")
    assert r.headers["location"] == "/manager"
    assert client.get("/").status_code == 200
    assert client.get("/kitchen").status_code == 200


def test_wrong_pin_shows_error(client):
    r = login(client, 1, "0000")
    assert r.status_code == 401 and "Wrong PIN" in r.text


def test_logout_ends_the_session(client):
    login(client, 1, "1111")
    client.post("/logout", follow_redirects=False)
    assert client.get("/", follow_redirects=False).status_code == 303


def test_customer_pages_stay_public(client):
    assert client.get("/board").status_code == 200
    assert client.get("/login").status_code == 200
    assert client.get(tracking.track_path(1)).status_code == 404     # no order 1 yet, but no login wall


def test_only_manager_can_open_manager_screen(client):
    login(client, 1, "1111")
    assert client.get("/manager").status_code == 403
    client.post("/logout")
    login(client, 3, "9999")
    assert client.get("/manager").status_code == 200