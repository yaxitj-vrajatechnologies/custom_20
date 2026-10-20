import math
import re

from odoo import fields, models, _


class StockPicking(models.Model):
    _name = 'stock.picking'
    _inherit = ['stock.picking', 'printnode.rule.mixin']

    shipping_label_ids = fields.One2many(comodel_name='shipping.label.vts', inverse_name='picking_id',
                                         string='Shipping Labels')

    def button_validate(self):
        """
         Overriding the default method to add custom logic with print rules for picking validate.
        """
        res = super(StockPicking, self).button_validate()
        if res is True:
            self.print_rule('print_document_on_transfer')

            # Print product labels
            self.print_rule('print_product_label_transfer')
            self.print_rule('print_product_label_when_packaging_on_transfer')

            # Print packages
            self.print_rule('print_label_of_packages_on_transfer')

        return res

    def _rule_print_put_in_pack_package(self, rule, report_info, printer_id, total_copies, packages_to_print=None,
                                        **kwargs):
        """
        Print new packages from stock.picking.
        packages_to_print is a recordset of stock.package to print
        """
        printer_id.printnode_print_document(report_info, packages_to_print, total_copies=total_copies)

    def _compute_state(self):
        """Override stock.picking status update method
        """
        previous_states = {rec.id: rec.state for rec in self}

        super()._compute_state()

        for record in self:
            if record.id and previous_states.get(record.id) != record.state:
                record.with_company(record.company_id).print_rule('print_document_when_picking_status_change')

    def _rule_print_document_when_picking_status_change(self, rule, report_info, printer_id, total_copies=1):

        printed = printer_id.printnode_print_document(report_info, self, total_copies=total_copies)
        return printed

    def _rule_print_label_of_packages_on_transfer(self, report_info, printer_id, total_copies=1):

        packages_id = self.move_line_ids.result_package_id

        if packages_id:
            return printer_id.printnode_print_document(report_info, packages_id, total_copies=total_copies)
        return False

    def _rule_print_product_label_transfer(self, rule, total_copies=1, **kwargs):
        """
          Print single product label for each move line (real time)
          Special method to provide custom logic of printing (like printing labels through wizards)
        """
        prepared_data = self._prepare_data_for_rule_to_print_product_labels(
            rule, move_lines=kwargs.get('changed_move_lines', self.move_line_ids), with_qty=True, **kwargs, )

        if not prepared_data:
            return False

        printer = self.env.user.sudo().get_printer(prepared_data.get('report_id').id)
        if not printer:
            log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(
                printnode_opr_name='printer_configuration',
                printnode_opr_type='print_request', instance="",
                printnode_opr_message=f"No printer configured for report {prepared_data.get('report_id').name}")

            self.env['printnode.log.vts.line'].sudo().generate_printnode_process_line(
                printnode_opr_name='printer_configuration', printnode_opr_type='print_request',
                instance="",
                printnode_opr_message=f"Printer configuration missing for report {prepared_data.get('report_id').name}",
                process_response_message="No printer defined at user level or company level.", log_id=log_id,
                fault_operation=True)
            return False
        printed = printer.printnode_print_document(report_info=prepared_data.get('report_id'),
                                                   objects=prepared_data.get('product_ids'), total_copies=total_copies,
                                                   data=prepared_data.get('data'))

        return printed

    def _prepare_data_for_rule_to_print_product_labels(self, rule, move_lines=None, with_qty=False, **kwargs):
        """
        This method prepares data to print product labels (using odoo Print Labels wizard)

        :param rule: required current rule
        :param moves: required stock moves from stock picking
        :param with_qty: optional boolean to change the move_quantity mode of wizard
        """

        move_lines_with_qty_done = move_lines.filtered(lambda ml: ml.quantity > 0)

        product_ids = move_lines_with_qty_done.mapped('product_id')

        if not product_ids:
            return False

        wizard = self._setup_product_label_layout_wizard(
            product_ids=product_ids,
            print_format=self.env.company.product_labels_format if self.env.company.product_labels_format else '2x7xprice',
        )
        printing_data = self._prepare_print_data(rule, wizard, **kwargs)
        printing_data['product_ids'] = product_ids

        return printing_data

    def _setup_product_label_layout_wizard(
            self, product_ids, print_format, **kwargs):
        """
        This method needed for ZPL Label Designer to allow pass additional fields to wizard.
        For now we use it to pass zld_label_id field to wizard.
        """
        with_price = print_format.endswith('xprice')
        if with_price:
            print_format = print_format[:-len('xprice')]

        return self.env['product.label.layout'].sudo().create({
            'product_ids': product_ids,
            'print_format': print_format,
            'with_price': with_price,
            **kwargs, })

    def _prepare_print_data(self, rule, wizard, **kwargs):
        """
        This method prepares all data required for rules to print something using Print Labels
        wizard (wizard parameter)
        """
        print_options = kwargs.get('options', {})

        if rule.printer_id:
            printer_id = rule.printer_id
        else:
            printer_id = self.env.company.label_printer_id

        # Get report
        xml_id, data = wizard._prepare_report_data()
        report_id = self.env.ref(xml_id)

        # Change type of dictionary keys to string
        if data.get('quantity_by_product'):
            data['quantity_by_product'] = {
                str(key): value
                for key, value in data['quantity_by_product'].items()
            }

        return {
            'printer_id': printer_id,
            'report_id': report_id,
            'data': data,
            'print_options': print_options,
        }

    def _rule_print_product_label_when_packaging_on_transfer(self, rule, total_copies=1, **kwargs):
        """
        Print multiple product labels based on packaging for each move line (after validation).
        Special method to provide custom logic of printing (like printing labels through wizards)
        """
        move_lines_qty_done_and_packaging = self.move_line_ids.filtered(
            lambda ml: (
                    ml.move_id.packaging_uom_id
                    and ml.move_id.packaging_uom_id.relative_factor != 0
                    and ml.quantity > 0))

        prepared_data = self._prepare_data_for_rule_to_print_product_labels(
            rule, move_lines=move_lines_qty_done_and_packaging, **kwargs)

        if not prepared_data:
            return False

        data = prepared_data.get('data', {}).get('quantity_by_product')

        for move_line in move_lines_qty_done_and_packaging:
            if move_line.move_id.packaging_uom_id:
                package = move_line.move_id.packaging_uom_id  # Assuming you want the first package
                total_package_qty = package.relative_factor
                labels_qty = move_line.quantity / total_package_qty if total_package_qty else 0
            else:
                labels_qty = 0
            # labels_qty = move_line.quantity / move_line.move_id.package_ids.qty # migrate use package_ids instead of product_packaging_id

            product_id = move_line.product_id.id
            if isinstance(product_id, int):
                product_id = str(product_id)
                data[product_id] = math.ceil(labels_qty)
        printer = self.env.user.sudo().get_printer(prepared_data.get('report_id').id)
        if not printer:
            log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(
                printnode_opr_name='printer_configuration',
                printnode_opr_type='print_request', instance="",
                printnode_opr_message=f"No printer configured for report {prepared_data.get('report_id').name}")

            self.env['printnode.log.vts.line'].sudo().generate_printnode_process_line(
                printnode_opr_name='printer_configuration', printnode_opr_type='print_request',
                instance="",
                printnode_opr_message=f"Printer configuration missing for report {prepared_data.get('report_id').name}",
                process_response_message="No printer defined at user level or company level.", log_id=log_id,
                fault_operation=True)
            return False

        printed = printer.printnode_print_document(report_info=prepared_data.get('report_id'),
                                                   objects=prepared_data.get('product_ids'), total_copies=total_copies,
                                                   data=prepared_data.get('data'))

        return printed

    def _create_backorder(self, backorder_moves=None):
        backorders = super(StockPicking, self)._create_backorder(backorder_moves)

        if backorders:
            self.print_rule('print_backorder_document', backorders.mapped('id'))

        return backorders

    @staticmethod
    def _is_return_label_message(message, return_label_prefix):
        """
        Check if a message is a return label message.
        """
        for attach_id in message.attachment_ids:
            if attach_id.description and attach_id.description.find(return_label_prefix) != -1:
                return True
        return False

    def _get_tracking_message(self, tracking_number):
        """
        Getting all messages related to the current stock picking, where the body
        contains any of the given tracking references.
        """
        base_domain = [
            ('model', '=', 'stock.picking'),
            ('res_id', '=', self.id),
            ('message_type', '=', 'notification')
        ]

        messages = self.env['mail.message']

        if tracking_number:
            # Add to base_domain with the conditions "OR" if there are several tracking references.
            # If there is one, add it to the domain using "AND"
            tracking_domain = ['|'] * (len(tracking_number) - 1)
            for track in tracking_number:
                tracking_domain.append(('body', 'ilike', track))
            base_domain += tracking_domain
            return messages.search(base_domain, order='create_date asc')

        return messages

    @staticmethod
    def _get_return_labels(message, return_label_prefix):
        """
        Check if the message is a return label message. If it is, create return label
        attachments for each attachment in that message and return them.
        """
        return_label_attachments = []

        if StockPicking._is_return_label_message(message, return_label_prefix):
            return_label_attachments = [
                (0, 0, {'attachment_id': attach.id, 'is_return_shipment': True})
                for attach in message.attachment_ids
            ]

        return return_label_attachments

    def _get_shipping_label_attachment(self, message):
        label_attachments = []
        packages = self.move_line_ids.result_package_id

        if len(packages) == len(message.attachment_ids):
            for index in range(len(packages)):
                vals = {
                    'attachment_id': message.attachment_ids[-index - 1].id,
                    'package_id': packages[index].id
                }
                label_attachments.append((0, 0, vals))
        else:
            for attach in message.attachment_ids:
                if self.carrier_id.delivery_type in ['ups_provider'] and not 'label' in attach.name.lower():
                    continue
                else:
                    label_attachments.append((0, 0, {'attachment_id': attach.id}))

        return label_attachments

    def _prepare_shipping_labels(self):
        """
        Creates shipping labels for the current stock picking record.
        """

        # Splitting tracking references by separator, if there are several of them
        tracking_number = re.sub(r'[+\-\\,/*\n\t\r]', ' ', self.carrier_tracking_ref).split()

        messages_to_parse = self._get_tracking_message(tracking_number)
        messages_to_parse = messages_to_parse.filtered('attachment_ids')

        # Get return shipping labels
        return_label_prefix = f'LabelReturn-% {self.carrier_id.delivery_type}'

        for i, message in enumerate(messages_to_parse):
            # Skip the message if it's a return label message
            if self._is_return_label_message(message, return_label_prefix):
                continue

            label_attachments = self._get_shipping_label_attachment(message)
            return_label_attachments = []

            next_message = messages_to_parse[i + 1] if i + 1 < len(messages_to_parse) else None
            if next_message:
                return_label_attachments = self._get_return_labels(
                    next_message, return_label_prefix)

            shipping_label_vals = {
                'carrier_id': self.carrier_id.id,
                'picking_id': self.id,
                'tracking_number': self.carrier_tracking_ref,
                'shipping_label_ids': label_attachments,
                'return_label_ids': return_label_attachments,
            }
            shipping_label_id = self.env['shipping.label.vts'].create(shipping_label_vals)
            return shipping_label_id

    def print_recent_shipping_label(self, shipping_label_id):
        """
        Print last shipping label if possible.
        """
        self.ensure_one()

        if self.picking_type_code != 'outgoing':
            return

        label = self.shipping_label_ids[:1]
        return label.print_through_printnode(shipping_label_id)

    def send_to_shipper(self):
        """
        Redefining a standard method
        """
        user = self.env.user
        company = self.env.company

        auto_print = company.auto_print_shipping_label and user.printnode_auto_print

        super(StockPicking, self).send_to_shipper()

        if not self.carrier_tracking_ref:
            return

        if auto_print:
            shipping_label_id = self._prepare_shipping_labels()

            if self.shipping_label_ids:
                self.with_context(raise_exception_slp=False).print_recent_shipping_label(shipping_label_id)


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _put_in_pack(self, package_id=False, package_type_id=False, package_name=False):
        package = super()._put_in_pack(package_id=package_id, package_type_id=package_type_id,
                                       package_name=package_name)

        # Print package label
        if package:
            pickings = self.move_id.picking_id
            if pickings:
                for picking in pickings:
                    if hasattr(picking, 'print_rule'):
                        picking.print_rule('print_package_on_put_in_pack')

        return package
