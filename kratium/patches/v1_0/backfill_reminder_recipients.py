import frappe


def execute():
	frappe.db.sql(
		"""
		UPDATE `tabReminder Master`
		SET recipient = owner
		WHERE COALESCE(recipient, '') = ''
		"""
	)
