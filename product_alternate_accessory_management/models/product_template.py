from odoo import models, api, fields
import json


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    product_brand_id = fields.Many2one(
        'product.brand.vts',
        string="Product Brand",
        help="Name of the brand"
    )

    def create_product_logs(self, log, relation_type, operation_type, product, related_product, message):
        self.env['product.log.line.vts'].sudo().create_log_line(log, relation_type, operation_type, product,
                                                                related_product, message)

        # ----------------------------------------------------------------------------------------------------------
        #                          Alternate Product Code
        # ----------------------------------------------------------------------------------------------------------

    def _get_alternative_rules(self):
        # getting value from ir config
        ICP = self.env['ir.config_parameter'].sudo()

        main_rule_ids = json.loads(ICP.get_str('product_alternate_accessory_management.main_rule_ids') or '[]')
        other_rule_ids = json.loads(ICP.get_str('product_alternate_accessory_management.other_rule_ids') or '[]')

        main_rules = self.env['product.rule.vts'].browse(main_rule_ids)
        other_rules = self.env['product.rule.vts'].browse(other_rule_ids)

        return main_rules.mapped('code'), other_rules.mapped('code')

    def _get_base_domain(self, product):
        # Default domain
        return [
            ('id', '!=', product.id),
            ('sale_ok', '=', True),
            ('active', '=', True),
            ('company_id', '=', product.company_id.id),
        ]

    def _apply_main_rules(self, domain, product, main_rule_codes):
        # Main product alternate rules
        if not main_rule_codes:
            return None

        if 'category' in main_rule_codes:
            domain.append(('categ_id', '=', product.categ_id.id))

        if 'brand' in main_rule_codes and product.product_brand_id:
            domain.append(('product_brand_id', '=', product.product_brand_id.id))

        return domain

    def _apply_other_rules(self, domain, product, other_rule_codes):
        # other alternate product rules
        # PRICE
        if 'price' in other_rule_codes:
            ICP = self.env['ir.config_parameter'].sudo()
            min_percent = ICP.get_float('product_alternate_accessory_management.min_price_range') or 0.1
            max_percent = ICP.get_float('product_alternate_accessory_management.max_price_range') or 0.1

            min_price = product.list_price * (1 - min_percent)
            max_price = product.list_price * (1 + max_percent)

            domain += [
                ('list_price', '>=', min_price),
                ('list_price', '<=', max_price),
            ]

        # STOCK
        if 'in_stock' in other_rule_codes:
            domain.append(('qty_available', '>', 0))

        # TAGS
        if 'tags' in other_rule_codes and product.product_tag_ids:
            domain.append(('product_tag_ids', 'in', product.product_tag_ids.ids))

        return domain

    def _remove_from_other_alternatives(self, product):
        """Remove given product from all other product's alternative list"""
        product.alternative_product_ids = [(5, 0, 0)]
        linked_products = self.env['product.template'].sudo().search([
            ('alternative_product_ids', 'in', product.id)
        ])
        log_id = False
        if linked_products:
            log_id = self.env['product.log.vts'].generate_log(relation_type='alternative',
                                                              product=product, message='Alternative products updated')

        for rec in linked_products:
            rec.write({'alternative_product_ids': [(3, product.id)]})
            self.create_product_logs(log_id, 'alternative', 'remove',
                                     rec, product, f"Product {product.display_name} removed from alternative product")
            self.create_product_logs(log_id, 'alternative', 'remove',
                                     product, rec, f"Product {rec.display_name} removed from alternative product")

    def _filter_by_attribute_match(self, product, alternative_products):
        # attributes rules
        product_attr_map = {}

        for line in product.attribute_line_ids:
            product_attr_map[line.attribute_id.id] = set(line.value_ids.ids)

        filtered_products = self.env['product.template']
        if not product_attr_map:
            return filtered_products

        total_attributes = len(product_attr_map)
        required_match = max(1, round(total_attributes * 0.5))

        for alternative_product in alternative_products:
            matched_attribute_count = 0
            for line in alternative_product.attribute_line_ids:
                attr_id = line.attribute_id.id
                if attr_id in product_attr_map:

                    product_values = product_attr_map[attr_id]
                    alternative_values = set(line.value_ids.ids)

                    if product_values & alternative_values:
                        matched_attribute_count += 1
            if matched_attribute_count >= required_match:
                filtered_products |= alternative_product

        return filtered_products

    def _is_product_valid_for_rules(self, product, main_rule_codes, other_rule_codes):
        """Check if product is eligible for alternative computation"""

        if not main_rule_codes:
            return False

        if 'brand' in main_rule_codes and not product.product_brand_id:
            return False

        if 'in_stock' in other_rule_codes and product.qty_available <= 0:
            return False

        if 'tags' in other_rule_codes and not product.product_tag_ids:
            return False

        return True

    @api.constrains('list_price', 'categ_id', 'qty_available', 'attribute_line_ids', 'product_brand_id',
                    'product_tag_ids', 'company_id')
    def _compute_alternative_products(self):

        main_rule_codes, other_rule_codes = self._get_alternative_rules()

        if not main_rule_codes:
            return

        for product in self:
            old_alternatives = product.alternative_product_ids

            is_product_valid = self._is_product_valid_for_rules(product, main_rule_codes, other_rule_codes)

            if not is_product_valid:
                product.alternative_product_ids = [(5, 0, 0)]
                self._remove_from_other_alternatives(product)
                continue
            domain = self._get_base_domain(product)

            domain = self._apply_main_rules(domain, product, main_rule_codes)
            if domain is None:
                continue
            if other_rule_codes:
                domain = self._apply_other_rules(domain, product, other_rule_codes)

            alternative_products = self.env['product.template'].search(domain)

            # ATTRIBUTE FILTER (only if selected)
            if 'attributes' in other_rule_codes and alternative_products:
                filtered_products = self._filter_by_attribute_match(
                    product, alternative_products
                )
                alternative_products = filtered_products or self.env['product.template']

            product.alternative_product_ids = [(6, 0, alternative_products.ids)]

            new_alternatives = product.alternative_product_ids

            added = new_alternatives - old_alternatives
            removed = old_alternatives - new_alternatives

            if added or removed:
                log_id = self.env['product.log.vts'].generate_log(relation_type='alternative',
                    product=product,message='Alternative products updated')

                for alt in added:
                    self.create_product_logs(log_id, 'alternative', 'add',
                        product, alt,f"Product {alt.display_name} added as alternative product")

                    # REVERSE SYNC + LOG
                    if product.id not in alt.alternative_product_ids.ids:
                        alt.write({'alternative_product_ids': [(4, product.id)]})
                        self.create_product_logs(log_id, 'alternative', 'add',
                            alt, product,f"Product {product.display_name} added as alternative product")

                for alt in removed:
                    self.create_product_logs(log_id, 'alternative', 'remove',
                                             product, alt,
                                             f"Product {alt.display_name} removed from alternative product")

                    if product.id in alt.alternative_product_ids.ids:
                        remaining_ids = alt.alternative_product_ids.ids.copy()
                        remaining_ids.remove(product.id)

                        alt.write({'alternative_product_ids': [(6, 0, remaining_ids)]})
                        self.create_product_logs(log_id, 'alternative', 'remove',
                                                 alt, product,
                                                 f"Product {product.display_name} removed from alternative product")

    # ----------------------------------------------------------------------------------------------------------
    #                         Product Accessories Code
    # ----------------------------------------------------------------------------------------------------------

    def _remove_from_other_accessories(self, product, rule):
        """Remove given variant only from products affected by this rule"""

        Product = self.env['product.template'].sudo()
        variant_id = product.product_variant_id.id

        linked_products = Product.search([
            ('accessory_product_ids', 'in', variant_id),
            ('categ_id', '=', rule.category_id.id),
            ('company_id', '=', product.company_id.id)
        ])

        for rec in linked_products:
            rec.write({'accessory_product_ids': [(3, variant_id)]})

    def _apply_accessory_rules(self, product, rules, domain):
        """Apply dynamic accessory rules on domain"""

        for rule in rules:
            if rule.code == 'brand' and product.product_brand_id:
                domain.append(('product_brand_id', '=', product.product_brand_id.id))

            if rule.code == 'tags' and product.product_tag_ids:
                domain.append(('product_tag_ids', 'in', product.product_tag_ids.ids))

            if rule.code == 'in_stock':
                domain.append(('qty_available', '>', 0))

        return domain

    def _valid_product(self, product, matched_rule):
        for rule in matched_rule.accessory_product_rule_ids:
            if 'brand' in rule.code and not product.product_brand_id:
                return False
            if 'tags' in rule.code and not product.product_tag_ids:
                return False
            if 'in_stock' in rule.code and product.qty_available <= 0:
                return False

        return True

    @api.constrains('list_price', 'categ_id', 'product_brand_id', 'product_tag_ids', 'company_id')
    def _compute_product_accessories(self):
        """this method is used at the time of adding accessories to the product"""

        Product = self.env['product.template'].sudo()
        accessory_rules = self.env['product.accessory.vts'].search([])

        for product in self:

            all_matched_rules = accessory_rules.filtered(lambda r:
                                                         product.categ_id.id == r.category_id.id
                                                         or product.categ_id.id in r.accessory_category_ids.ids)
            if not all_matched_rules:
                all_products = self.env['product.template'].sudo().search([
                    ('accessory_product_ids', 'in', product.product_variant_id.id)
                ])
                if all_products:
                    all_products.write({
                        'accessory_product_ids': [(3, product.product_variant_id.id)]
                    })

            for matched_rule in all_matched_rules:
                matched_rule.filtered(lambda r: r.category_id.id == product.categ_id.id)

                if matched_rule and matched_rule.accessory_category_ids.id == product.categ_id.id:
                    product._update_product_accessory(product, matched_rule)
                    continue

                accessory_category_ids = matched_rule.accessory_category_ids.ids

                # No categories → clear
                if not accessory_category_ids:
                    product.accessory_product_ids = [(5, 0, 0)]
                    continue

                # Rule codes
                rule_codes = matched_rule.accessory_product_rule_ids.mapped('code')

                if 'in_stock' in rule_codes and product.qty_available <= 0:
                    product.accessory_product_ids = [(5, 0, 0)]
                    self._remove_from_other_accessories(product, matched_rule)
                    continue

                # Base domain
                domain = [
                    ('categ_id', 'in', accessory_category_ids),
                    ('sale_ok', '=', True),
                    ('active', '=', True),
                    ('id', '!=', product.id),
                    ('company_id', '=', product.company_id.id)
                ]

                # Apply dynamic rules
                domain = self._apply_accessory_rules(product, matched_rule.accessory_product_rule_ids, domain)

                is_product_valid = self._valid_product(product, matched_rule)
                if not is_product_valid:
                    product.accessory_product_ids = [(5, 0, 0)]
                    continue

                accessory_products = Product.search(domain)
                variants = accessory_products.mapped('product_variant_id').exists()

                old_ids = product.accessory_product_ids.product_tmpl_id.ids
                product.accessory_product_ids = [(6, 0, variants.ids)]

                new_ids = accessory_products.ids

                added = list(set(new_ids) - set(old_ids))
                removed = list(set(old_ids) - set(new_ids))

                if added or removed:
                    log_id = self.env['product.log.vts'].generate_log(relation_type='accessory',
                                                                      product=product,
                                                                      message='Accessory products updated')

                    # ADD
                    for acc in self.env['product.template'].browse(added):
                        self.create_product_logs(log_id, 'accessory', 'add',
                                                 product, acc, f"Product {acc.display_name} added as accessory product")

                    # REMOVE (rule scoped)
                    for acc in self.env['product.template'].browse(removed):
                        self._remove_from_other_accessories(acc, matched_rule)

                        self.create_product_logs(log_id, 'accessory', 'remove',
                                                 product, acc,
                                                 f"Product {acc.display_name} removed from accessory product")

    # ----------------------------------------------------------------------------------------------------------
    # Reverse Updates (this below method only calls when changes made in the accessories)
    # ----------------------------------------------------------------------------------------------------------

    def _update_product_accessory(self, product, rule):

        """this method is changed occured in the accessories product"""

        Product = self.env['product.template'].sudo()
        product_variant_id = product.product_variant_id.id

        if not product_variant_id:
            return

        #  Products that currently have this accessory
        main_products = Product.search([
            ('accessory_product_ids', 'in', product_variant_id),
            ('categ_id', '=', rule.category_id.id),
            ('company_id', '=', product.company_id.id)
        ])

        #  If product no longer valid for this rule → remove everywhere
        if product.categ_id.id not in rule.accessory_category_ids.ids:
            main_products.write({'accessory_product_ids': [(3, product_variant_id)]})
            return

        #  Rule codes (brand, tags, in_stock)
        rule_codes = rule.accessory_product_rule_ids.mapped('code')

        # if product does not found according to the rule and rule than remove current product from main product
        if (('brand' in rule_codes and not product.product_brand_id)
                or ('tags' in rule_codes and not product.product_tag_ids)
                or ('in_stock' in rule_codes and product.qty_available <= 0)):
            main_products.write({
                'accessory_product_ids': [(3, product_variant_id)]
            })
            return

        #  BASE DOMAIN
        domain = [
            ('id', '!=', product.id),
            ('categ_id', '=', rule.category_id.id),
            ('sale_ok', '=', True),
            ('active', '=', True),
            ('company_id', '=', product.company_id.id)
        ]

        #  Apply dynamic rules
        domain = self._apply_accessory_rules(product, rule.accessory_product_rule_ids, domain)

        # Products that should have this accessory
        product_search = Product.search(domain)

        to_remove = main_products - product_search
        to_add = product_search - main_products

        log_id = False
        if to_remove or to_add:
            log_id = self.env['product.log.vts'].generate_log(relation_type='accessory',
                                                              product=product, message='Accessory products updated')
        for rec in to_remove:
            if product_variant_id in rec.accessory_product_ids.ids:
                rec.write({
                    'accessory_product_ids': [(3, product_variant_id)]
                })
                self.create_product_logs(log_id, 'accessory', 'remove',
                                         product, rec, f"Product {rec.display_name} removed from accessory product")

        for rec in to_add:
            if product_variant_id not in rec.accessory_product_ids.ids:
                rec.write({
                    'accessory_product_ids': [(4, product_variant_id)]
                })
                self.create_product_logs(log_id, 'accessory', 'add',
                                         product, rec, f"Product {rec.display_name} added as accessory product")
