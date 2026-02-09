# Copyright (c) 2026, Keenan Solomon and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

def post_sle(grocery, location, qty, voucher):
    last_qty = frappe.db.get_value(
        "Grocery Bin",
        {"grocery": grocery, "location": location},
        "actual_qty"
    ) or 0

    new_qty = last_qty + qty

    frappe.get_doc({
        "doctype": "Grocery Stock Ledger Entry",
        "grocery": grocery,
        "location": location,
        "actual_qty": qty,
        "qty_after_transaction": new_qty,
        "posting_datetime": voucher.posting_datetime,
        "voucher_type": voucher.doctype,
        "voucher_no": voucher.name
    }).insert(ignore_permissions=True)

    upsert_bin(grocery, location, new_qty)


#Bin Upsert
def upsert_bin(grocery, location, qty):
    if frappe.db.exists("Grocery Bin", {"grocery": grocery, "location": location}):
        frappe.db.set_value(
            "Grocery Bin",
            {"grocery": grocery, "location": location},
            "actual_qty",
            qty
        )
    else:
        frappe.get_doc({
            "doctype": "Grocery Bin",
            "grocery": grocery,
            "location": location,
            "actual_qty": qty
        }).insert(ignore_permissions=True)



class GroceryStockEntry(Document):
    def on_submit(self):
        for row in self.items:
            if self.entry_type == "Receipt":
                post_sle(
                    grocery=row.grocery,
                    location=row.target_location,
                    qty=row.qty,
                    voucher=self
                )

            elif self.entry_type == "Consumption":
                post_sle(
                    grocery=row.grocery,
                    location=row.source_location,
                    qty=-row.qty,
                    voucher=self
                )

            elif self.entry_type == "Transfer":
                post_sle(row.grocery, row.source_location, -row.qty, self)
                post_sle(row.grocery, row.target_location, row.qty, self)

    def on_cancel(self):
        cancel_ledger_entries(self)
