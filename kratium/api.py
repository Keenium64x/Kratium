import frappe


@frappe.whitelist()
def get_final_action_list(view_mode, calendar):
    owner = frappe.session.user
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
            if int(node["estimated_hours"]) < hour_condition:
                fail_con = True
        if fail_con is True:
            parent_fail = get_parent(nodes[0])
            if parent_fail[0] not in final_actions:
                final_actions.append(parent_fail[0])
            return False
        else:
            for action in nodes:
                if is_leaf(action) and int(action["estimated_hours"]) > hour_condition and action not in final_actions:
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
        filters={"name": ["in", final_action_name], "milestone": 0, "owner": owner}
        ).run(as_dict=True) 


    event_actions = frappe.qb.get_query(
        "Action",
        fields=["name", "action_name", "start_date", "end_date", "estimated_hours", "color", "parent_action", "full_day","event"],
        filters={"event": 1, "milestone": 0, "owner": owner}
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
            formatted_condition_actions = []
            for a in condition_actions:
                start = a["start_date"]
                end = a["end_date"]

                item = dict(a) 
                item["fromDate"] = start.strftime("%Y-%m-%d")
                item["toDate"] = end.strftime("%Y-%m-%d")
                item["fromTime"] = start.strftime("%H:%M")
                item["toTime"] = end.strftime("%H:%M")

                formatted_condition_actions.append(item)            
            for action in formatted_condition_actions:
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




