# Copyright (c) 2025, Keenan Solomon and contributors
# For license information, please see license.txt

# import frappe
from frappe.utils.nestedset import NestedSet
from frappe.utils import date_diff

class Action(NestedSet):
	def before_save(self):
		self.estimated_hours = date_diff(self.end_date, self.start_date) * 24
