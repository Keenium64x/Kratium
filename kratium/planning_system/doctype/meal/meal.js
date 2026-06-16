frappe.ui.form.on("Grocery Item", {
    grocery(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.grocery) return;

        frappe.db.get_value("Grocery", row.grocery, "base_uom")
            .then(r => {
                if (r.message) {
                    row.uom = r.message.base_uom;
                    frm.refresh_field("table_groceries");
                }
            });
    }
});
