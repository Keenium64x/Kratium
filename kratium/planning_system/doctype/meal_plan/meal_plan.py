import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime


class MealPlan(Document):

    def validate(self):
        self.validate_dates()
        self.calculate_period()

    def validate_dates(self):
        if not self.start_date or not self.end_date:
            return

        start = get_datetime(self.start_date)
        end = get_datetime(self.end_date)

        if end < start:
            frappe.throw("End Date cannot be before Start Date")

    def calculate_period(self):
        if not self.start_date or not self.end_date:
            self.period = 0
            return

        start = get_datetime(self.start_date)
        end = get_datetime(self.end_date)

        delta = end - start
        self.period = delta.total_seconds() 
