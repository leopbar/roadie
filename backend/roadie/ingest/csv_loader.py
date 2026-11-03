"""Leitura e normalização dos CSVs fornecidos pela loja.

Os arquivos são lidos exatamente como foram entregues (nomes com espaço e
tudo). Cada linha passa por um modelo Pydantic que normaliza tipos, converte
vazios em nulos e extrai campos derivados (ex.: telefone só com dígitos).
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from roadie.db.models import OrderStatus, ProductStatus

FILE_SUFFIXES = {
    "categories": "categories.csv",
    "customers": "customers.csv",
    "orders": "orders.csv",
    "order_items": "order_items.csv",
    "products": "products.csv",
    "promotions": "promotions.csv",
}


def find_csv(data_dir: Path, key: str) -> Path:
    suffix = FILE_SUFFIXES[key]
    matches = sorted(p for p in data_dir.glob(f"*{suffix}") if p.name.endswith(suffix))
    if not matches:
        raise FileNotFoundError(f"nenhum arquivo *{suffix} em {data_dir}")
    return matches[0]


def only_digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


class _Row(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _blank_to_none(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {
                k: (None if isinstance(v, str) and v.strip() == "" else v) for k, v in data.items()
            }
        return data


class CategoryRow(_Row):
    category_id: int
    name: str
    description: str | None = None


class ProductRow(_Row):
    product_id: int
    price_brl: Decimal
    name: str
    category_id: int
    description: str | None = None
    stock_quantity: int = 0
    status: ProductStatus
    specs: dict[str, Any] = Field(default_factory=dict)
    created_at: date | None = None

    @field_validator("specs", mode="before")
    @classmethod
    def _parse_specs(cls, value: Any) -> Any:
        if value is None:
            return {}
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {"_raw": value, "_parse_error": True}
            return parsed if isinstance(parsed, dict) else {"_raw": parsed}
        return value

    @field_validator("name", "description")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class CustomerRow(_Row):
    customer_id: int
    name: str
    phone: str | None = None
    email: str | None = None
    city: str | None = None

    @property
    def phone_digits(self) -> str | None:
        digits = only_digits(self.phone)
        return digits or None

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str | None) -> str | None:
        return value.strip().lower() if isinstance(value, str) else value


class OrderRow(_Row):
    order_id: int
    customer_id: int
    order_date: date
    status: OrderStatus
    total_brl: Decimal
    payment_method: str | None = None
    tracking_code: str | None = None
    estimated_delivery: date | None = None
    notes: str | None = None


class OrderItemRow(_Row):
    order_id: int
    quantity: int = 1
    product_id: int


class PromotionRow(_Row):
    promotion_id: int
    product_id: int
    discount_percent: Decimal
    description: str | None = None
    is_active: bool = False

    @field_validator("is_active", mode="before")
    @classmethod
    def _parse_bool(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "sim", "yes", "t"}
        return bool(value) if value is not None else False


@dataclass
class Dataset:
    categories: list[CategoryRow] = field(default_factory=list)
    products: list[ProductRow] = field(default_factory=list)
    customers: list[CustomerRow] = field(default_factory=list)
    orders: list[OrderRow] = field(default_factory=list)
    order_items: list[OrderItemRow] = field(default_factory=list)
    promotions: list[PromotionRow] = field(default_factory=list)
    sources: dict[str, Path] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        return {
            "categories": len(self.categories),
            "products": len(self.products),
            "customers": len(self.customers),
            "orders": len(self.orders),
            "order_items": len(self.order_items),
            "promotions": len(self.promotions),
        }


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_dataset(data_dir: Path) -> Dataset:
    """Carrega os seis CSVs e valida linha a linha."""
    ds = Dataset()
    ds.sources = {key: find_csv(data_dir, key) for key in FILE_SUFFIXES}
    ds.categories = [CategoryRow(**r) for r in _read_rows(ds.sources["categories"])]
    ds.products = [ProductRow(**r) for r in _read_rows(ds.sources["products"])]
    ds.customers = [CustomerRow(**r) for r in _read_rows(ds.sources["customers"])]
    ds.orders = [OrderRow(**r) for r in _read_rows(ds.sources["orders"])]
    ds.order_items = [OrderItemRow(**r) for r in _read_rows(ds.sources["order_items"])]
    ds.promotions = [PromotionRow(**r) for r in _read_rows(ds.sources["promotions"])]
    return ds
