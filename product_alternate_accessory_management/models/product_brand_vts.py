from odoo import models,fields

class ProductBrandVTS(models.Model):
    _name = 'product.brand.vts'
    _description = "Product Brand"

    name = fields.Char(
        string="Name",
        help="Name of the Product Brand"
    )

    short_description = fields.Text(
        string="Short Description",
        help="Shot description of the Brand"
    )

    detailed_description = fields.Html(
        string="Detailed Description",
        help="Detailed description of Brand"
    )

    product_tmpl_ids = fields.One2many(
        'product.template',
        'product_brand_id',
        string="Product",
    )
