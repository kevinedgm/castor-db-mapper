"""Install Castor Claude Code agents and skills into a target project, without overwriting."""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def install(target: Path, force: bool = False) -> list[Path]:
    if not target.is_dir():
        raise ValueError(f"Target project is not a directory: {target}")
    copied = []
    for base in ("agents", "skills"):
        source = ROOT / ".claude" / base
        for item in sorted(source.rglob("*")):
            if not item.is_file():
                continue
            dest = target / ".claude" / base / item.relative_to(source)
            if dest.exists() and not force:
                print(f"SKIP {dest} (use --force to replace)")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            copied.append(dest)
            print(f"COPY {dest}")
    return copied


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Install Castor agents/skills into a project")
    p.add_argument("project", type=Path)
    p.add_argument("--force", action="store_true", help="Overwrite Castor agent/skill files")
    args = p.parse_args()
    install(args.project.resolve(), force=args.force)
