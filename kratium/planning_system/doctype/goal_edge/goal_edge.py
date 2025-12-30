import re
import frappe
from frappe.model.document import Document


class GoalEdge(Document):
    def autoname(self):
        user = frappe.session.user
        local = user.split("@", 1)[0]
        safe_local = re.sub(r'[^A-Za-z0-9_-]', '', local)

        self.owner = user
        prefix = f"{safe_local}-GE-"

        last = frappe.db.sql(
            """
            SELECT name
            FROM `tabGoal Edge`
            WHERE name LIKE %s
            ORDER BY name DESC
            LIMIT 1
            """,
            (prefix + "%",),
            as_dict=True,
        )

        idx = int(last[0]["name"].split(prefix)[1]) + 1 if last else 0
        self.name = f"{prefix}{idx:06d}"






