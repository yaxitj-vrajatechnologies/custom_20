# -*- coding: utf-8 *-*
import requests
import base64
from odoo import models, fields,api,_


class PrintNodePrinter(models.Model):
    _name = "printnode.printer.vts"
    _description = "PrintNode Printer"

    name = fields.Char(string="Printer Name", required=True, help="Name of printer from PrintNode.")
    printer_id = fields.Char(string="Printer ID", required=True,
                             help="Unique Printer ID from PrintNode API used for sending print jobs.")
    status = fields.Selection([('online', 'Online'), ('offline', 'Offline')], string="Printer Status",
                              help="Current status of printer from PrintNode.")
    printnode_instance_id = fields.Many2one('printnode.connect', string="PrintNode Instance", required=True,
                                            ondelete='cascade', help="PrintNode connection this printer belongs to.")
    computer_id = fields.Many2one('printnode.computer.vts', string="Computer")
    paper_ids = fields.Many2many('printnode.paper.vts', string='Papers')
    description = fields.Char("Description")
    is_printer_active = fields.Boolean(string='Is Printer Active',compute='_compute_printer_state',store=True,readonly=True,help="True only if the printer is online and computer is in connected state")
    is_color_printer = fields.Boolean("Color Printer")

    @api.depends('status', 'computer_id.state')
    def _compute_printer_state(self):
        """ check computer and printer status
        """
        for rec in self:
            rec.is_printer_active = rec.status in ['online'] and rec.computer_id.state in ['connected']

    def _get_source(self):
        printnode_version = self.env['ir.module.module'].sudo().search(
            [['name', '=', 'printnode_odoo_connector']]).latest_version

        split_value = printnode_version and printnode_version.split('.')
        module_version = split_value and '.'.join(split_value[-3:])
        source_name = f'Odoo PrintNode {module_version}'

        return source_name

    def create_atttachment(self, data,content):
        attachment = self.env['ir.attachment'].sudo().create({
            'name': f"{data.get('title')}",
            'type': 'binary',
            'datas': content,
            'mimetype': 'application/pdf',
        })
        return attachment

    def verify_printnode_report(self,report=None):
        """
           This method checks if the report is compatible with PrintNode settings
            and ensures that required printing parameters are valid.
            :param report: Optional dictionary with report details,
        """
        self.ensure_one()

        if not report:
            return None

        if not self.env.company.printnode_auto_print:
           return("PrintNode printing is disabled for '%(company)s'. Please contact your Administrator." % {'company': self.env.company.name})

        if not self.sudo().printnode_instance_id.check_printer_status(self.sudo()):
            return ("Printer is not available, select another printer for a while")

        REQUIRED_REPORT_KEYS = ['title', 'type', 'size']
        missing_key = [key for key in REQUIRED_REPORT_KEYS if not report.get(key)]
        if missing_key:
            return  _('One of the required field is Missing : %s') % ', '.join(missing_key)
        return


    def _source_name(self):
        full_version = self.env['ir.module.module'].sudo().search(
            [['name', '=', 'printnode_odoo_connector']]).latest_version

        split_value = full_version and full_version.split('.')
        module_version = split_value and '.'.join(split_value[-3:])
        source_name = f'Odoo Printnode Printer {module_version}'

        return source_name

    def print_base64_report(self, ascii_data, params, check_printer_format=True,label_paper=None,label_id=None):
        """
        Prepares "qweb-pdf" and "py3o" ("pdf_base64") reports before sending them
        to PrintNode. Used for printing via Actions -> Print or printing attachments.
        """
        self.ensure_one()
        error = self.verify_printnode_report(report=(check_printer_format and params))
        if error:
            log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(printnode_opr_name='printjob_request',
                printnode_opr_type='print_request',instance=self.printnode_instance_id.id if self.printnode_instance_id else False,
                printnode_opr_message=f"PrintNode Label Verification Failed")

            self.env['printnode.log.vts.line'].sudo().generate_printnode_process_line(printnode_opr_name='printjob_request',
                printnode_opr_type='print_request',instance=self.printnode_instance_id.id if self.printnode_instance_id else False,
                printnode_opr_message=f"{error}",process_response_message=str(error), log_id=log_id,
                fault_operation=True)
            return

        data = {
            'printerId': self.printer_id,
            'qty': params.get('copies', 1),
            'title': params.get('title'),
            'source': self._source_name(),
            'contentType':  'pdf_base64' if check_printer_format in ['qweb-pdf', 'py3o'] else 'raw_base64',
            'content': ascii_data,
            "options": {
                "paper": label_paper.name,
            }
        }

        return self.send_printjob_request_to_printnode(data,label_id=label_id)

    def printnode_report_verify(self,report_info, report_setting,paper):
        """
        Verify the given report against the auto-printing rules and PrintNode policies.

        Checks whether the report is marked as "Inactive" and
        calls `printnode_check()`. If any check fails and `raise_exception` is True.
        :param report_id: The report record to verify"""

        report_error = False

        if not report_setting:
            report_error = _('Your are trying to print report. But it was InActive from printing in "Print Rule" menu.').format(report_info.name)

        report = {
            'title': report_setting and report_info.name,
            'type': report_setting and report_setting.report_type,
            'size': report_setting and report_setting.report_paper_id or paper or self.env.company.paper_id,
        }
        if not report_error:
            report_error =  self.verify_printnode_report(report)
        if report_error:
            log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(printnode_opr_name='printjob_request',
            printnode_opr_type='print_request',instance=self.printnode_instance_id.id if self.printnode_instance_id else False,
            printnode_opr_message=f"PrintNode Report Verification Failed - {report_info.name}")

            self.env['printnode.log.vts.line'].sudo().generate_printnode_process_line(printnode_opr_name='printjob_request',
               printnode_opr_type='print_request',instance=self.printnode_instance_id.id if self.printnode_instance_id else False,
                printnode_opr_message=f"{report_error}",
                process_response_message=str(report_error), log_id=log_id,fault_operation=True)
        return report_error


    def printnode_print_document(self, report_info, objects, total_copies,data=None,paper=None):
        self.ensure_one()
        report_setting = None
        if not self.env.context.get('skip_printnode_rule_check'):
            report_setting = self.env['printnode.rule'].search([('report_id', '=', report_info.id), ('active', '=', True)],limit=1)
            report_error = self.printnode_report_verify(report_info, report_setting,paper)
            if report_error:
                return
        ids = objects and objects.mapped('id') or None

        content, content_type = report_info._render(
            report_ref=report_info.xml_id, res_ids=ids, data=data)

        content_type='pdf_base64' if report_info.report_type in ['qweb-pdf', 'py3o'] else 'raw_base64'
        paper_id = report_setting.report_paper_id if report_setting else paper

        payload = {
            "printerId": self.printer_id,
            "title": report_info.name,
            'qty': total_copies,
            "contentType": content_type,
            "content": base64.b64encode(content).decode('ascii'),
            "source": self._get_source(),
            "options": {
                   "paper":paper_id.name if paper_id else self.env.company.paper_id.name
            }
        }
        attachment = self.create_atttachment(payload,content)
        printjob_id = self.env['printnode.printjob.vts'].sudo().create({
            'description':report_info.name,
            'printer_id':self.id,
            'attachment_id':attachment.id
        })
        printjob_request = self.send_printjob_request_to_printnode(payload,printjob_id)

        return printjob_request

    def send_printjob_request_to_printnode(self,payload,printjob_id=None,label_id=None):

        try:
            post_url = f'{self.printnode_instance_id.printnode_api}/printjobs'
            auth = requests.auth.HTTPBasicAuth(self.printnode_instance_id.printnode_api_key, '')
            # printjob_request=print(hello)
            printjob_request = requests.post(post_url, auth=auth, json=payload, timeout=30)

            if printjob_request.status_code == 201:
                response_id = printjob_request.json()

                if printjob_id:
                    printjob = self.env['printnode.printjob.vts'].sudo().browse(printjob_id.id)
                    printjob.write({'printjob_id': str(response_id),'printnode_instance_id':self.printnode_instance_id.id,'print_status':'done'})

                if label_id:
                    shipping_label_id = self.env['shipping.label.vts'].sudo().browse(label_id.id)
                    shipping_label_id.write({
                        'printjob_id': str(response_id),
                        'printnode_instance_id':self.printnode_instance_id.id})

                log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(printnode_opr_name='printjob_request',
                    printnode_opr_type='print_request', instance=self.printnode_instance_id.id,
                    printnode_opr_message=f"Print Job Request For {payload.get('title')} Created Successfully")

                self.env['printnode.log.vts.line'].sudo().generate_printnode_process_line(printnode_opr_name='printjob_request',
                    printnode_opr_type='print_request',instance=self.printnode_instance_id.id if self.printnode_instance_id else False,
                    printnode_opr_message=f"{payload.get('title')} Successfully Send To PrintNode For Printing",process_request_message=payload,process_response_message=response_id, log_id=log_id,
                    fault_operation=False)

            else:
                printjob = self.env['printnode.printjob.vts'].sudo().browse(printjob_id.id)
                printjob.write({'printnode_instance_id': self.printnode_instance_id.id,
                                'print_status': 'failed'})

                log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(printnode_opr_name='printjob_request',
                    printnode_opr_type='print_request',instance=self.printnode_instance_id.id,
                    printnode_opr_message="Error during Printjob Printing Process")

                self.env['printnode.log.vts.line'].sudo().generate_printnode_process_line(printnode_opr_name='printjob_request',
                    printnode_opr_type='print_request',instance=self.printnode_instance_id.id if self.printnode_instance_id else False,
                    printnode_opr_message=f"Error during the {payload.get('title')} print job process",process_request_message=payload,process_response_message=printjob_request.text,log_id=log_id,
                    fault_operation=True)

        except requests.exceptions.RequestException as e:
            log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(printnode_opr_name='printjob_request',
                printnode_opr_type='print_request',instance=self.printnode_instance_id.id,printnode_opr_message="PrintNode Request Error")

            self.env['printnode.log.vts.line'].sudo().generate_printnode_process_line(printnode_opr_name='printjob_request',
                printnode_opr_type='print_request',instance=self.printnode_instance_id.id if self.printnode_instance_id else False,
                printnode_opr_message=f"Exception during Printjob API Call for {payload.get('title')}",process_request_message=payload, process_response_message=str(e),
                log_id=log_id, fault_operation=True)

        except Exception as e:
            log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(printnode_opr_name='printjob_request',
                printnode_opr_type='print_request',instance=self.printnode_instance_id.id,
                printnode_opr_message="PrintNode PrintJob Error")

            self.env['printnode.log.vts.line'].sudo().generate_printnode_process_line(printnode_opr_name='printjob_request',
                printnode_opr_type='print_request',instance=self.printnode_instance_id.id if self.printnode_instance_id else False,
                printnode_opr_message=f"Error During Requesting for {payload.get('title')} Printjob",process_request_message=payload,process_response_message=str(e),
                log_id=log_id,fault_operation=True)


