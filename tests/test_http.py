"""
HTTP endpoint tests

  - Login flow (success / failure)
  - Auth guard (unauthenticated -> redirect)
  - [C7] Invoice delete -> Sale.status restored to "confirmed"
  - Customer create POST
"""

import pytest
from datetime import date
from decimal import Decimal

import models
from auth import create_session_token, hash_password


class TestLogin:
    def test_login_page_accessible(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200

    def test_login_success_redirects(self, client, admin_staff):
        resp = client.post(
            "/login",
            data={"login_id": "testadmin", "password": "testpass123"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "session" in resp.cookies

    def test_login_wrong_password(self, client, admin_staff):
        resp = client.post(
            "/login",
            data={"login_id": "testadmin", "password": "wrongpass"},
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "session" not in resp.cookies

    def test_login_nonexistent_user(self, client):
        resp = client.post(
            "/login",
            data={"login_id": "nobody", "password": "pass"},
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "session" not in resp.cookies

    def test_logout_clears_session(self, auth_client):
        c, _ = auth_client
        resp = c.get("/logout", follow_redirects=False)
        assert resp.status_code == 303


class TestAuthGuard:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/customers", follow_redirects=False)
        # middleware returns 307
        assert resp.status_code in (302, 303, 307, 308)
        assert "/login" in resp.headers.get("location", "")

    def test_authenticated_customer_list(self, auth_client):
        c, _ = auth_client
        resp = c.get("/customers")
        assert resp.status_code == 200

    def test_authenticated_product_list(self, auth_client):
        c, _ = auth_client
        resp = c.get("/products")
        assert resp.status_code == 200

    def test_authenticated_inventory(self, auth_client):
        c, _ = auth_client
        resp = c.get("/inventory")
        assert resp.status_code == 200


class TestInvoiceDeleteRestoresSaleStatus:
    """[C7] Invoice delete must restore Sale.status to 'confirmed'."""

    def _setup(self, db, customer, product):
        sale = models.Sale(
            sale_number="S-INV-001",
            customer_id=customer.id,
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10000"),
            subtotal=Decimal("10000"),
            tax_amount=Decimal("1000"),
            total_amount=Decimal("11000"),
            sale_date=date.today(),
            status="invoiced",
        )
        db.add(sale)
        db.flush()
        invoice = models.Invoice(
            invoice_number="INV-001",
            customer_id=customer.id,
            issue_date=date.today(),
            subtotal=Decimal("10000"),
            tax_amount=Decimal("1000"),
            total_amount=Decimal("11000"),
            status="unpaid",
        )
        db.add(invoice)
        db.flush()
        db.add(models.InvoiceItem(
            invoice_id=invoice.id,
            sale_id=sale.id,
            amount=Decimal("11000"),
        ))
        db.commit()
        db.refresh(sale)
        db.refresh(invoice)
        return sale, invoice

    def test_delete_restores_sale_status(self, auth_client, db, sample_customer, sample_product):
        c, _ = auth_client
        sale, invoice = self._setup(db, sample_customer, sample_product)
        assert sale.status == "invoiced"

        resp = c.post(f"/invoices/{invoice.id}/delete", follow_redirects=False)
        assert resp.status_code == 303

        db.expire_all()
        assert db.query(models.Sale).filter_by(id=sale.id).first().status == "confirmed"

    def test_non_admin_forbidden(self, client, db, sample_customer, sample_product):
        user = models.Staff(
            name="Normal User",
            login_id="normaluser",
            password_hash=hash_password("pass"),
            role="user",
            is_active=True,
        )
        db.add(user)
        db.commit()
        sale, invoice = self._setup(db, sample_customer, sample_product)

        client.cookies.set("session", create_session_token(user.id))
        resp = client.post(f"/invoices/{invoice.id}/delete", follow_redirects=False)
        assert resp.status_code == 403

        db.expire_all()
        assert db.query(models.Sale).filter_by(id=sale.id).first().status == "invoiced"


class TestProductEdit:
    """商品編集ルート (GET/POST /products/{id}/edit)"""

    def test_edit_form_accessible(self, auth_client, db, sample_product):
        c, _ = auth_client
        resp = c.get(f"/products/{sample_product.id}/edit")
        assert resp.status_code == 200
        assert sample_product.name.encode() in resp.content

    def test_edit_form_404_for_missing(self, auth_client):
        c, _ = auth_client
        resp = c.get("/products/99999/edit")
        assert resp.status_code == 404

    def test_edit_post_updates_product(self, auth_client, db, sample_product):
        c, _ = auth_client
        resp = c.post(
            f"/products/{sample_product.id}/edit",
            data={
                "name": "更新済み商品名",
                "category": "medical",
                "sku": "",
                "unit_price": "99000",
                "unit": "台",
                "tracking_type": "serial",
                "stock_alert_threshold": "5",
                "alert_enabled": "on",
                "maker": "",
                "jan_code": "",
                "approval_number": "",
                "device_class": "",
                "sales_role": "",
                "model_spec": "",
                "sterility": "",
                "notes": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        db.expire_all()
        updated = db.query(models.Product).filter_by(id=sample_product.id).first()
        assert updated.name == "更新済み商品名"
        assert updated.unit_price == 99000

    def test_redirect_from_product_detail(self, auth_client, db, sample_product):
        c, _ = auth_client
        resp = c.get(f"/products/{sample_product.id}", follow_redirects=False)
        assert resp.status_code == 302
        assert f"/products/{sample_product.id}/edit" in resp.headers.get("location", "")


class TestCustomerCreate:
    def test_create_redirects(self, auth_client):
        c, _ = auth_client
        resp = c.post(
            "/customers/new",
            data={"name": "New Hospital", "category": "hospital",
                  "phone": "", "email": "", "address": "",
                  "trading_terms": "", "notes": "", "staff_id": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers.get("location", "").endswith("/customers")

    def test_create_persisted(self, auth_client, db):
        c, _ = auth_client
        c.post(
            "/customers/new",
            data={"name": "Persisted Hospital", "category": "hospital",
                  "phone": "", "email": "", "address": "",
                  "trading_terms": "", "notes": "", "staff_id": ""},
        )
        assert db.query(models.Customer).filter_by(name="Persisted Hospital").first() is not None
