import runpy
from pathlib import Path


def test_configuration_preserves_settings_and_signing_key(tmp_path):
    configure = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "configure.py"))[
        "configure"
    ]
    path = tmp_path / ".env"
    path.write_text("DASHBOARD_PORT=3001", encoding="utf-8")
    configure(path)
    first = path.read_text(encoding="utf-8")
    configure(path)
    assert path.read_text(encoding="utf-8") == first
    assert first.startswith("DASHBOARD_PORT=3001\n")
    assert len(first.split("DJANGO_SECRET_KEY=")[1].strip()) >= 64
