import frappe

def action_changed(doc, method):
    frappe.publish_realtime(
        event="action_changed",
        message={
            "name": doc.name,
            "doctype": doc.doctype,
            "data": doc.as_dict(),
            "method": method,
        },
    )

def action_deleted(doc, method):
    frappe.publish_realtime(
        event="action_deleted",
        message={
            "name": doc.name,
            "doctype": doc.doctype,
            "method": method,
        },
    )