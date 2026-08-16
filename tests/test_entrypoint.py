"""The package entry point exposes only local GUI startup options."""

from office_translate.gui import launcher


def test_package_entrypoint_forwards_gui_options(monkeypatch):
    calls = []

    def fake_launch(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(launcher, "launch", fake_launch)
    monkeypatch.setattr(
        "sys.argv",
        [
            "office_translate",
            "-c",
            "custom.yaml",
            "-g",
            "custom-glossary.json",
            "--port",
            "8765",
            "--no-webview",
        ],
    )
    launcher.main()
    assert calls == [
        {
            "config_path": "custom.yaml",
            "glossary_path": "custom-glossary.json",
            "port": 8765,
            "use_webview": False,
        }
    ]
