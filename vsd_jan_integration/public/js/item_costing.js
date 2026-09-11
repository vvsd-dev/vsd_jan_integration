// Copyright (c) 2026, VV Systems Developer LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on('Item', {
	refresh(frm) {
		if (frm.is_new() || frm.doc.disabled) {
			return;
		}

		frm.add_custom_button(__('Car Costing'), () => open_car_costing(frm), __('Costing'));
	},

	custom_costing_tab(frm) {
		// tab refresh hook
	},
});

function open_car_costing(frm) {
	frappe.call({
		method: 'vsd_jan_integration.vsd_jan_international_customization.doctype.car_costing.car_costing.get_or_create_for_item',
		args: { item: frm.doc.name },
		freeze: true,
		freeze_message: __('Opening Car Costing...'),
		callback(r) {
			if (r.message) {
				frappe.set_route('Form', 'Car Costing', r.message);
			}
		},
	});
}
