import frappe
from frappe.utils import now

def reminder_scheduler():
    now = now_datetime()

    reminders = frappe.get_all(
        "Reminder Master",
        filters={
            "reminder_type": "Until Completion"
        },
        fields=[
            "name",
            "reminder_for",
            "remind_at",
            "reminder_interval"
        ]
    )

    for r in reminders:
        parent = frappe.get_doc("Action", r.reminder_for)

        # stop polling
        if parent.status == "Completed":
            continue

        interval = parse_interval(r.reminder_interval)
        next_time = r.remind_at + interval

        if now >= next_time:
            new_reminder = frappe.new_doc("Reminder Master")
            new_reminder.name1 = f"{parent.action_name} Reminder {now.timestamp()}"
            new_reminder.description = parent.description
            new_reminder.reminder_for = parent.name
            new_reminder.remind_at = next_time
            new_reminder.reminder_type = "Until Completion"
            new_reminder.reminder_interval = r.reminder_interval
            new_reminder.owner = parent.owner
            new_reminder.save(ignore_permissions=True)

            # IMPORTANT: update last reminder time
            frappe.db.set_value(
                "Reminder Master",
                r.name,
                "remind_at",
                next_time
            )

def dispatch_reminders():
    now_ts = now()

    reminders = frappe.db.sql(
        """
        SELECT name, owner, name1, description
        FROM `tabReminder Master`
        WHERE status = 'Pending'
          AND remind_at <= %s
        LIMIT 200
        """,
        now_ts,
        as_dict=True,
    )

    for r in reminders:
        frappe.db.sql(
            """
            UPDATE `tabReminder Master`
            SET status = 'Fired'
            WHERE name = %s
              AND status = 'Pending'
            """,
            r.name,
        )

        frappe.enqueue(
            method="kratium.api.notify_user",
            queue="long",
            timeout=300,
            user=r.owner,
            title=r.name1,
            body=r.description,
        )

    frappe.db.commit()