"""Theme: hercomeback brand, one photo in the hero, mocha palette, and accessible focus ring."""

from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
STYLE = APP / "static" / "style.css"
HERO = APP / "static" / "img" / "hero-group.jpg"


def test_brand_is_hercomeback_everywhere_on_home(client):
    html = client.get("/").text
    assert "<title>hercomeback</title>" in html
    assert 'class="logo"><b>her</b>comeback<' in html
    assert "Comeback" not in html.replace(
        "Comeback Buddy", ""
    )  # old brand name must not appear


def test_hero_uses_the_group_photo_with_alt_text(client):
    html = client.get("/").text
    assert 'src="/static/img/hero-group.jpg"' in html
    assert 'alt="Four women working together on a colourful poster"' in html


def test_hero_photo_is_served(client):
    r = client.get("/static/img/hero-group.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/jpeg")
    assert HERO.exists()


def test_cartoon_illustrations_are_removed():
    assert not list((APP / "static" / "img").glob("peep-*.svg"))
    assert "Open Peeps" not in "".join(
        p.read_text(encoding="utf-8") for p in APP.rglob("*.html")
    )


def test_no_leftover_illustration_references(client):
    for path in ["/", "/money", "/contact", "/login", "/register", "/privacy"]:
        assert "peep-" not in client.get(path).text, path


def test_photo_credit_is_in_the_footer(client):
    assert "Photo: Karola G on Pexels (free licence)." in client.get("/").text


def _unused_cards_test(logged_in):
    html = logged_in.get("/").text
    assert html.count('class="tile"') == 6
    assert 'class="tile"><img' not in html


def test_empty_states_are_text_only(logged_in):
    assert "No entries yet" in logged_in.get("/journal").text
    assert "No profile saved yet" in logged_in.get("/profile").text
    assert "Nothing published yet" in logged_in.get("/site").text


def test_palette_is_mocha_not_plum():
    css = STYLE.read_text(encoding="utf-8")
    assert "--acc:#8A6A4F" in css
    assert "#5B2A5E" not in css  # old plum must be gone


def test_focus_ring_uses_accent_colour():
    css = STYLE.read_text(encoding="utf-8")
    assert ":focus-visible{outline:3px solid var(--acc)" in css


def test_stylesheet_link_has_a_content_version(client):
    import re

    html = client.get("/").text
    match = re.search(r'href="/static/style.css\?v=([0-9a-f]{10})"', html)
    assert match, "stylesheet link must carry a version so browsers refetch changes"


def test_signed_in_pages_show_sidebar_and_phone_bar(logged_in):
    html = logged_in.get("/journal").text
    assert 'class="side-nav"' in html and 'class="bottom-nav"' in html
    for path in ["/journal", "/profile", "/jobs", "/money", "/community"]:
        assert f'href="{path}"' in html
    assert 'aria-current="page"' in html
    assert "/static/icons/notebook.svg" in html


def test_greeting_uses_name_from_sign_up(client):
    import uuid

    email = f"named-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/register",
        data={
            "email": email,
            "password": "longpass1",
            "confirm": "longpass1",
            "name": "Ananya",
        },
    )
    assert "Welcome, Ananya" in client.get("/journal").text


def test_greeting_without_a_name_is_plain_welcome(logged_in):
    html = logged_in.get("/journal").text
    assert "Welcome</span>" in html


def test_demo_greets_priya(client):
    client.post("/demo")
    assert "Welcome, Priya" in client.get("/journal").text


def test_home_shows_the_roadmap_linked_to_the_tool_pages(logged_in):
    html = logged_in.get("/").text
    # Each pitstop opens the same page as its left-nav link, and nothing extra in between.
    for path in ["/journal", "/money", "/profile", "/community", "/jobs"]:
        assert f'class="road-link" href="{path}"' in html
    assert "GOAL: BACK TO THE WORKPLACE!" in html
    assert "/roadmap/" not in html


def test_botanical_and_icon_files_are_served(client):
    for path in [
        "/static/img/botanical/money.svg",
        "/static/img/botanical/journal.svg",
        "/static/img/botanical/community.svg",
        "/static/icons/wallet.svg",
    ]:
        assert client.get(path).status_code == 200, path


def test_every_card_has_its_own_botanical_image():
    from app import main

    files = [c[3] for c in main.CARDS.values()]
    assert len(set(files)) == len(files) == 8
    for name in files:
        assert (APP / "static" / "img" / "botanical" / name).exists(), name
