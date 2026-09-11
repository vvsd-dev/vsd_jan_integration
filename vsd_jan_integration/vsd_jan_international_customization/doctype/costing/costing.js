// Copyright (c) 2026, VV Systems Developer LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("Costing", {
	setup(frm) {
		frm.set_query("account", () => ({
			filters: { is_group: 0 },
		}));
		frm.set_query("payable_account", () => ({
			filters: {
				is_group: 0,
				account_type: ["in", ["Payable", ""]],
			},
		}));
	},
});
