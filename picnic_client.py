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


def add_ingredients_to_cart(ingredients: list[str]) -> dict:
    """Search Picnic for each ingredient and add the top result to cart.

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
            product = None
            for category in results:
                items = category.get("items", [])
                if items:
                    product = items[0]
                    break

            if product is None:
                not_found.append(ingredient)
                continue

            product_id = product["id"]
            product_name = product.get("name", product_id)
            client.add_product(product_id, count=1)
            added.append({
                "ingredient": ingredient,
                "product_name": product_name,
                "product_id": product_id,
            })
        except Exception as e:
            logger.error(f"Error adding ingredient '{ingredient}': {e}")
            not_found.append(ingredient)

    return {"added": added, "not_found": not_found}
