# -*- coding: utf-8 -*-
from odoo import models, fields

class GMCFeedAttributeMapping(models.Model):
    _name = "gmc.feed.attribute.mapping"
    _description = "GMC Feed Attribute Mapping"

    feed_id = fields.Many2one("gmc.feed", string="Feed", required=True, ondelete="cascade", index=True)
    attribute_id = fields.Many2one("product.attribute", string="Odoo Attribute", required=True)
    gmc_tag = fields.Selection([
        ('g:color', 'Color (g:color)'),
        ('g:size', 'Size (g:size)'),
        ('g:material', 'Material (g:material)'),
        ('g:pattern', 'Pattern (g:pattern)'),
        ('g:gender', 'Gender (g:gender)'),
        ('g:age_group', 'Age Group (g:age_group)'),
        ('g:custom_label_0', 'Custom Label 0'),
        ('g:custom_label_1', 'Custom Label 1'),
        ('g:custom_label_2', 'Custom Label 2'),
        ('g:custom_label_3', 'Custom Label 3'),
        ('g:custom_label_4', 'Custom Label 4'),
        ('custom', 'Custom Tag...'),
        ('ignore', 'Do Not Export'),
    ], string="Google Tag", required=True)
    custom_tag = fields.Char(string="Custom Tag", help="e.g. g:custom")

    _feed_attribute_uniq = models.Constraint(
        'unique(feed_id, attribute_id)',
        'Each attribute can only be mapped once per feed!',
    )