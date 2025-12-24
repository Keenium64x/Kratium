// Copyright (c) 2025, Keenan Solomon and contributors
// For license information, please see license.txt

frappe.ui.form.on("Action", {
  setup(frm) {
    frm.set_query("action", () => {
      return {
        filters: {
          owner: frappe.session.user
        }
      };
    });
  }
});
