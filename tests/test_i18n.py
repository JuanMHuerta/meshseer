import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "src" / "meshseer" / "static"


def _catalog_keys(source: str, catalog_name: str) -> set[str]:
    pattern = rf"const {catalog_name} = Object\.freeze\(\{{(?P<body>.*?)\n  \}}\);"
    match = re.search(pattern, source, re.S)
    assert match is not None, f"missing {catalog_name} catalog"
    return set(re.findall(r'^\s+"([^"]+)":', match.group("body"), re.M))


def test_spanish_catalog_matches_english_catalog_keys():
    source = (STATIC_DIR / "i18n.js").read_text(encoding="utf-8")

    english_keys = _catalog_keys(source, "EN")
    spanish_keys = _catalog_keys(source, "ES")

    assert spanish_keys - english_keys == set()
    assert english_keys - spanish_keys == set()
    assert len(english_keys) >= 100


def test_static_and_dynamic_translation_references_are_defined():
    i18n_source = (STATIC_DIR / "i18n.js").read_text(encoding="utf-8")
    app_source = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    html_source = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    catalog_keys = _catalog_keys(i18n_source, "EN")
    referenced_keys = set(re.findall(r'\bt\("([^"]+)"', app_source))
    referenced_keys.update(re.findall(r'labelKey: "([^"]+)"', app_source))
    referenced_keys.update(re.findall(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', html_source))

    assert referenced_keys
    assert referenced_keys - catalog_keys == set()


def test_i18n_script_loads_before_app_script():
    html_source = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert html_source.index('/static/i18n.js') < html_source.index('/static/app.js')


def test_readme_language_links_are_bidirectional():
    english_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    spanish_readme = (ROOT / "README.es.md").read_text(encoding="utf-8")

    assert "[English](README.md) | [Español](README.es.md)" in english_readme
    assert "[English](README.md) | [Español](README.es.md)" in spanish_readme
