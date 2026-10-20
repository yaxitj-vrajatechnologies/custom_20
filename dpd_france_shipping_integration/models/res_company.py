# -*- coding: utf-8 -*-
from odoo import fields, models


class DPDFrCompany(models.Model):
    _inherit = 'res.company'

    use_dpd_fr_shipping_provider = fields.Boolean(copy=False, string="Are You DPD France?",
                                                       help="If use DPD France shipping Integration than value set TRUE.",
                                                       default=False)

    dpd_fr_api_url = fields.Char(string='DPD France API URL', default='https://e-station-testenv.cargonet.software/eprintwebservice/eprintwebservice.asmx')
    dpd_fr_username = fields.Char(string='DPD France Username')
    dpd_fr_password = fields.Char(string='DPD France Password')
    dpd_fr_customer_number = fields.Char(string='DPD France Customer Number')
    dpd_fr_center_number = fields.Char(string='DPD France Center Number')
