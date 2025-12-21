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

class Action(NestedSet):
    def before_save(self):
        hours = hour_diff(self.start_date, self.end_date)
        self.estimated_hours = hours
        if hours > 24:
            self.full_day = True
        else:
            self.full_day = False