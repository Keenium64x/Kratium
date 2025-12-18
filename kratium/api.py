import frappe







@frappe.whitelist(allow_guest=True)
def get_final_action_list():
    actions = frappe.db.sql("""
    SELECT
        name,
        parent_action,
        estimated_hours
    FROM
        `tabAction`
    """, as_dict=True)
        
    hours_in_month = 720
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
        if any(int(a["estimated_hours"]) < hours_in_month for a in siblings):
            parent_name = node["parent_action"]
            for a in actions:
                if a["name"] == parent_name:
                    final_action.add(a["name"])
            return  # <-- THIS was missing conceptually

        #Endcase if final node and valid
        leaf_siblings = [s for s in siblings if not get_children(s)]

        for sibling in leaf_siblings:
            if int(sibling["estimated_hours"]) > hours_in_month:
                final_action.add(sibling["name"])


        for sibling in siblings:
            for child in get_children(sibling):
                complete_node_condition(child)


    complete_node_condition(parent_node)

    # materialize result
    return {
        "count": len(final_action),
        "actions": final_action,
    }