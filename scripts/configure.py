"""Create stable local signing material without printing or replacing existing secrets."""

import secrets
from pathlib import Path


def configure(path):
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if not any(
        line.strip().startswith("DJANGO_SECRET_KEY=") and line.split("=", 1)[1].strip()
        for line in existing.splitlines()
    ):
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                ("\n" if existing and not existing.endswith("\n") else "")
                + "DJANGO_SECRET_KEY="
                + secrets.token_urlsafe(64)
                + "\n"
            )
        if __import__("os").name != "nt":
            path.chmod(0o600)


if __name__ == "__main__":
    configure(Path(__file__).resolve().parents[1] / ".env")
    print("Local configuration ready. Existing settings preserved; secrets were not printed.")
