import csv
import json
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from demo import DEFAULT_CATALOG, DEMOS
from matcher import CatalogError, Contractor, Request, filter_candidates, load_catalog, recommend


BASE = Contractor("a", "Тестовый ведущий", ("Ведущий",), "Алматы", 600_000,
                  ("свадьба",), ("русский",), 8, (),
                  "Ведущий: свадьба, интерактивные игры и импровизация.", True, False, False)
QUERY = Request("Алматы", "2026-11-14", "свадьба", "Ведущий", 800_000, 6, "русский")


class MatchingTests(unittest.TestCase):
    def test_deterministic_and_tie_breaker(self):
        catalog = [replace(BASE, id=k) for k in ["d", "b", "c", "a"]]
        result = recommend(catalog, QUERY)
        self.assertEqual(result, recommend(catalog, QUERY))
        self.assertEqual(result, recommend(list(reversed(catalog)), QUERY))
        self.assertEqual([x["contractor"].id for x in result["cards"]], ["a", "b", "c"])
        self.assertEqual(result["eligible_count"], 4)

    def test_busy_never_returned(self):
        result = recommend([replace(BASE, busy_dates=(QUERY.event_date,))], QUERY)
        self.assertEqual(result["status"], "NO_MATCH")
        self.assertEqual(result["cards"], [])
        self.assertEqual(result["rejections"], {"busy": 1})

    def test_budget_boundary(self):
        good = replace(BASE, price_from_kzt=QUERY.budget_kzt)
        bad = replace(BASE, id="b", price_from_kzt=QUERY.budget_kzt + 1)
        result = recommend([good, bad], QUERY)
        self.assertEqual([x["contractor"] for x in result["cards"]], [good])

    def test_event_format_is_mandatory(self):
        result = recommend([replace(BASE, event_formats=("корпоратив",))], QUERY)
        self.assertEqual(result["rejections"], {"event_format": 1})
        self.assertEqual(result["cards"], [])

    def test_city_and_category(self):
        for contractor in (replace(BASE, city="Астана"), replace(BASE, categories=("Фотограф",))):
            self.assertEqual(recommend([contractor], QUERY)["status"], "CATEGORY_NOT_FOUND")
        self.assertEqual(recommend([], QUERY)["status"], "CATEGORY_NOT_FOUND")

    def test_multicategory_and_normalization(self):
        contractor = replace(BASE, categories=("Ведущий церемонии", "Ведущий"))
        query = replace(QUERY, city=" алматы ", category="ВЕДУЩИЙ")
        self.assertEqual(recommend([contractor], query)["status"], "SUCCESS")

    def test_rejection_counts_are_overlapping(self):
        bad = replace(BASE, busy_dates=(QUERY.event_date,), price_from_kzt=900_000,
                      max_hours=3, event_formats=("той",))
        result = recommend([bad], QUERY)
        self.assertEqual(result["rejections"], {"busy": 1, "event_format": 1, "budget": 1, "duration": 1})
        self.assertIn("несколько причин", result["message"])

    def test_one_or_two_results_not_padded(self):
        for count in [1, 2]:
            result = recommend([replace(BASE, id=str(i)) for i in range(count)], QUERY)
            self.assertEqual(len(result["cards"]), count)
            self.assertIn("Менее трёх", result["message"])

    def test_duration_null_boundary_and_optional(self):
        for hours in [None, 6, 8]:
            self.assertEqual(recommend([replace(BASE, max_hours=hours)], QUERY)["status"], "SUCCESS")
        self.assertEqual(recommend([replace(BASE, max_hours=5)], QUERY)["status"], "NO_MATCH")
        self.assertEqual(recommend([replace(BASE, max_hours=1)], replace(QUERY, duration_hours=None))["status"], "SUCCESS")

    def test_language_is_a_soft_preference_and_mismatch_is_disclosed(self):
        mismatch = replace(BASE, id="b", languages=("казахский",))
        result = recommend([mismatch, BASE], QUERY)
        self.assertEqual(result["cards"][0]["contractor"], BASE)
        self.assertIn("не указан", result["cards"][1]["explanation"])

    def test_cheapest_is_not_automatically_first(self):
        cheaper = replace(BASE, id="b", price_from_kzt=100_000)
        self.assertEqual(recommend([cheaper, BASE], QUERY)["cards"][0]["contractor"], BASE)

    def test_description_changes_ranking(self):
        unrelated = replace(BASE, id="0", description="Портретная съёмка на плёнку.")
        result = recommend([unrelated, BASE], QUERY)
        self.assertEqual(result["cards"][0]["contractor"], BASE)
        self.assertGreater(result["cards"][0]["score_parts"]["Описание"], 0)

    def test_explanation_is_grounded(self):
        explanation = recommend([BASE], QUERY)["cards"][0]["explanation"]
        for fact in (BASE.anon_name, "600 000 ₸", "800 000 ₸", "14.11.2026", "6 ч", "8 ч", BASE.description):
            self.assertIn(fact, explanation)

    def test_request_validation(self):
        for changes in [{"budget_kzt": 0}, {"budget_kzt": float("nan")}, {"duration_hours": -1},
                        {"event_date": "2026-02-30"}, {"event_date": "20261114"}, {"city": ""}]:
            with self.assertRaises(ValueError):
                replace(QUERY, **changes)


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog(DEFAULT_CATALOG)

    def test_supplied_catalog_parsing(self):
        self.assertEqual(len(self.catalog), 66)
        self.assertEqual(sum(c.synthetic for c in self.catalog), 13)
        self.assertEqual(sum(c.max_hours is None for c in self.catalog), 9)
        self.assertEqual(sum(c.city_imputed for c in self.catalog), 8)
        self.assertEqual(sum(c.price_imputed for c in self.catalog), 18)
        self.assertEqual(len({c.id for c in self.catalog}), 66)

    def test_fixed_demos(self):
        expected = [("SUCCESS", 3, 4), ("SUCCESS", 1, 1), ("NO_MATCH", 0, 0), ("CATEGORY_NOT_FOUND", 0, 0)]
        for query, (status, cards, eligible) in zip(DEMOS.values(), expected):
            result = recommend(self.catalog, query)
            self.assertEqual((result["status"], len(result["cards"]), result["eligible_count"]), (status, cards, eligible))

    def test_every_busy_date_in_source_is_excluded(self):
        for c in self.catalog:
            for day in c.busy_dates:
                request = Request(c.city, day, c.event_formats[0], c.categories[0], 10_000_000)
                _, survivors, rejected = filter_candidates([c], request)
                self.assertEqual(survivors, [])
                self.assertEqual(rejected["busy"], 1)

    def test_real_results_satisfy_all_constraints(self):
        for city in ("Алматы", "Астана"):
            for category in ("Ведущий", "Фотограф", "Флорист", "Отель"):
                for day in ("2026-10-01", "2026-11-14", "2026-12-31"):
                    request = Request(city, day, "свадьба", category, 1_000_000, 6, "казахский")
                    result = recommend(self.catalog, request)
                    self.assertEqual(result, recommend(list(reversed(self.catalog)), request))
                    self.assertLessEqual(len(result["cards"]), 3)
                    for card in result["cards"]:
                        c = card["contractor"]
                        self.assertEqual(c.city, city)
                        self.assertIn(category, c.categories)
                        self.assertNotIn(day, c.busy_dates)
                        self.assertIn("свадьба", c.event_formats)
                        self.assertLessEqual(c.price_from_kzt, 1_000_000)
                        self.assertTrue(c.max_hours is None or c.max_hours >= 6)

    def test_malformed_catalogs_fail_closed(self):
        base = asdict(BASE)
        mutations = [dict(base, busy_dates=["14/11/2026"]), dict(base, synthetic="no"),
                     dict(base, price_from_kzt="unknown"), dict(base, city=""),
                     dict(base, max_hours=-1), {k: v for k, v in base.items() if k != "busy_dates"}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "catalog.json"
            for row in mutations:
                path.write_text(json.dumps([row]), encoding="utf-8")
                with self.assertRaises(CatalogError):
                    load_catalog(path)
            path.write_text(json.dumps([base, base]), encoding="utf-8")
            with self.assertRaises(CatalogError):
                load_catalog(path)

    def test_csv_false_and_empty_list_and_null_hours(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "catalog.csv"
            row = asdict(BASE)
            for key in ("categories", "event_formats", "languages", "busy_dates"):
                row[key] = "|".join(row[key])
            row.update(synthetic="False", max_hours="")
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=row.keys())
                writer.writeheader()
                writer.writerow(row)
            parsed = load_catalog(path)[0]
            self.assertFalse(parsed.synthetic)
            self.assertIsNone(parsed.max_hours)
            self.assertEqual(parsed.busy_dates, ())


if __name__ == "__main__":
    unittest.main()
