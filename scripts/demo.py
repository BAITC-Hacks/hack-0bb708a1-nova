"""Print the same deterministic scenarios offered by the UI."""
from eventmatch.paths import CATALOG_PATH
from eventmatch.domain.matcher import load_catalog, recommend
from eventmatch.ui.demo_scenarios import DEMOS


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
