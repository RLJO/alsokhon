# -*- coding: utf-8 -*-
from itertools import groupby
from odoo.osv import expression
from odoo import api, fields, models


class AccountAccount(models.Model):
    _inherit = 'account.account'

    gold = fields.Boolean('Gold')


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    gold = fields.Boolean('Gold Journal')


class AccountReport(models.AbstractModel):
    _inherit = 'account.report'

    @api.model
    def _query_get(self, options, domain=None):
        domain = self._get_options_domain(options) + (domain or [])
        self.env['account.move.line'].check_access_rights('read')
        domain = expression.AND([domain, [('journal_id.gold', '=', False)]])
        query = self.env['account.move.line']._where_calc(domain)
        # Wrap the query with 'company_id IN (...)' to avoid bypassing company access rights.
        self.env['account.move.line']._apply_ir_rules(query)
        return query.get_sql()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    gross_wt = fields.Float('Gross Wt', digits=(16, 3))
    purity_id = fields.Many2one('gold.purity', 'Purity')
    pure_wt = fields.Float('Pure Wt', digits=(16, 3))
    purity_diff = fields.Float('Purity +/-', digits=(16, 3))
    total_pure_weight = fields.Float('Pure Weight', digits=(16, 3))
    make_rate = fields.Monetary('Make Rate/G', digits=(16, 3))
    make_value = fields.Monetary('Make Value', digits=(16, 3))
    gold_rate = fields.Float('Gold Rate/G', digits=(16, 3))
    gold_value = fields.Monetary('Gold Value', digits=(16, 3))


class AccountMove(models.Model):
    _inherit = 'account.move'

    def post(self):
        res = super(AccountMove, self).post()
        po_id = self.is_po_related()
        if po_id:
            self.create_gold_journal_entry(po_id)
            
            if self.line_ids:
                for rec in self.line_ids:
                    if rec.account_id.reconcile:
                        rec.update({'account_id': rec.move_id.partner_id.gold_account_payable_id.id})
                    else:
                        if rec.make_value:
                            rec.with_context(check_move_validity=False).update({'account_id': rec.product_id.categ_id.property_account_expense_categ_id.id,'debit': rec.debit - rec.make_value})
            
                            self.env['account.move.line'].with_context(check_move_validity=False).create({
                                'move_id': self.id,
                                'account_id': rec.product_id.categ_id.property_account_expense_categ_id.id,
                                'debit': rec.make_value,
                                'name': rec.name or "",
                            })
        return res


    def is_po_related(self):
        '''
        find's related purchase order, if found check for order type = fixed
        :return: if order type == fixed return po else false
        '''
        po_id = self.env['purchase.order'].search(
            [('invoice_ids', '=', self.id)])
        if po_id and po_id.order_type.is_fixed:
            return po_id
        return False

    def create_gold_journal_entry(self, po_id):
        self.ensure_one()
        gold_journal = self.env.ref('gold_purchases.gold_journal')
        moves = self.invoice_line_ids.filtered(lambda x: x.product_id and
                                                         x.product_id.gold and
                                                         x.product_id.categ_id and
                                                         x.product_id.categ_id.is_gold and
                                                         x.product_id.categ_id.gold_expense_account)
        if moves:
            total_purity = 0
            product_dict = {}
            description = '%s' % po_id.name
            for product_id, move_list in groupby(moves, lambda x: x.product_id):
                description = '%s-%s' % (description, product_id.display_name)
                if product_id not in product_dict.keys():
                    product_dict[product_id] = sum(
                        x.pure_wt for x in move_list)
                else:
                    product_dict[product_id] = product_dict[product_id] + sum(
                        x.pure_wt for x in move_list)
            total_purity = sum(value for key, value in product_dict.items())
            if gold_journal and total_purity > 0.0 and product_dict and \
                    self.partner_id and self.partner_id.gold_account_payable_id:
                journal_id = gold_journal.id
                move_lines = self._prepare_account_move_line(product_dict, po_id)
                if move_lines:
                    AccountMove = self.with_context(default_type='entry',
                        default_journal_id=journal_id)
                    date = self._context.get('force_period_date',
                                             fields.Date.context_today(self))
                    new_account_move = AccountMove.sudo().create({
                        'journal_id': journal_id,
                        'line_ids': move_lines,
                        'date': date,
                        'ref': description,
                        'type': 'entry'
                    })
                    new_account_move.post()
                    print ('----------------------', new_account_move)
                    po_id.write({'stock_move_id': new_account_move.id})

    def _prepare_account_move_line(self, product_dict, po_id):
        debit_lines = []
        for product_id, value in product_dict.items():
            debit_lines.append({
                'name': '%s - %s' % (po_id.name, product_id.name),
                'product_id': product_id.id,
                'quantity': 1,
                'product_uom_id': product_id.uom_id.id,
                'ref': '%s - %s' % (po_id.name, product_id.name),
                'partner_id': self.partner_id.id,
                'debit': round(value, 3),
                'credit': 0,
                'account_id': product_id.categ_id.gold_expense_account.id,
            })
        credit_line = [{
            'name': '%s - %s' % (po_id.name, product_id.name),
            'product_id': product_id.id,
            'quantity': 1,
            'product_uom_id': product_id.uom_id.id,
            'ref': '%s - %s' % (po_id.name, product_id.name),
            'partner_id': self.partner_id.id,
            'debit': 0,
            'credit': sum(x['debit'] for x in debit_lines),
            'account_id': self.partner_id.gold_account_payable_id.id,
        }]
        res = [(0, 0, x) for x in debit_lines + credit_line]
        return res


