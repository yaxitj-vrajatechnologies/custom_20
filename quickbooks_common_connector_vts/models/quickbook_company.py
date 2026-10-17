# -*- coding: utf-8 *-*
from odoo import models, fields, api


class QuickbooksCompany(models.Model):

    _name = 'quickbooks.company.vts'
    _description = "Quickbooks Connect Vts"


    name = fields.Char(string="Name")
    quickbook_ID = fields.Char(string="Quickbook Company ID")
    company_email = fields.Char(string="Quickbook Company Email")
    company_response = fields.Text(string="Company Response")