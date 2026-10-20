from odoo import models, fields


class ShippingLabelAttachments(models.Model):
    """ Add Attachments to the Shipping Label entity
    """
    _name = 'shipping.label.attachment'
    _description = 'Shipping Label Attachment'
    _rec_name = 'attachment_id'

    shipping_label_id = fields.Many2one(string='Related Shipping Label',comodel_name='shipping.label.vts',ondelete='cascade')
    attachment_id = fields.Many2one(comodel_name='ir.attachment',string='Shipping Label Document')
    package_id = fields.Many2one(string='Package',comodel_name='stock.package',ondelete='set null')
    is_return_shipment = fields.Boolean(string='Is Return Shipping label?',default=False)
