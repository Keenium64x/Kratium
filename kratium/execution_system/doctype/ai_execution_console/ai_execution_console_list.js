frappe.listview_settings["AI Execution Console"] = {
	add_fields: ["request_title", "status"],
	hide_name_column: true,
	get_indicator(doc) {
		const colors = {
			Draft: "gray",
			Queued: "orange",
			Processing: "blue",
			"Waiting for User": "yellow",
			"Waiting for Approval": "orange",
			"Ready to Execute": "purple",
			Executed: "green",
			Paused: "gray",
			Blocked: "red",
			Failed: "red",
		};
		const label = ["Queued", "Processing"].includes(doc.status)
			? `${doc.status} ⏳`
			: doc.status || "Draft";
		return [label, colors[doc.status] || "gray", `status,=,${doc.status || "Draft"}`];
	},
	formatters: {
		request_title(value, df, doc) {
			const title = frappe.utils.escape_html(value || doc.name);
			if (["Queued", "Processing"].includes(doc.status)) {
				return `<span class="indicator-pill blue">Working</span> ${title}`;
			}
			return title;
		},
	},
};
