import frappe
from frappe.model.document import Document

class UOMConversion(Document):

    def validate(self):
        self._validate_not_same()
        self._validate_category()
        self._validate_unique()
        self._validate_factor()

    def _validate_not_same(self):
        if self.from_uom == self.to_uom:
            frappe.throw("from_uom and to_uom must be different")

    def _validate_category(self):
        from_cat = frappe.get_value("Unit of Measure", self.from_uom, "category")
        to_cat   = frappe.get_value("Unit of Measure", self.to_uom, "category")

        if from_cat != to_cat:
            frappe.throw("UOM categories must match")

    def _validate_unique(self):
        if frappe.db.exists(
            "UOM Conversion",
            {
                "from_uom": self.from_uom,
                "to_uom": self.to_uom,
                "name": ["!=", self.name],
            }
        ):
            frappe.throw("This UOM conversion already exists")

    def _validate_factor(self):
        if self.factor <= 0:
            frappe.throw("Conversion factor must be > 0")