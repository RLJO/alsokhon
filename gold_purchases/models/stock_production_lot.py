# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

class StockProductionLot(models.Model):
    _inherit = 'stock.production.lot'

    gold = fields.Boolean(string="Gold", compute="_compute_gold_state")
    diamond = fields.Boolean(string="Diamond", compute="_compute_gold_state")
    assembly = fields.Boolean(string="assembly", compute="_compute_gold_state")
    def _compute_gold_state(self):
        for this in self:
            if this.product_id.categ_id.is_gold:
                this.gold = True
                this.diamond = False
                this.assembly = False
                break
            elif this.product_id.categ_id.is_diamond:
                this.gold = False
                this.assembly = False
                this.diamond = True
                break
            else:
                this.gold = False
                this.assembly = True
                this.diamond = False

    gross_weight = fields.Float(string="Gross Weight")
    purity_id = fields.Many2one('gold.purity', string="Purity Karat", compute="_compute_purity_id")
    def _compute_purity_id(self):
        for this in self:
            this.purity_id = False
            if this.product_id and this.product_id.categ_id.is_scrap:
                purity_id = self.env['gold.purity'].search([('scrap_purity','=',this.purity)])
                if purity_id:
                    this.purity_id = purity_id.id
            elif this.product_id and not this.product_id.categ_id.is_scrap:
                purity_id = self.env['gold.purity'].search([('purity','=',this.purity)])
                if purity_id:
                    this.purity_id = purity_id.id

    purity = fields.Float(string="Purity")
    is_scrap = fields.Boolean(related="product_id.categ_id.is_scrap" , string="scrap", store=True)
    pure_weight = fields.Float(compute='get_pure_weight',string="Pure Weight", store=True, digits=(16, 3))
    item_category_id = fields.Many2one('item.category',string="Item Category")
    sub_category_id = fields.Many2one('item.category.line', string="Sub Category")
    selling_karat_id = fields.Many2one('product.attribute.value', string="Selling Karat")
    selling_making_charge = fields.Monetary('Selling Making Charge')
    currency_id = fields.Many2one('res.currency', string="Company Currency", related='company_id.currency_id')
    remaining_weight = fields.Float(string="Remaining Weight", store=True, digits=(16, 3))

    @api.depends('gross_weight', 'purity')
    def get_pure_weight(self):
        for rec in self:
            rec.pure_weight = rec.gross_weight * rec.purity / 1000

    @api.depends('gross_weight', 'purity')
    def get_remain_weight(self):
        prev_weight_out = self.env["stock.move.line"].search([('lot_id','in',self.id),('location_id','=',8)])
        prev_weight_in = self.env["stock.move.line"].search([('lot_id','in',self.id),('location_dest_id','=',8)])
        tot_prev_out = 0
        tot_prev_in = 0
        for i in prev_weight_out:
            tot_prev_out += i.pure_weight
        for n in prev_weight_in:
            tot_prev_in += n.pure_weight
        for rec in self:
            rec.remaining_weight += tot_prev_in-tot_prev_out
