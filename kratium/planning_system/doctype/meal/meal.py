import frappe
import re
from frappe.model.document import Document

class Meal(Document):

    def validate(self):
        self.validate_grocery_items()

    def validate_grocery_items(self):
        for row in self.table_groceries:
            self._validate_and_format_quantity(row)

    def _validate_and_format_quantity(self, row):
        if not row.base_uom:
            frappe.throw("Base UOM is required in grocery row")

        if not row.quantity:
            frappe.throw("Quantity is required in grocery row")

        match = re.fullmatch(r"\s*(\d+(\.\d+)?)\s*", row.quantity)
        if not match:
            frappe.throw("Quantity must be a number only")

        number = match.group(1)
        row.quantity = f"{number} {row.base_uom}"