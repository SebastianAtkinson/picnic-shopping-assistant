import logging
from python_picnic_api2 import PicnicAPI
from config import PICNIC_USERNAME, PICNIC_PASSWORD, PICNIC_AUTH_TOKEN

logger = logging.getLogger(__name__)

_client: PicnicAPI | None = None


def get_picnic_client() -> PicnicAPI:
    global _client
    if _client is None:
        if PICNIC_AUTH_TOKEN:
            _client = PicnicAPI(auth_token=PICNIC_AUTH_TOKEN, country_code="NL")
        else:
            _client = PicnicAPI(username=PICNIC_USERNAME, password=PICNIC_PASSWORD, country_code="NL")
    return _client


def _select_best_product(items: list[dict]) -> dict | None:
    """Select the best product using this priority:
    1. Biological/organic (bio in name) — always preferred over non-bio
    2. Picnic house brand — preferred within the same bio tier
    3. Price ascending — cheaper options before expensive brands
    """
    if not items:
        return None

    def score(product):
        name = product.get("name", "").lower()
        is_bio = any(kw in name for kw in ("bio", "biologisch", "organic"))
        is_picnic = "picnic" in name
        price = product.get("display_price", 999_999)

        if is_bio and is_picnic:
            tier = 0
        elif is_bio:
            tier = 1
        elif is_picnic:
            tier = 2
        else:
            tier = 3

        return (tier, price)

    return min(items, key=score)


def add_ingredients_to_cart(ingredients: list[str]) -> dict:
    """Search Picnic for each ingredient and add the best result to cart.

    Returns:
        {
            "added": [{"ingredient": str, "product_name": str, "product_id": str}],
            "not_found": [str]
        }
    """
    client = get_picnic_client()
    added = []
    not_found = []

    for ingredient in ingredients:
        try:
            results = client.search(ingredient)
            all_items = [item for category in results for item in category.get("items", [])]
            product = _select_best_product(all_items)

            if product is None:
                not_found.append(ingredient)
                continue

            product_id = product["id"]
            product_name = product.get("name", product_id)
            client.add_product(product_id, count=1)
            added.append({
                "ingredient": ingredient,
                "product_name": product_name,
            })
        except Exception as e:
            logger.error(f"Error adding ingredient '{ingredient}': {e}")
            not_found.append(ingredient)

    return {"added": added, "not_found": not_found}
