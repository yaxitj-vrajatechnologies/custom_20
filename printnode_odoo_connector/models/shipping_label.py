import base64

from odoo import models, fields, _


class ShippingLabelVTS(models.Model):
    """ Shipping Label entity from Deliver Carrier
    """

    _name = 'shipping.label.vts'
    _description = 'Shipping Label VTS'
    _rec_name = 'picking_id'
    _order = 'create_date desc'

    picking_id = fields.Many2one(comodel_name='stock.picking', string='Delivery Order',
                                 domain='[("picking_type_id.code", "=", "outgoing")]', required=True, readonly=True)
    printnode_instance_id = fields.Many2one('printnode.connect', string='PrintNode Instance',ondelete='cascade',help='Select Instance Id')
    carrier_id = fields.Many2one(comodel_name='delivery.carrier', string='Delivery Carrier', required=True,
                                 readonly=True)
    printjob_id = fields.Char(string="Print ID", help="PrintNode job ID returned after the print job is created ")
    tracking_number = fields.Char(string='Tracking Number', readonly=True)
    shipping_label_ids = fields.One2many(comodel_name='shipping.label.attachment', inverse_name='shipping_label_id',
                                         string='Shipping Label',
                                         domain=[('is_return_shipment', '=', False)], readonly=True, copy=False)
    return_label_ids = fields.One2many(comodel_name='shipping.label.attachment', inverse_name='shipping_label_id',
                                       string='Return Shipping Label',
                                       domain=[('is_return_shipment', '=', True)], readonly=True, copy=False)

    def _get_attachment_list(self,paper):
        self.ensure_one()
        attachment_list = []

        def update_attachment_list(label):
            doc = label.attachment_id
            params = {
                'title': doc.name,
                'type': 'qweb-pdf' if doc.mimetype == 'application/pdf' else 'qweb-text',
                'size': paper,
                'copies':self.carrier_id.total_copies
            }
            if label.package_id:
                params['package_id'] = label.package_id
            attachment_list.append((base64.b64encode(doc.raw or b'').decode('ascii'), params))

        if self.env.context.get('label'):
            label = self.env.context.get('label')
            update_attachment_list(label)
            return attachment_list

        for label in self.shipping_label_ids + self.return_label_ids:
            update_attachment_list(label)

        return attachment_list

    def print_through_printnode(self,shipping_label_id=None):
        """ Print Shipping Labels through the printnode service
        """
        user = self.env.user

        for shipping_label in self:
            printer,paper,total_copies = user.get_label_printer(shipping_label.carrier_id)
            if not printer:
                shipping_label.picking_id.message_post(body=("PrintNode printer is not configured. Please configure a printer for the delivery method in PrintNode Delivery carrier settings or either at the Company or User level"))
                return

            attachment_list = shipping_label._get_attachment_list(paper)
            if not attachment_list:
                continue

            for ascii_data, params in attachment_list:

                print_label=printer.print_base64_report(ascii_data, params,label_paper=paper, label_id=self)
                if print_label:
                    shipping_label.picking_id.message_post(body=(
                        "Shipping label printed successfully"))
                else:
                    shipping_label.picking_id.message_post(body=(
                "PrintNode: Package report is not configured in company settings. "
                "Package label was not printed."))