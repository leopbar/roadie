from decimal import Decimal

from roadie.db.models import FlagSeverity
from roadie.ingest.csv_loader import CategoryRow, Dataset, ProductRow
from roadie.ingest.quality import brand_of, find_brands, group_flags, run_all, worst_severity


def _flags_for(flags, entity, entity_id):
    return {f.flag for f in flags if f.entity == entity and f.entity_id == str(entity_id)}


def test_brand_detection_handles_compound_and_prefix_names():
    assert brand_of("Music Man Bass 1X Electric Bass") == "Music Man"
    assert brand_of("Bateria Acústica Yamaha Kit 1 Studio") == "Yamaha"
    assert brand_of("Kala KA-15S Soprano Mogno") == "Kala"
    assert brand_of("Kalani KAL-300S Soprano Natural") == "Kalani"
    assert find_brands("Contrabaixo elétrico Fender Jazz Bass com corpo em Alder") == ["Fender"]
    assert brand_of("Violão genérico sem marca conhecida") is None


def test_real_dataset_quarantines_the_contradictory_products(dataset: Dataset):
    flags = run_all(dataset)
    # baixos, baterias e teclados com nome de uma marca e descrição de outra
    for pid in (135, 137, 139, 140, 142, 144):
        assert "brand_mismatch" in _flags_for(flags, "product", pid), pid
    # descrição fala em 88 teclas / 5 cordas, specs dizem 61 / 4
    assert "spec_mismatch" in _flags_for(flags, "product", 142)
    assert "spec_mismatch" in _flags_for(flags, "product", 137)
    # preços implausíveis para a categoria
    assert "price_outlier" in _flags_for(flags, "product", 136)
    assert "price_outlier" in _flags_for(flags, "product", 142)
    # produtos consistentes não são quarentenados
    for pid in (87, 93, 95, 106, 131, 133, 141, 143, 145):
        grouped = group_flags(flags).get(("product", str(pid)), [])
        assert worst_severity(grouped) in (None, FlagSeverity.info, FlagSeverity.warning), (
            pid,
            grouped,
        )


def test_real_dataset_flags_orders_customers_categories(dataset: Dataset):
    flags = run_all(dataset)
    assert "total_mismatch" in _flags_for(flags, "order", 3)
    assert "total_mismatch" in _flags_for(flags, "order", 20)
    assert "total_mismatch" not in _flags_for(flags, "order", 15)
    assert "preorder_item" in _flags_for(flags, "order", 14)
    assert "zero_stock_active" in _flags_for(flags, "product", 96)
    assert "discontinued_with_stock" in _flags_for(flags, "product", 136)
    # categorias de sopro e cordas orquestrais não têm produtos
    assert {f.entity_id for f in flags if f.flag == "empty_category"} == {"6", "7", "8"}
    # clientes com e-mail repetido e quase homônimos
    assert "duplicate_email" in _flags_for(flags, "customer", 11)
    assert "duplicate_email" in _flags_for(flags, "customer", 43)
    dup_details = " ".join(f.detail for f in flags if f.flag == "possible_duplicate")
    assert "Bruno Carvalho Martins" in dup_details and "Diego Fernandes Castro" in dup_details


def test_price_outlier_uses_category_median():
    cats = [CategoryRow(category_id=1, name="x")]
    base = dict(category_id=1, status="active", stock_quantity=1)
    products = [
        ProductRow(product_id=1, price_brl=Decimal("100"), name="Yamaha A", **base),
        ProductRow(product_id=2, price_brl=Decimal("120"), name="Yamaha B", **base),
        ProductRow(product_id=3, price_brl=Decimal("110"), name="Yamaha C", **base),
        ProductRow(product_id=4, price_brl=Decimal("10"), name="Yamaha D", **base),
    ]
    ds = Dataset(categories=cats, products=products)
    flags = run_all(ds)
    assert _flags_for(flags, "product", 4) == {"price_outlier"}
    assert not _flags_for(flags, "product", 1)
