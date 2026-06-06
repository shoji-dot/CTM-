"""
CRUD business logic unit tests

  - [C5] Customer delete integrity
  - [C6] Quote delete integrity
  - [I5] Inventory minus prevention
  - Product delete integrity
  - Paginator
"""

import pytest
from datetime import date
from decimal import Decimal
from fastapi import HTTPException

import crud
import models


class TestCustomerCrud:
    def test_create_and_get(self, db):
        c = crud.create_customer(db, {"name": "Test Hospital", "category": "hospital"})
        assert crud.get_customer(db, c.id).name == "Test Hospital"

    def test_update(self, db):
        c = crud.create_customer(db, {"name": "Old Name", "category": "hospital"})
        crud.update_customer(db, c.id, {"name": "New Name"})
        assert crud.get_customer(db, c.id).name == "New Name"

    def test_delete_no_relations(self, db, sample_customer):
        result = crud.delete_customer(db, sample_customer.id)
        assert result is not None
        assert crud.get_customer(db, sample_customer.id) is None

    def test_delete_nonexistent_returns_none(self, db):
        assert crud.delete_customer(db, 9999) is None


class TestCustomerDeleteIntegrity:
    """[C5] Customer cannot be deleted if related data exists."""

    def test_block_with_quote(self, db, sample_customer):
        q = models.Quote(quote_number="Q-001", customer_id=sample_customer.id, status="draft")
        db.add(q)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            crud.delete_customer(db, sample_customer.id)
        assert exc.value.status_code == 400
        assert "見積" in exc.value.detail

    def test_block_with_sale(self, db, sample_customer, sample_product):
        s = models.Sale(
            sale_number="S-001",
            customer_id=sample_customer.id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal("10000"),
            subtotal=Decimal("10000"),
            tax_amount=Decimal("1000"),
            total_amount=Decimal("11000"),
            sale_date=date.today(),
            status="confirmed",
        )
        db.add(s)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            crud.delete_customer(db, sample_customer.id)
        assert exc.value.status_code == 400
        assert "売上" in exc.value.detail

    def test_block_with_shipment(self, db, sample_customer, sample_product):
        inv = db.query(models.Inventory).filter_by(product_id=sample_product.id).first()
        inv.current_stock = 5
        db.commit()
        ship = models.Shipment(
            shipment_number="SH-001",
            customer_id=sample_customer.id,
            product_id=sample_product.id,
            quantity=1,
            shipment_type="sale",
            status="shipped",
            shipped_date=date.today(),
        )
        db.add(ship)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            crud.delete_customer(db, sample_customer.id)
        assert exc.value.status_code == 400
        assert "出荷" in exc.value.detail

    def test_block_with_repair(self, db, sample_customer, sample_product):
        repair = models.Repair(
            repair_number="REP-001",
            customer_id=sample_customer.id,
            product_id=sample_product.id,
            received_date=date.today(),
            fault_description="test fault",
            status="received",
        )
        db.add(repair)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            crud.delete_customer(db, sample_customer.id)
        assert exc.value.status_code == 400
        assert "修理" in exc.value.detail

    def test_block_with_demo_loan(self, db, sample_customer, sample_product):
        unit = models.DemoUnit(unit_code="DEMO-001", product_id=sample_product.id, status="available")
        db.add(unit)
        db.flush()
        loan = models.DemoLoan(
            demo_unit_id=unit.id,
            customer_id=sample_customer.id,
            loan_date=date.today(),
            due_date=date.today(),
        )
        db.add(loan)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            crud.delete_customer(db, sample_customer.id)
        assert exc.value.status_code == 400
        assert "デモ" in exc.value.detail


class TestProductDeleteIntegrity:
    def test_delete_no_relations(self, db, sample_product):
        assert crud.delete_product(db, sample_product.id) is not None

    def test_block_with_stock(self, db, sample_product):
        inv = db.query(models.Inventory).filter_by(product_id=sample_product.id).first()
        inv.current_stock = 3
        db.commit()
        with pytest.raises(HTTPException) as exc:
            crud.delete_product(db, sample_product.id)
        assert exc.value.status_code == 400
        assert "在庫" in exc.value.detail

    def test_block_with_quote_item(self, db, sample_product, sample_customer):
        q = models.Quote(quote_number="Q-P-001", customer_id=sample_customer.id, status="draft")
        db.add(q)
        db.flush()
        qi = models.QuoteItem(
            quote_id=q.id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal("10000"),
            subtotal=Decimal("10000"),
        )
        db.add(qi)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            crud.delete_product(db, sample_product.id)
        assert exc.value.status_code == 400
        assert "見積明細" in exc.value.detail


class TestQuoteDeleteIntegrity:
    """[C6] Quote cannot be deleted if a Sale is attached."""

    def test_delete_no_sales(self, db, sample_customer):
        q = models.Quote(quote_number="Q-D-001", customer_id=sample_customer.id, status="draft")
        db.add(q)
        db.commit()
        assert crud.delete_quote(db, q.id) is not None
        assert db.query(models.Quote).filter_by(id=q.id).first() is None

    def test_block_with_sale(self, db, sample_customer, sample_product):
        q = models.Quote(quote_number="Q-D-002", customer_id=sample_customer.id, status="confirmed")
        db.add(q)
        db.flush()
        s = models.Sale(
            sale_number="S-QD-001",
            customer_id=sample_customer.id,
            product_id=sample_product.id,
            quote_id=q.id,
            quantity=1,
            unit_price=Decimal("10000"),
            subtotal=Decimal("10000"),
            tax_amount=Decimal("1000"),
            total_amount=Decimal("11000"),
            sale_date=date.today(),
            status="confirmed",
        )
        db.add(s)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            crud.delete_quote(db, q.id)
        assert exc.value.status_code == 400
        assert "売上" in exc.value.detail


class TestInventory:
    """[I5] Inventory minus prevention."""

    def test_stock_in(self, db, sample_product):
        crud.move_inventory(db, sample_product.id, "in", 10, reason="purchase")
        inv = db.query(models.Inventory).filter_by(product_id=sample_product.id).first()
        assert inv.current_stock == 10

    def test_stock_out(self, db, sample_product):
        crud.move_inventory(db, sample_product.id, "in", 10)
        crud.move_inventory(db, sample_product.id, "out", 3)
        inv = db.query(models.Inventory).filter_by(product_id=sample_product.id).first()
        assert inv.current_stock == 7

    def test_prevent_negative_stock(self, db, sample_product):
        crud.move_inventory(db, sample_product.id, "in", 2)
        with pytest.raises(ValueError) as exc:
            crud.move_inventory(db, sample_product.id, "out", 5)
        assert "在庫不足" in str(exc.value)

    def test_stock_zero_out_raises(self, db, sample_product):
        with pytest.raises(ValueError):
            crud.move_inventory(db, sample_product.id, "out", 1)

    def test_allow_negative_flag(self, db, sample_product):
        crud.move_inventory(db, sample_product.id, "out", 1, allow_negative=True)
        inv = db.query(models.Inventory).filter_by(product_id=sample_product.id).first()
        assert inv.current_stock == 0

    def test_history_recorded(self, db, sample_product):
        crud.move_inventory(db, sample_product.id, "in", 5, reason="test")
        history = db.query(models.InventoryHistory).filter_by(product_id=sample_product.id).all()
        assert len(history) == 1
        assert history[0].movement_type == "in"
        assert history[0].quantity == 5


class TestPaginator:
    def test_basic(self, db):
        for i in range(5):
            db.add(models.Customer(name=f"Customer{i}", category="hospital"))
        db.commit()
        p = crud.paginate(db.query(models.Customer), page=1, per_page=3)
        assert p.total == 5
        assert len(p.items) == 3
        assert p.total_pages == 2
        assert p.has_next is True
        assert p.has_prev is False

    def test_page2(self, db):
        for i in range(5):
            db.add(models.Customer(name=f"Customer{i}", category="hospital"))
        db.commit()
        p = crud.paginate(db.query(models.Customer), page=2, per_page=3)
        assert len(p.items) == 2
        assert p.has_prev is True
        assert p.has_next is False
