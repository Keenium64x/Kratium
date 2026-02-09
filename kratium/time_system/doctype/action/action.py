import re
import frappe
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils.nestedset import NestedSet
from datetime import datetime
import frappe



DT_FMT  = "%Y-%m-%d %H:%M:%S"
DT_FMT2 = "%Y-%m-%d %H:%M"
D_FMT   = "%Y-%m-%d"

def to_datetime(x):
    if isinstance(x, datetime):
        return x
    if isinstance(x, str):
        for fmt in (DT_FMT, DT_FMT2, D_FMT):
            try:
                return datetime.strptime(x, fmt)
            except ValueError:
                pass
    raise TypeError(f"Unsupported type: {type(x)}")

def hour_diff(dt1, dt2) -> float:
    t1 = to_datetime(dt1)
    t2 = to_datetime(dt2)
    return round((t2 - t1).total_seconds() / 3600, 0)

def parse_interval(interval_str):
    pattern = r'(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?'
    h, m, s = re.match(pattern, interval_str).groups()
    return timedelta(
        hours=int(h or 0),
        minutes=int(m or 0),
        seconds=int(s or 0),
    )

class Action(NestedSet):
    def autoname(self):
        user = frappe.session.user
        local = user.split("@", 1)[0]
        safe_local = re.sub(r'[^A-Za-z0-9_-]', '', local)

        self.owner = user
        prefix = f"{safe_local}-ACT-"

        last = frappe.db.sql(
            """
            SELECT name
            FROM `tabAction`
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

    def validate(self):  
        self.group_time()   
        self.validate_goals()    
        self.sync_milestone_dates()
        self.compute_duration()
        self.check_leaf()
        self.validate_lifectye()


    def after_insert(self):
        self.sync_reminder()        

    def validate_goals(self):
        goal = self.goal or 0
        basegoal = self.basegoal or 0

        if goal > 0 and basegoal > 0:
            frappe.throw(
                "Goal and Base Goal cannot both be positive at the same time."
            )

    def sync_milestone_dates(self):
        if self.milestone and self.milestone_action:
            row = frappe.db.get_value(
                "Action",
                self.milestone_action,
                ["start_date", "end_date"],
                as_dict=True
            )
            if row:
                self.start_date = row.start_date
                self.end_date = row.end_date

    def compute_duration(self):
        if getattr(self, "todo", False) and (self.estimated_hours is None):
            if self.start_date and self.end_date:
                hours = hour_diff(self.start_date, self.end_date)
                self.estimated_hours = hours
                self.full_day = hours > 24
            else:
                self.estimated_hours = 0
                self.full_day = False
        elif not getattr(self, "todo", False):
            if self.start_date and self.end_date:
                hours = hour_diff(self.start_date, self.end_date)
                self.estimated_hours = hours
                self.full_day = hours > 24
            else:
                self.estimated_hours = 0
                self.full_day = False

    def check_leaf(self):
        if self.is_new():
            return

        if self.lft is None or self.rgt is None:
            return

        if self.rgt == self.lft + 1:
            self.leaf = 1


    def group_time(self):
        if not self.is_group:
            return

    def group_time(self):
        if not self.is_group:
            return

        children = frappe.get_all(
            "Action",
            filters={
                "parent_action": self.name,
                "milestone": 0,
                "owner": self.owner,
                "start_date": ["is", "set"],
                "end_date": ["is", "set"],
            },
            fields=["start_date", "end_date"],
        )

        if not children:
            return

        earliest_start = min(c.start_date for c in children if c.start_date)
        latest_end = max(c.end_date for c in children if c.end_date)

        self.start_date = earliest_start.strftime("%Y-%m-%d 00:00:00")
        self.end_date = latest_end.strftime("%Y-%m-%d 00:00:00")

    def validate_lifectye(self):
        if self.status == 'Completed':
            self.completed = true


    def sync_reminder(self):
        if not self.reminder:
            return

        now = now_datetime()

        # only fire when reminder is due
        if self.reminder > now:
            return

        reminder_name = f"{self.name}-{self.reminder}"

        # avoid duplicates for same timestamp
        if frappe.db.exists("Reminder Master", reminder_name):
            return

        reminder = frappe.new_doc("Reminder Master")
        reminder.name1 = reminder_name
        reminder.description = self.description
        reminder.reminder_for = self.name
        reminder.remind_at = self.reminder
        reminder.owner = self.owner
        reminder.save(ignore_permissions=True)

        # handle recurrence
        if self.reminder_type == "Until Completion" and self.status != "Completed":
            interval = self._parse_interval(self.reminder_interval)
            self.reminder = self.reminder + interval
            self.db_set("reminder", self.reminder)

        # Once → nothing else happens

    def _parse_interval(self, interval_str: str) -> timedelta:
        """
        Parses '9h 35m 34s' into timedelta
        """
        h = m = s = 0
        for value, unit in re.findall(r'(\d+)\s*([hms])', interval_str.lower()):
            if unit == "h":
                h = int(value)
            elif unit == "m":
                m = int(value)
            elif unit == "s":
                s = int(value)
        return timedelta(hours=h, minutes=m, seconds=s)
