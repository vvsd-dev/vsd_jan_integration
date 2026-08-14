// Copyright (c) 2026, VV Systems Developer LTD and contributors
// For license information, please see license.txt

function format_seconds(secs) {
	if (isNaN(secs) || secs === null || secs === undefined || secs < 0) return '0s';
	secs = Math.round(secs);
	if (secs < 60) return secs + 's';
	var mins = Math.floor(secs / 60);
	var rem = secs % 60;
	return mins + 'm ' + (rem < 10 ? '0' : '') + rem + 's';
}

frappe.ui.form.on('Item Excel Importer', {
	refresh: function(frm) {
		frm.trigger('setup_realtime_listener');
		frm.trigger('render_progress_html');

		if (!frm.is_new() && frm.doc.excel_file) {
			if (frm.doc.import_status !== 'Queued' && frm.doc.import_status !== 'In Progress') {
				frm.add_custom_button(__('Start Import'), function() {
					frappe.confirm(
						__('Are you sure you want to process and import items from this Excel file in the background?'),
						function() {
							// Immediately update UI to Queued state so user sees instant progress bar without reloading
							frm.doc.import_status = 'Queued';
							frm.doc.processed_invoices = 0;
							frm.doc.processed_cars = 0;
							frm.active_step_text = __('Import job queued in background, starting...');
							frm.progress_percent = 0;
							frm._import_elapsed_secs = 0;
							frm._import_start_epoch = Date.now();
							frm.trigger('setup_realtime_listener');
							frm.trigger('render_progress_html');
							frm.trigger('start_live_timer');

							frappe.call({
								method: 'vsd_jan_integration.vsd_jan_international_customization.doctype.item_excel_importer.item_excel_importer.enqueue_import',
								args: {
									docname: frm.doc.name,
									retry_failed_only: false
								},
								freeze: false,
								callback: function(r) {
									if (!r.exc && r.message) {
										frappe.show_alert({
											message: __('Import job queued successfully.'),
											indicator: 'blue'
										});
									}
								}
							});
						}
					);
				}).addClass('btn-primary');
			}

			var has_failed = frm.doc.failed_records && frm.doc.failed_records !== '[]' && frm.doc.failed_records !== '{}';
			if (has_failed) {
				frm.add_custom_button(__('Export Errored Rows'), function() {
					var url = frappe.urllib.get_full_url(
						'/api/method/vsd_jan_integration.vsd_jan_international_customization.doctype.item_excel_importer.item_excel_importer.download_errored_rows?docname=' + encodeURIComponent(frm.doc.name)
					);
					window.open(url);
				}).addClass('btn-secondary');
			}

			if (has_failed && (frm.doc.import_status === 'Completed with Errors' || frm.doc.import_status === 'Failed')) {
				frm.add_custom_button(__('Retry Failed'), function() {
					frappe.confirm(
						__('Are you sure you want to retry importing only the failed records?'),
						function() {
							// Immediately update UI to Queued state
							frm.doc.import_status = 'Queued';
							frm.active_step_text = __('Retry job queued in background, starting...');
							frm.progress_percent = 0;
							frm._import_elapsed_secs = 0;
							frm._import_start_epoch = Date.now();
							frm.trigger('setup_realtime_listener');
							frm.trigger('render_progress_html');
							frm.trigger('start_live_timer');

							frappe.call({
								method: 'vsd_jan_integration.vsd_jan_international_customization.doctype.item_excel_importer.item_excel_importer.enqueue_import',
								args: {
									docname: frm.doc.name,
									retry_failed_only: true
								},
								freeze: false,
								callback: function(r) {
									if (!r.exc && r.message) {
										frappe.show_alert({
											message: __('Retry job queued successfully.'),
											indicator: 'blue'
										});
									}
								}
							});
						}
					);
				}).addClass('btn-danger');
			}
		}
	},

	setup_realtime_listener: function(frm) {
		if (!frm.doc.name || frm.is_new()) return;

		var event_name = 'item_excel_import_progress_' + frm.doc.name;
		frappe.realtime.off(event_name);
		frappe.realtime.on(event_name, function(data) {
			if (data) {
				if (data.status) {
					frm.doc.import_status = data.status;
				}
				frm.doc.processed_invoices = data.processed_invoices || 0;
				frm.doc.total_invoices = data.total_invoices || 0;
				frm.doc.processed_cars = data.processed_cars || 0;
				frm.doc.total_cars = data.total_cars || 0;
				if (data.estimated_time_str) {
					frm.doc.estimated_time = data.estimated_time_str;
					frm._estimated_time_str = data.estimated_time_str;
				} else if (data.estimated_time) {
					frm.doc.estimated_time = data.estimated_time;
				}
				if (data.remaining_time_str) {
					frm._remaining_time_str = data.remaining_time_str;
				}
				if (data.elapsed_secs !== undefined && data.elapsed_secs !== null) {
					frm._import_elapsed_secs = data.elapsed_secs;
					frm._import_start_epoch = Date.now() - (data.elapsed_secs * 1000);
				}
				frm.active_step_text = data.active_step_text || '';
				frm.progress_percent = data.percent !== undefined ? data.percent : (frm.progress_percent || 0);
				frm.trigger('render_progress_html');

				if (data.status && data.status !== 'In Progress' && data.status !== 'Queued') {
					if (frm._timer_interval) {
						clearInterval(frm._timer_interval);
						frm._timer_interval = null;
					}
					frm.doc.import_status = data.status;
					frm.reload_doc();
				}
			}
		});

		if (frm.doc.import_status === 'In Progress' || frm.doc.import_status === 'Queued') {
			frm.trigger('start_live_timer');
		}
	},

	start_live_timer: function(frm) {
		if (frm._timer_interval) {
			clearInterval(frm._timer_interval);
			frm._timer_interval = null;
		}
		var is_active = (frm.doc.import_status === 'In Progress' || frm.doc.import_status === 'Queued');
		if (!is_active) return;

		if (!frm._import_start_epoch) {
			var init_elapsed = frm._import_elapsed_secs || 0;
			frm._import_start_epoch = Date.now() - (init_elapsed * 1000);
		}

		frm._timer_interval = setInterval(function() {
			if (frm.doc.import_status !== 'In Progress' && frm.doc.import_status !== 'Queued') {
				clearInterval(frm._timer_interval);
				frm._timer_interval = null;
				return;
			}
			var current_elapsed = Math.max(0, Math.floor((Date.now() - frm._import_start_epoch) / 1000));
			frm._import_elapsed_secs = current_elapsed;
			var elapsed_el = document.getElementById('progress_live_elapsed');
			if (elapsed_el) {
				elapsed_el.innerText = format_seconds(current_elapsed);
			}
		}, 1000);
	},

	render_progress_html: function(frm) {
		if (!frm.fields_dict.progress_html) return;
		var status = frm.doc.import_status;
		if (!status || status === 'Pending') {
			if (frm._timer_interval) {
				clearInterval(frm._timer_interval);
				frm._timer_interval = null;
			}
			frm.fields_dict.progress_html.set_value('');
			return;
		}

		var percent = frm.progress_percent;
		if (percent === undefined || percent === null || isNaN(percent)) {
			if (status === 'Completed' || status === 'Completed with Errors') {
				percent = 100;
			} else {
				var tot = (frm.doc.total_invoices || 0) + (frm.doc.total_cars || 0);
				var proc = (frm.doc.processed_invoices || 0) + (frm.doc.processed_cars || 0);
				percent = tot > 0 ? Math.min(100, Math.round((proc / tot) * 100)) : 0;
			}
		}
		if (status === 'Completed' || status === 'Completed with Errors') {
			percent = 100;
		}

		var step_text = frm.active_step_text || (status === 'Completed' ? 'Import completed successfully.' : (status === 'Completed with Errors' ? 'Import completed with errors.' : 'Processing import...'));
		var indicator = 'info';
		var bg_class = 'bg-primary';

		if (status === 'Completed') {
			indicator = 'success';
			bg_class = 'bg-success';
		} else if (status === 'Completed with Errors') {
			indicator = 'warning';
			bg_class = 'bg-warning';
		} else if (status === 'Failed') {
			indicator = 'danger';
			bg_class = 'bg-danger';
		}

		var is_active = (status === 'In Progress' || status === 'Queued');
		var spinner_html = is_active ? '<i class="fa fa-circle-o-notch fa-spin" style="margin-right: 6px; color: #2563eb;"></i>' : '';

		var elapsed_str = frm._import_elapsed_secs !== undefined ? format_seconds(frm._import_elapsed_secs) : (frm.doc.estimated_time || '0s');
		var est_str = frm._estimated_time_str || frm.doc.estimated_time || 'Calculating...';
		var rem_str = frm._remaining_time_str || '';

		var timing_details_html = '';
		if (is_active) {
			timing_details_html = `
				<div><i class="fa fa-clock-o" style="margin-right: 4px; color: #3b82f6;"></i><strong>Time Elapsed:</strong> <span id="progress_live_elapsed" style="font-weight: 700; color: #0f172a;">${elapsed_str}</span></div>
				<div><i class="fa fa-hourglass-half" style="margin-right: 4px; color: #8b5cf6;"></i><strong>Est. Total:</strong> <span id="progress_live_est" style="font-weight: 700; color: #2563eb;">${est_str}</span>${rem_str && rem_str !== '0s' ? ` <span style="color: #64748b; font-size: 11px;">(rem: ~${rem_str})</span>` : ''}</div>
			`;
		} else {
			timing_details_html = `
				<div><i class="fa fa-clock-o" style="margin-right: 4px; color: #10b981;"></i><strong>Total Time Elapsed:</strong> <strong style="color: #0f172a;">${frm.doc.estimated_time || elapsed_str}</strong></div>
			`;
		}

		var html = `
			<div class="import-progress-card" style="border: 1px solid #e2e8f0; border-radius: 10px; padding: 18px; margin-bottom: 20px; background-color: #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
				<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
					<strong style="font-size: 14px; color: #1e293b;">Import Status: <span class="indicator-pill ${indicator}">${status}</span></strong>
					<span style="font-weight: 700; font-size: 14px; color: #2563eb;">${percent}%</span>
				</div>
				<div class="progress" style="height: 14px; border-radius: 7px; background-color: #f1f5f9; overflow: hidden; margin-bottom: 12px;">
					<div class="progress-bar ${bg_class} ${is_active ? 'progress-bar-striped progress-bar-animated' : ''}" role="progressbar" style="width: ${percent}%;"></div>
				</div>
				<div style="font-size: 13px; color: #334155; margin-bottom: 12px; font-weight: 500; display: flex; align-items: center;">
					${spinner_html}
					<span>${step_text}</span>
				</div>
				<div style="display: flex; flex-wrap: wrap; gap: 20px; font-size: 12px; color: #64748b; border-top: 1px solid #f1f5f9; padding-top: 10px;">
					<div><i class="fa fa-file-text-o" style="margin-right: 4px;"></i><strong>Invoices:</strong> ${frm.doc.processed_invoices || 0} / ${frm.doc.total_invoices || 0}</div>
					<div><i class="fa fa-car" style="margin-right: 4px;"></i><strong>Cars:</strong> ${frm.doc.processed_cars || 0} / ${frm.doc.total_cars || 0}</div>
					${timing_details_html}
				</div>
			</div>
		`;

		frm.fields_dict.progress_html.set_value(html);
		if (is_active) {
			frm.trigger('start_live_timer');
		}
	}
});
