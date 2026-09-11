// Copyright (c) 2026, VV Systems Developer LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on('Journal Entry', {
	setup(frm) {
		frm.set_query('custom_item', () => {
			if (!frm.doc.import_file) {
				return {};
			}
			return {
				query: 'vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher.item_query_for_import_file',
				filters: { import_file: frm.doc.import_file },
			};
		});
	},

	custom_item(frm) {
		if (!frm.doc.custom_item) {
			frm.set_value('custom_chassis_no', '');
			return;
		}
		frappe.db.get_value('Item', frm.doc.custom_item, 'custom_chassis_no').then(r => {
			frm.set_value('custom_chassis_no', (r.message && r.message.custom_chassis_no) || '');
		});
	},
});
