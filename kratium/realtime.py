import frappe

def action_changed(doc):
    frappe.publish_realtime(
        event="action_changed",
        message={
            "name": doc.name,
            "doctype": doc.doctype,
            "data": doc.as_dict(),
            "method": method,
        },
        broadcast=True
    )

def action_deleted(doc):
    frappe.publish_realtime(
        event="action_deleted",
        message={
            "name": doc.name,
            "doctype": doc.doctype,
        },
        broadcast=True
    )