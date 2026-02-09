import frappe
from frappe.model.document import Document
import re

class ReminderMaster(Document):
    def autoname(self):
        user = frappe.session.user
        local = user.split("@", 1)[0]
        safe_local = re.sub(r'[^A-Za-z0-9_-]', '', local)

        self.owner = user
        prefix = f"{safe_local}-ACT-"

        last = frappe.db.sql(
            """
            SELECT name
            FROM `tabReminder Master`
            WHERE name LIKE %s
            ORDER BY name DESC
            LIMIT 1
            """,
            (prefix + "%",),
            as_dict=True,
        )

        if not last:
            idx = 0   
        else:
            idx = int(last[0]["name"].split(prefix)[1]) + 1

        self.name = f"{prefix}{idx:06d}"
    
    def before_insert(self):
        self.status = "Pending"