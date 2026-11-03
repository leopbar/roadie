from decimal import Decimal

from roadie.db.models import OrderStatus, ProductStatus
from roadie.ingest.csv_loader import Dataset


def test_counts_match_the_delivered_files(dataset: Dataset):
    assert dataset.counts() == {
        "categories": 9,
        "products": 65,
        "customers": 50,
        "orders": 20,
        "order_items": 22,
        "promotions": 25,
    }


def test_specs_json_is_parsed_even_with_spaces(dataset: Dataset):
    by_id = {p.product_id: p for p in dataset.products}
    assert by_id[81].specs["strings"] == "nylon"
    assert by_id[135].specs == {"body": "Ash", "neck": "Maple", "strings": "4", "color": "Red"}
    assert not any(p.specs.get("_parse_error") for p in dataset.products)


def test_types_are_normalized(dataset: Dataset):
    by_id = {p.product_id: p for p in dataset.products}
    assert by_id[96].price_brl == Decimal("799.9")
    assert by_id[113].status == ProductStatus.discontinued
    assert by_id[130].status == ProductStatus.coming_soon

    orders = {o.order_id: o for o in dataset.orders}
    assert orders[9].tracking_code is None  # vazio vira nulo
    assert orders[9].estimated_delivery is None
    assert orders[17].status == OrderStatus.cancelled
    assert orders[17].notes.startswith("Pedido cancelado")

    customers = {c.customer_id: c for c in dataset.customers}
    assert customers[1].phone_digits == "67998123456"
    assert customers[1].email == "lucas.mendes@jmail.com"


def test_promotions_flag_parsed_as_bool(dataset: Dataset):
    active = sorted(p.promotion_id for p in dataset.promotions if p.is_active)
    assert active == [12, 14, 19, 24]
