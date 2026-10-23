import unittest

from nexus_services.platform_catalog import get_platform_catalog


class PlatformCatalogTests(unittest.TestCase):
    def test_fixed_platform_inventory_is_present(self):
        names = {item["name"] for item in get_platform_catalog()}
        self.assertTrue({"Amazon", "Shopify", "Alibaba", "eBay", "1xBet"}.issubset(names))

    def test_category_filter_returns_only_that_category(self):
        items = get_platform_catalog("ecommerce")
        self.assertEqual({item["category"] for item in items}, {"ecommerce"})

    def test_catalog_result_is_a_copy(self):
        items = get_platform_catalog()
        items.clear()
        self.assertTrue(get_platform_catalog())


if __name__ == "__main__":
    unittest.main()
