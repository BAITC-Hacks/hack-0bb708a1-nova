"""Fixed, reproducible scenarios using the supplied catalog."""

import os
from pathlib import Path

from matcher import Request, load_catalog, recommend

ROOT = Path(__file__).resolve().parent
DEFAULT_CATALOG = ROOT / "data" / "hackathon dataset anonymized .csv"
CATALOG_PATH = Path(os.environ.get("NOVA_DATASET", str(DEFAULT_CATALOG)))

DEMOS = {
    "Плотная категория": Request("Алматы", "2026-11-02", "свадьба", "Ведущий", 2_000_000, 6, "русский"),
    "Редкая категория": Request("Алматы", "2026-11-14", "свадьба", "Флорист", 400_000, None, "русский"),
    "Нет подходящих вариантов": Request("Алматы", "2026-11-14", "свадьба", "Ведущий", 1_000, 6, "русский"),
    "Нет категории в локации": Request("Астана", "2026-11-14", "свадьба", "Декоратор", 400_000),
}


if __name__ == "__main__":
    catalog = load_catalog(CATALOG_PATH)
    for title, request in DEMOS.items():
        result = recommend(catalog, request)
        print(f"\n{title}\n{result['status']}: {result['message']}")
        for card in result["cards"]:
            c = card["contractor"]
            print(f"  {c.id} | {c.anon_name} | {card['score']:.3f} | "
                  f"{'Синтетический профиль' if c.synthetic else 'Исходный профиль'}")
            print(f"  {card['explanation']}")
