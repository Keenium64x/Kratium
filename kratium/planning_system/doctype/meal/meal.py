import frappe
from frappe.model.document import Document

class Meal(Document):
    def validate(self):
        self.sync_grocery_uom()

    def sync_grocery_uom(self):
        for row in self.table_groceries:
            if not row.grocery:
                continue

            row.uom = frappe.db.get_value(
                "Grocery",
                row.grocery,
                "base_uom"
            )

            if row.quantity is None:
                frappe.throw("Quantity is required")