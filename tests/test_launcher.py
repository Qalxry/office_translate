"""Launcher and offline frontend boundary tests."""

from pathlib import Path

import pytest

from office_translate.gui.launcher import _local_url, _validate_localhost


ROOT = Path(__file__).parents[1]
WEB_DIR = ROOT / "office_translate" / "gui" / "web"


def test_launcher_accepts_only_loopback_hosts():
    assert _validate_localhost("127.0.0.1") == "127.0.0.1"
    assert _validate_localhost("localhost") == "localhost"
    assert _validate_localhost("::1") == "::1"
    assert _local_url("127.0.0.1", 8765) == "http://127.0.0.1:8765"
    assert _local_url("::1", 8765) == "http://[::1]:8765"

    for host in ("0.0.0.0", "192.168.1.20", "example.test", ""):
        with pytest.raises(ValueError):
            _validate_localhost(host)


def test_frontend_is_offline_and_does_not_forward_loaded_api_keys():
    index = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    app = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert 'src="vendor/vue.global.prod.js"' in index
    assert "unpkg.com" not in index
    assert "vendor/vue.global.prod.js" in app or "normalizeSettingsForUi" in app
    assert "api_key: provider.api_key" not in app
    assert "provider_id: this.activeProviderKey" in app
    assert "api_key: ''" in app


def test_local_vue_vendor_is_present():
    vendor = WEB_DIR / "vendor" / "vue.global.prod.js"
    assert vendor.is_file()
    # A runtime-sized, checked-in production bundle is expected; a tiny stub
    # would make the GUI appear to work while failing on first load offline.
    assert vendor.stat().st_size > 100_000
    assert "Vue" in vendor.read_text(encoding="utf-8")
