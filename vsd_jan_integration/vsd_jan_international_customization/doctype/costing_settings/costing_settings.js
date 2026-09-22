// Copyright (c) 2026, VV Systems Developer LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on('Costing Settings', {
	refresh(frm) {
		frm.set_intro(
			__(
				'Controls whether Import File Cost Voucher submit creates Landed Cost Vouchers or applies stock valuation and GL directly.'
			)
		);
	},
});
