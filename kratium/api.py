import frappe
from frappe.utils import now_datetime
from kratium.auth_guard import jwt_required
from kratium.firebase.fcm import get_firebase_service_account_path
from kratium.notifications import Notification, enqueue_notification, send_notification as deliver_notification
from kratium.reminders import (
	cancel_reminder as cancel_scheduled_reminder,
	reschedule_reminder as reschedule_scheduled_reminder,
	schedule_reminder,
)


@frappe.whitelist(allow_guest=True)
def mobile_token_exists(token_hash: str):
    if not token_hash:
        return {"ok": False}

    row = frappe.db.get_value(
        "Mobile Auth Token",
        {"token_hash": token_hash},
        ["name", "expires_at"],
        as_dict=True,
    )

    if not row:
        return {"ok": False}


    if row.expires_at and row.expires_at <= now_datetime():
        return {"ok": False}

    return {"ok": True}

@frappe.whitelist(allow_guest=True)
def revoke_mobile_token(token_hash: str):
    if not token_hash:
        return {"ok": False}
    frappe.db.delete("Mobile Auth Token", {"token_hash": token_hash})
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist(allow_guest=True)
@jwt_required
def register_device(token, platform, refreshed=False):
    user = getattr(frappe.local, "jwt_user", None)
    if not user or user == "Guest":
        frappe.throw("Not authenticated")
    if not token or not str(token).strip():
        frappe.throw("Device token is required")

    platform_map = {
        "android": "android",
        "ios": "ios",
        "web": "web",
        "windows": "windows",
        "linux": "linux",
        "webapp": "webapp",
        "macos": "macos",
    }

    device_type = platform_map.get(str(platform or "").lower())
    if not device_type:
        frappe.throw("Unsupported platform")
    existing = frappe.db.get_value(
        "FCM Device",
        {"token": token},
        ["name", "enabled"],
        as_dict=True,
    )

    if existing:
        frappe.db.set_value(
            "FCM Device",
            existing.name,
            {
                "user": user,
                "device_type": device_type,
                "enabled": 1,
                "last_seen": now_datetime(),
            },
        )
        return {
            "device": existing.name,
            "registered": True,
            "created": False,
        }

    doc = frappe.get_doc({
        "doctype": "FCM Device",
        "user": user,
        "token": token,
        "device_type": device_type,
        "enabled": 1,
        "last_seen": now_datetime(),
    })
    doc.insert(ignore_permissions=True)
    return {
        "device": doc.name,
        "registered": True,
        "created": True,
    }


@frappe.whitelist(allow_guest=True)
@jwt_required
def mobile_sync_status():
    user = getattr(frappe.local, "jwt_user", None) or frappe.session.user
    if not user or user == "Guest":
        frappe.throw("Not authenticated", frappe.PermissionError)

    devices = frappe.get_all(
        "FCM Device",
        filters={"user": user},
        fields=["name", "device_type", "enabled", "last_seen"],
        order_by="modified desc",
    )

    return {
        "ok": True,
        "user": user,
        "devices": devices,
        "firebase_configured": bool(get_firebase_service_account_path()),
        "server_time": now_datetime(),
    }


@frappe.whitelist(allow_guest=True)
@jwt_required
def send_test_notification(title="Kratium Sync Test", body="Mobile notifications are connected"):
    user = _resolve_notification_user()
    result = deliver_notification(
        Notification(
            user=user,
            title=title,
            body=body,
            data={"source": "mobile_sync_test"},
            route="/kratium/home",
            event_type="sync_test",
        ),
        raise_on_total_failure=False,
    )
    return {"sent": result.get("success", 0) > 0, "user": user, "result": result}


@frappe.whitelist(allow_guest=True)
@jwt_required
def unregister_device(token):
	user = getattr(frappe.local, "jwt_user", None)
	name = frappe.db.get_value("FCM Device", {"token": token, "user": user}, "name")
	if not name:
		return {"unregistered": False}
	frappe.db.set_value("FCM Device", name, "enabled", 0)
	return {"unregistered": True, "device": name}



@frappe.whitelist()
def notify_user(user, title, body, data=None, route=None, event_type="notification"):
	"""Send immediately. Kept at the old dotted path for queued-job compatibility."""
	return deliver_notification(
		Notification(
			user=user,
			title=title,
			body=body,
			data=data or {},
			route=route,
			event_type=event_type,
		)
	)

@frappe.whitelist(allow_guest=True)
@jwt_required
def send_notification(user=None, title=None, body=None, data=None, route=None, event_type="notification"):
	user = _resolve_notification_user(user)
	enqueue_notification(
		user=user,
		title=title,
		body=body,
		data=data,
		route=route,
		event_type=event_type,
	)
	return {"queued": True, "user": user}

@frappe.whitelist(allow_guest=True)
@jwt_required
def schedule_notification(
	user=None,
	title=None,
	body=None,
	run_at=None,
	data=None,
	route=None,
	reminder_type="Once",
	repeat_every=None,
	event_type="reminder",
	action=None,
):
	user = _resolve_notification_user(user)
	name = schedule_reminder(
		user,
		title,
		body,
		run_at,
		data=data,
		route=route,
		reminder_type=reminder_type,
		repeat_every=repeat_every,
		event_type=event_type,
		action=action,
	)
	return {"scheduled": True, "reminder": name, "run_at": run_at}


@frappe.whitelist(allow_guest=True)
@jwt_required
def reschedule_notification(reminder, run_at):
	_assert_reminder_access(reminder)
	return {
		"scheduled": True,
		"reminder": reschedule_scheduled_reminder(reminder, run_at),
		"run_at": run_at,
	}


@frappe.whitelist(allow_guest=True)
@jwt_required
def cancel_notification(reminder):
	_assert_reminder_access(reminder)
	return {
		"cancelled": True,
		"reminder": cancel_scheduled_reminder(reminder),
	}


def _resolve_notification_user(requested_user=None):
	current_user = getattr(frappe.local, "jwt_user", None) or frappe.session.user
	if not current_user or current_user == "Guest":
		frappe.throw("Not authenticated", frappe.PermissionError)

	requested_user = requested_user or current_user
	if requested_user != current_user and "System Manager" not in frappe.get_roles(current_user):
		frappe.throw("You can only send notifications to yourself", frappe.PermissionError)
	return requested_user


def _assert_reminder_access(reminder_name):
	current_user = _resolve_notification_user()
	recipient = frappe.db.get_value("Reminder Master", reminder_name, "recipient")
	owner = frappe.db.get_value("Reminder Master", reminder_name, "owner")
	if current_user not in {recipient, owner} and "System Manager" not in frappe.get_roles(current_user):
		frappe.throw("Not permitted to change this reminder", frappe.PermissionError)


def has_app_permission():
    return True




#Action Filter
@frappe.whitelist(allow_guest=True)
@jwt_required
def get_final_action_list(view_mode, calendar):
    owner = getattr(frappe.local, "jwt_user", None) or frappe.session.user

    calendar = str(calendar).lower()

    view_mode = (view_mode or "").strip('"')
    if view_mode == "Year":
        hour_condition = 720
    elif view_mode == "Month":
        hour_condition = 24
    elif view_mode == "Day":
        hour_condition = 1
    else:
        frappe.throw("Invalid view_mode")

    top_actions = frappe.qb.get_query(
            "Action",
            fields=["name", "estimated_hours", "parent_action"],
            filters={"parent_action": None, "owner": owner}
        ).run(as_dict=True)




    final_actions = []
    #Fetching Functions
    def get_children(node):
        return frappe.qb.get_query(
            "Action",
            fields=["name", "estimated_hours", "parent_action"],
            filters={"parent_action": node["name"], "milestone": 0, "owner": owner}
        ).run(as_dict=True)
  
    def get_parent(node):
        return frappe.qb.get_query(
            "Action",
            fields=["name", "estimated_hours", "parent_action"],
            filters={"name": node["parent_action"], "milestone": 0, "owner": owner}
        ).run(as_dict=True)

    def get_siblings(node):
        return frappe.qb.get_query(
            "Action",
            fields=["name", "estimated_hours", "parent_action"],
            filters={
                "parent_action": node["parent_action"], 'milestone': 0, "owner": owner
            }
        ).run(as_dict=True)

    #Validation Function
    def is_leaf(node):
        return get_children(node) == [] 

    def validify_action_level(nodes):
        fail_con = False
        for node in nodes:
            if float(node["estimated_hours"]) < hour_condition:
                fail_con = True
        if fail_con is True:
            parent_fail = get_parent(nodes[0])
            if parent_fail[0] not in final_actions:
                final_actions.append(parent_fail[0])
            return False
        else:
            for action in nodes:
                if is_leaf(action) and float(action["estimated_hours"]) > hour_condition and action not in final_actions:
                    final_actions.append(action)
            return True
        

    #node process
    def tree_walk(node):
        if isinstance(node, list):
            for top_node in node:
                if top_node["parent_action"] is None:
                    children = get_children(top_node)
                    for child in children:
                        tree_walk(child)
        else:
            siblings = get_siblings(node)
            if validify_action_level(siblings):
                for action in siblings:
                    for child in get_children(action):
                        tree_walk(child)

    tree_walk(top_actions)

    final_action_name = [action["name"] for action in final_actions]
    condition_actions = frappe.qb.get_query(
        "Action",
        fields=["name", "action_name", "start_date", "end_date", "estimated_hours", "color", "parent_action", "full_day","event"],
        filters={"name": ["in", final_action_name], "milestone": 0, "owner": owner, }
        ).run(as_dict=True) 
# "type": ["not in", ["BaseAction"]]
    condition_event_actions = frappe.qb.get_query(
        "Action",
        fields=["name", "action_name", "start_date", "end_date", "estimated_hours", "color", "parent_action", "full_day","event"],
        filters={"name": ["in", final_action_name], "milestone": 0, "owner": owner, "full_day": 0}
        ).run(as_dict=True)     

    event_actions = frappe.qb.get_query(
        "Action",
        fields=["name", "action_name", "start_date", "end_date", "estimated_hours", "color", "parent_action", "full_day","event"],
        filters={"event": 1, "milestone": 0, "owner": owner, "full_day": 0}
        ).run(as_dict=True) 


    final_object = []
    if calendar == 'false':
        for action in condition_actions:
            final_object.append(
                {
                    "id": action["name"],
                    "name": action["action_name"],
                    "start": action["start_date"],
                    "end": action["end_date"],
                }
            )
    else:
        if view_mode == "Day":
            formatted_condition_event_actions = []
            for a in condition_event_actions:
                start = a["start_date"]
                end = a["end_date"]

                item = dict(a) 
                item["fromDate"] = start.strftime("%Y-%m-%d")
                item["toDate"] = end.strftime("%Y-%m-%d")
                item["fromTime"] = start.strftime("%H:%M")
                item["toTime"] = end.strftime("%H:%M")

                formatted_condition_event_actions.append(item)            
            for action in formatted_condition_event_actions:
                final_object.append(
                    {
                        "title": action["action_name"],
                        "id": action["name"],
                        "fromDate": action["fromDate"],
                        "toDate": action["toDate"],
                        "fromTime": action["fromTime"],
                        "toTime": action["toTime"],
                        "color": action["color"],
                        "isFullDay": action["full_day"]

                    }
                )        
        else:
            formatted_event_actions = []
            for a in event_actions:
                start = a["start_date"]
                end = a["end_date"]

                item = dict(a) 
                item["fromDate"] = start.strftime("%Y-%m-%d")
                item["toDate"] = end.strftime("%Y-%m-%d")
                item["fromTime"] = start.strftime("%H:%M")
                item["toTime"] = end.strftime("%H:%M")

                formatted_event_actions.append(item)

            for action in formatted_event_actions:
                if action["event"] == True:
                    final_object.append(
                        {
                            "title": action["action_name"],
                            "id": action["name"],
                            "fromDate": action["fromDate"],
                            "toDate": action["toDate"],
                            "fromTime": action["fromTime"],
                            "toTime": action["toTime"],
                            "color": action["color"],
                            "isFullDay": action["full_day"]

                        }
                    )        

    return final_object












#Grocery Stock Calculations
#Conver UOM
@frappe.whitelist(allow_guest=True)
@jwt_required
def convert_qty(qty, from_uom, to_uom):
    if from_uom == to_uom:
        return qty

    factor = frappe.get_value(
        "UOM Conversion",
        {
            "from_uom": from_uom,
            "to_uom": to_uom
        },
        "factor"
    )

    if not factor:
        frappe.throw(
            f"No UOM conversion from {from_uom} to {to_uom}"
        )

    return qty * factor


#Grocery bin(cache) Rebuild
def rebuild_grocery_bins():
    frappe.db.sql("DELETE FROM `tabGrocery Bin`")

    rows = frappe.db.sql("""
        SELECT
            grocery,
            location,
            SUM(actual_qty) AS qty
        FROM `tabGrocery Stock Ledger Entry`
        WHERE is_cancelled = 0
        GROUP BY grocery, location
        HAVING qty != 0
    """, as_dict=True)

    for r in rows:
        frappe.get_doc({
            "doctype": "Grocery Bin",
            "grocery": r.grocery,
            "location": r.location,
            "actual_qty": r.qty
        }).insert(ignore_permissions=True)
