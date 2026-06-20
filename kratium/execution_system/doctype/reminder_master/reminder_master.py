import frappe
from frappe.model.document import Document
from frappe.model.naming import make_autoname

class ReminderMaster(Document):
    def autoname(self):
        self.name = make_autoname("REM-.YYYY.-.#####")
    
    def before_insert(self):
        self.status = self.status or "Pending"
        self.recipient = self.recipient or self.owner or frappe.session.user

    def validate(self):
        if not self.name1:
            frappe.throw("Reminder title is required")
        if not self.recipient:
            frappe.throw("Reminder recipient is required")
        if not self.remind_at:
            frappe.throw("Reminder time is required")
