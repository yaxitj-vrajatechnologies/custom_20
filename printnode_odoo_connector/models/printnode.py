# -*- coding: utf-8 *-*
import pprint
from odoo.exceptions import UserError
from odoo import models, fields,_


class PrintNodeConnect(models.Model):

    _name = "printnode.connect"
    _description = "PrintNode Connect"


    name = fields.Char(string="Name",required=True,help="Name of this PrintNode configuration.")
    printnode_api_key = fields.Char(string="PrintNode API Key",required=True,help="API Key from your PrintNode account. Used by Odoo to authenticate with PrintNode Cloud.")
    printnode_api = fields.Char(string="PrintNode API",required=True,default="https://api.printnode.com",help="API used for connection with the PrintNode")
    printnode_printer_count = fields.Integer(string="Printers Counts",compute="_computer_printnode_printer_count")
    printnode_computer_count = fields.Integer(string="Computer Counts",compute="_computer_printnode_computer_count")


    def build_printnode_log(self, entity_name, message, instance_id, entity_data=None, log_id=None, fault=False):
        """
        Method Used for generating log details for import operation
        """
        return {
            'printnode_opr_name': entity_name,
            'printnode_opr_type': 'import',
            'printnode_instance_id': instance_id,
            'printnode_opr_message': message,
            'process_response_message': pprint.pformat(entity_data),
            'printnode_opr_id': log_id.id if log_id else False,
            'fault_operation': fault
        }

    def _computer_printnode_printer_count(self):
        for rec in self:
            rec.printnode_printer_count=self.env['printnode.printer.vts'].sudo().search_count([('printnode_instance_id','=',rec.id)])

    def action_printnode_printer(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("printnode_odoo_connector.action_printnode_printers")
        action['domain'] = [('printnode_instance_id','=',self.id)]
        return action

    def _computer_printnode_computer_count(self):
        for rec in self:
            rec.printnode_computer_count=self.env['printnode.computer.vts'].sudo().search_count([('printnode_instance_id','=',rec.id)])

    def action_printnode_computer(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("printnode_odoo_connector.action_printnode_computer_menu")
        action['domain'] = [('printnode_instance_id','=',self.id)]
        return action

    def get_printers_from_printnode(self,computer_id):
        """
        Get all printers connected with this computer_id
        and auto-disconnect printers not returned by API.
        """
        # URL for getting all connected printers with computer_id
        printer_endpoint = f'computers/{computer_id}/printers'

        printer_info, printer_status = self.env['printnode.api.vts'].get_data_from_printnode(
            self.printnode_api, self.printnode_api_key, printer_endpoint)

        if printer_status == 200 and printer_info:

            printer_vals_list = []
            log_lines = []
            printer_creation =False
            active_printer_ids=[]

            log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(printnode_opr_name='printer',printnode_opr_type='import',
                        instance=self.id,printnode_opr_message='Fetch All Printers From PrintNode')

            for printer in printer_info:
                if not printer or not isinstance(printer, dict):
                    continue
                printer_id = printer.get("id")
                active_printer_ids.append(printer_id)

                capabilities = printer.get('capabilities') or {}
                papers_dict = capabilities.get('papers') or {}

                paper_ids = []
                for paper_name, size in papers_dict.items():
                    try:
                        width_mm = size[0] / 10.0
                        height_mm = size[1] / 10.0
                    except Exception:
                        continue

                    paper_record = self.env['printnode.paper.vts'].sudo().search([('name', '=', paper_name)], limit=1)

                    if not paper_record:
                        paper_record = self.env['printnode.paper.vts'].sudo().create({
                            'name': paper_name,
                            'width': width_mm,
                            'height': height_mm,
                        })

                    paper_ids.append(paper_record.id)

                if printer_id:
                    existing_printer = self.env["printnode.printer.vts"].sudo().search([
                        ("printer_id", "=", printer_id), ("printnode_instance_id", "=", self.id)],limit=1)

                    if existing_printer:
                        existing_printer.write({"status": printer.get("state"),
                                                "paper_ids": [(6, 0, paper_ids)]})

                        msg = f"PrintNode Printer is already Exist with id {printer_id}"
                        log_lines.append(self.build_printnode_log(entity_name='printer', message=msg,
                                instance_id=self.id, entity_data=printer,log_id=log_id, fault=False))
                        continue

                    computer = self.env['printnode.computer.vts'].sudo().search([('printnode_computer_id', '=', computer_id),
                         ('printnode_instance_id', '=', self.id)], limit=1)
                    vals = {
                        "printer_id": printer_id,
                        "name": printer.get("name"),
                        "status": printer.get("state"),
                        "description": printer.get("description"),
                        "computer_id": computer.id,
                        "paper_ids": [(6, 0, paper_ids)],
                        "is_printer_active": printer.get("default"),
                        "printnode_instance_id": self.id,
                    }
                    printer_vals_list.append(vals)
                    msg = "PrintNode printer imported successfully"
                    log_lines.append(self.build_printnode_log(entity_name='printer', message=msg,instance_id=self.id,
                                                              entity_data=printer, log_id=log_id, fault=False))
            if printer_vals_list:
                printer_creation = self.env['printnode.printer.vts'].sudo().create(printer_vals_list)

            computer = self.env['printnode.computer.vts'].sudo().search([
                ('printnode_computer_id', '=', computer_id),
                ('printnode_instance_id', '=', self.id)], limit=1)

            if computer:
                existing_printers = self.env['printnode.printer.vts'].sudo().search([
                    ('computer_id', '=', computer.id),('printnode_instance_id', '=', self.id),
                    ('status','=','online')])

                for printer in existing_printers:
                    if int(printer.printer_id) not in active_printer_ids:
                        printer.write({
                            "status": "offline",
                            "is_printer_active": False
                        })


            if log_lines:
                log_creation = self.env['printnode.log.vts.line'].sudo().create(log_lines)

            return printer_creation
        else:
            log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(printnode_opr_name='printer',
                        printnode_opr_type='import',instance=self.id,printnode_opr_message="Error during printers import process")
            self.build_printnode_log(entity_name='computer', message='Error during printers import process',
                                     instance_id=self.id,entity_data=printer_info, log_id=log_id, fault=True)

    def sync_all_printnode_data(self):
        """
        Send request with basic authentication and API key
        """
        if not self.printnode_api_key and not self.printnode_api:
            UserError("Please Enter the PrintNode Api to SYNC all data from PrintNode")

        computer_info, computer_status = self.env['printnode.api.vts'].get_data_from_printnode(
            self.printnode_api, self.printnode_api_key, 'computers')

        if computer_status == 200 and computer_info:
            log_lines = []

            log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(printnode_opr_name='computer',
                    printnode_opr_type='import',instance=self.id,printnode_opr_message='Fetch All Computers From PrintNode')

            for computer in computer_info:
                computer_id = computer.get("id")

                computer_record = self.env["printnode.computer.vts"].sudo().search([("printnode_computer_id", "=", computer_id),
                    ("printnode_instance_id", "=", self.id)],limit=1)
                if not computer_record:
                    computer_record = self.env["printnode.computer.vts"].sudo().create({
                        'name': computer.get("name"),
                        'printnode_computer_id': computer_id,
                        'printnode_instance_id': self.id,
                        'state': computer.get('state')
                    })
                    msg = "PrintNode Computer Imported Successfully"
                elif computer_record:
                    computer_record.write({"state": computer.get('state')})
                    msg= "PrintNode Computer is Already Exist"
                log_lines.append(self.build_printnode_log(entity_name='computer', message=msg, instance_id=self.id,
                                                          entity_data=computer, log_id=log_id, fault=False))
                self.get_printers_from_printnode(computer_id)

            if log_lines:
                log_creation = self.env['printnode.log.vts.line'].sudo().create(log_lines)
        else:
            log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(printnode_opr_name='computer',
                        printnode_opr_type='import',instance=self.id,printnode_opr_message="Error during computer import process")
            self.build_printnode_log(entity_name='computer', message='Error during computer import process', instance_id=self.id,
                                     entity_data=computer_info, log_id=log_id, fault=True)


    def check_printer_status(self, printer):
        """ Re-check particular printer status
        """
        try:
            printer_endpoint = f'printers/{printer.printer_id}'

            res_info, res_status = self.env['printnode.api.vts'].get_data_from_printnode(
                self.printnode_api, self.printnode_api_key, printer_endpoint)

            if res_status in (200, 204, 403) and res_info:

                printer_status = res_info[0].get('state', 'offline')
                computer_status = res_info[0]['computer'].get('state', 'disconnected')

                if printer.status != printer_status:
                    printer.status = printer_status

                if printer.computer_id.state != computer_status:
                    printer.computer_id.state = computer_status

                if printer_status == 'online' and computer_status == 'connected':
                    printer.is_printer_active = True
                else:
                    printer.is_printer_active = False

                return printer.is_printer_active

            else:
                printer.write({'status': 'offline'})
                printer.is_printer_active = False

            log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(printnode_opr_name='printjob_request',
                    printnode_opr_type='print_request',instance=self.id,
                    printnode_opr_message=f"Printer is not configure with the printnode or printer is not online")

            self.build_printnode_log(entity_name='printjob_request', message='Printer is not configure with the printnode or printer is offline',
                                     instance_id=self.id,entity_data=str(res_info), log_id=log_id, fault=True)
            return

        except Exception as e:
            printer.is_printer_active = False
            log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(printnode_opr_name='printjob_request',
                printnode_opr_type='print_request',instance=self.id ,printnode_opr_message="Exception occurred while fetching printer state")

            self.build_printnode_log(entity_name='printjob_request',
                                     message='Error in printer state API call',
                                     instance_id=self.id, entity_data=str(e), log_id=log_id, fault=True)

        return printer.is_printer_active

    def unlink(self):
        for rec in self:
            self.env['printnode.computer.vts'].sudo().search([('printnode_instance_id', '=', rec.id)]).unlink()
            self.env['printnode.printer.vts'].sudo().search([('printnode_instance_id', '=', rec.id)]).unlink()
            self.env['printnode.printjob.vts'].sudo().search([('printnode_instance_id', '=', rec.id)]).unlink()
            self.env['printnode.log.vts'].sudo().search([('printnode_instance_id', '=', rec.id)]).unlink()
            self.env['shipping.label.vts'].sudo().search([('printnode_instance_id', '=', rec.id)]).unlink()

        return super(PrintNodeConnect, self).unlink()

    def cron_sync_all_printnode_data(self):
        instances = self.search([])
        for rec in instances:
            rec.sync_all_printnode_data()


