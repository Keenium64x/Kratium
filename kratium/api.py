import frappe
from datetime import datetime






@frappe.whitelist()
def get_final_action_list(view_mode, calendar):
    actions = frappe.db.sql("""
    SELECT
        name,
        parent_action,
        estimated_hours,
        start_date,
        end_date,
        event,
        full_day,
        color
    FROM
        `tabAction`
    """, as_dict=True)
        
    view_mode = (view_mode or "").strip('"')

    if view_mode == "Year":
        hour_condition = 720
    elif view_mode == "Month":
        hour_condition = 24
    elif view_mode == "Day":
        hour_condition = 1
    else:
        frappe.throw("Invalid view_mode")

    parent_node = {}
    parent_node_lft = int
    parent_node_rgt = int
    parent_node_name = ""



    # Find the first root node
    for d in actions:
        if d["parent_action"] is None:
            parent_node = d
            parent_node_name = d["name"]
            break  # stop at the first one found



    final_action = set()  # use set to guarantee uniqueness


    def get_siblings(node):
        if node["parent_action"] is None:
            return [node]
        return [a for a in actions if a["parent_action"] == node["parent_action"]]


    def get_children(node):
        return [a for a in actions if a["parent_action"] == node["name"]]


    def complete_node_condition(node):
        siblings = get_siblings(node)

        # FAIL CASE → stop here, add parent, do NOT recurse
        if any(int(a["estimated_hours"]) < hour_condition for a in siblings):
            parent_name = node["parent_action"]
            for a in actions:
                if a["name"] == parent_name:
                    final_action.add(a["name"])
            return  # <-- THIS was missing conceptually

        #Endcase if final node and valid
        leaf_siblings = [s for s in siblings if not get_children(s)]

        for sibling in leaf_siblings:
            if int(sibling["estimated_hours"]) > hour_condition:
                final_action.add(sibling["name"])


        for sibling in siblings:
            for child in get_children(sibling):
                complete_node_condition(child)


    complete_node_condition(parent_node)

    
    final_object = []
    if calendar == False:
        for action in actions:
            if action["name"] in final_action:
                final_object.append(
                    {
                        "id": action["name"],
                        "start": action["start_date"],
                        "end": action["end_date"],
                    }
                )
    else:
        formatted_actions = []
        for a in actions:
            start = a["start_date"]
            end = a["end_date"]

            item = dict(a)  # copy original
            item["fromDate"] = start.strftime("%Y-%m-%d")
            item["toDate"] = end.strftime("%Y-%m-%d")
            item["fromTime"] = start.strftime("%H:%M")
            item["toTime"] = end.strftime("%H:%M")

            formatted_actions.append(item)


        for action in formatted_actions:
            if action["event"] == True:
                final_object.append(
                    {
                        "title": action["name"],
                        "id: ": action["name"],
                        "fromDate": action["fromDate"],
                        "toDate": action["toDate"],
                        "fromTime": action["fromTime"],
                        "toTime": action["toTime"],
                        "color": action["color"],
                        "isFullDay": action["full_day"]

                    }
                )        

    return final_object




