# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # ── Global SFTP Credentials ────────────────────────────────────────────────
    gmc_sftp_host = fields.Char(
        string="SFTP Host",
        config_parameter="gmc.sftp_host",
        default="partnerupload.google.com",
    )
    gmc_sftp_port = fields.Integer(
        string="SFTP Port",
        config_parameter="gmc.sftp_port",
        default=19321,
    )
    gmc_sftp_username = fields.Char(
        string="SFTP Username",
        config_parameter="gmc.sftp_username",
    )
    gmc_sftp_password = fields.Char(
        string="SFTP Password",
        config_parameter="gmc.sftp_password",
    )

    # ── Default Store URL ──────────────────────────────────────────────────────
    gmc_store_url = fields.Char(
        string="Store URL",
        config_parameter="gmc.store_url",
        help="Base URL of your eCommerce store, used to build product and image links.",
    )
