import openerp
import requests
import json

from fedex.services.track_service import FedexTrackRequest
from fedex.config import FedexConfig
from openerp.osv import fields, osv, expression
import logging
_logger = logging.getLogger(__name__)
from dateutil.parser import parse
from openerp import SUPERUSER_ID, workflow
from datetime import datetime
import time
from dateutil.relativedelta import relativedelta
from operator import attrgetter
from openerp.tools.safe_eval import safe_eval as eval
from openerp.osv import fields, osv
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp
from openerp.osv.orm import browse_record_list, browse_record, browse_null
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT, DATETIME_FORMATS_MAP
from openerp.tools.float_utils import float_compare, float_is_zero

class vsa_tracking_line(osv.osv):
    _name = 'vsa.line'
    _columns = {'vsa_line':fields.many2one('purchase.order','Tracking Line'),
                'name':fields.text('Last Status'),
                'description':fields.text('Description'),
                'date':fields.text("Date"),
                }


class vsa_purchase_order(osv.osv):
    _inherit='purchase.order'
    _description = "Inheriting Purchase Order For VSA"

    def _amount_all(self, cr, uid, ids, field_name, arg, context=None):
        res = {}
        cur_obj=self.pool.get('res.currency')
        line_obj = self.pool['purchase.order.line']
        for order in self.browse(cr, uid, ids, context=context):
            res[order.id] = {
                'amount_untaxed': 0.0,
                'amount_tax': 0.0,
                'amount_total': 0.0,
                'total_weight':0.0,
            }
            val = val1 =val2= 0.0
            cur = order.pricelist_id.currency_id
            for line in order.order_line:
                val1 += line.price_subtotal
                val2 += line.weight_subtotal
                line_price = line_obj._calc_line_base_price(cr, uid, line,
                                                            context=context)
                line_qty = line_obj._calc_line_quantity(cr, uid, line,
                                                        context=context)
                for c in self.pool['account.tax'].compute_all(
                        cr, uid, line.taxes_id, line_price, line_qty,
                        line.product_id, order.partner_id)['taxes']:
                    val += c.get('amount', 0.0)
            res[order.id]['total_weight'] = val2
            res[order.id]['amount_tax']=cur_obj.round(cr, uid, cur, val)
            res[order.id]['amount_untaxed']=cur_obj.round(cr, uid, cur, val1)
            res[order.id]['amount_total']=res[order.id]['amount_untaxed'] + res[order.id]['amount_tax']
        return res

    _columns ={'tracking_no':fields.char(string="Tracking No."),
               'carrier_selection':fields.selection([('ups', 'UPS'),
                                   ('dhl', 'DHL'),
                                   ('fedex', 'FEDEX')],'Carrier'),
               'last_status':fields.text('Last Status',readonly=True),
               'expected_arrival':fields.text('Expected Arrival',readonly=True),
               'last_status_line': fields.one2many('vsa.line','vsa_line', readonly=True),
               'delivered':fields.boolean('Delivered'),
               'total_weight': fields.function(_amount_all, digits_compute=dp.get_precision('Account'),string='Total Weight',store=True, multi="sums", help="The Total Weight",track_visibility='always')
               }

    def cron_for_url_scrapping(self,cr,uid,context=None):
        po_obj = self.pool.get('purchase.order')
        ups_obj=self.pool.get('ups.config')
        ups_ids = ups_obj.search(cr, uid, [], context=None)
        ups_browse = ups_obj.browse(cr, uid, ups_ids, context=context)
        fedex_obj=self.pool.get('fedex.config')
        fedex_ids=fedex_obj.search(cr,uid,[],context=None)
        fedex_browse=fedex_obj.browse(cr, uid, fedex_ids, context=context)
        print fedex_browse

        purchase_ids=po_obj.search(cr,uid,[],context=None)
        print purchase_ids
        for po in purchase_ids:
            print "------------po-------------",po
            po_obj.url_scrapping(cr,uid,[po],ups_browse,fedex_browse,context=context)
        # for po in po_obj.browse(cr, uid, purchase_ids, context=context):
        #     po.url_scrapping()
        return True


    def url_scrapping(self,cr,uid,ids,ups_browse,fedex_browse,context=None):
        print ids[0]
        obj = self.browse(cr, uid, ids[0], context=context)
        print '>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>',obj

        if obj.carrier_selection == 'dhl' and obj.delivered == False:
            try:
                url = "http://www.dhl.co.in/shipmentTracking"
                querystring = {"AWB":obj.tracking_no, "countryCode": "in", "languageCode": "en", "_": "1511447699608"}
                headers = {
                    'cache-control': "no-cache",
                    'postman-token': "cb9efd5e-f6be-248f-cf53-9bb555403121"
                }
                response = requests.request("GET", url, headers=headers, params=querystring)
                print response.text
                data=json.loads(response.text)
                # print'>>>>>>>>>>jsonloads', data
                for result in data['results']:
                    count=0
                    for check in result.get('checkpoints'):
                        count +=1
                        print count
                        result_description=check.get('description')
                        print ">>>",result_description
                        result_time=check.get('time')
                        result_date=check.get('date')
                        result_date=parse(result_date).strftime('%d/%m/%Y')
                        print ">>>", result_date
                        result_location=check.get('location')
                        print ">>>", result_date
                        vsa_line_env=self.pool.get('vsa.line')
                        vsa_id=vsa_line_env.search(cr,uid,[('date','=',result_date+'-'+result_time)],context)
                        if not vsa_id:
                            vals={'name':result_location,
                                  'description':result_description,
                                  'date':result_date+'-'+result_time,
                                  'vsa_line':ids[0]}
                            vsa_line_create=vsa_line_env.create(cr, uid, vals, context)
                            result_edd='NA'
                            if result.get('edd'):
                                result_edd=result.get('edd').get('date')
                                result_edd = parse(result_edd).strftime('%d/%m/%Y')
                            result_signatory=result.get('signature').get('signatory')
                            print '>>>>?>>>>>>',result_signatory
                            if count ==1:
                                write=obj.write({'expected_arrival':result_edd,'last_status':result_description+ " On "+result_date })
                                print '>>>>>>>>>>>>>>>>>>>>>>>>>>>write',write
                            if "Delivered" in result_description:
                                write=obj.write({'delivered':True})

            except Exception:
                _logger.error("NO Records Found for DHL")
                vsa_line_env = self.pool.get('vsa.line')
                vals = {'name': "NOT FOUND",
                        'description': "NOT FOUND",
                        'date': "NOT FOUND",
                        'vsa_line': ids[0]}
                vsa_line_create = vsa_line_env.create(cr, uid, vals, context)



        if obj.carrier_selection =='ups' and obj.delivered == False:
            try:
                print ups_browse.name
                print ups_browse.password
                url_ups = "https://wwwcie.ups.com/rest/Track"

                payload ="""{
                              "Security": {
                                "UsernameToken": {
                                  "Username":""" +ups_browse.name+""",
                                  "Password":"""+ups_browse.password+"""
                                },
                                "UPSServiceAccessToken": {
                                  "AccessLicenseNumber":"""+ups_browse.access_key+"""
                                }
                              },
                              "TrackRequest": {
                                "Request": {
                                  "RequestOption": "15",
                                  "TransactionReference": {
                                    "CustomerContext": "Your Test Case Summary Description"
                                  }
                                },
                                "InquiryNumber":"""+obj.tracking_no+""",
                                "TrackingOption": "02"
                              }
                            }"""
                headers = {
                    'content-type': "application/json",
                    'cache-control': "no-cache",
                    'postman-token': "12a378d9-76ec-08f6-e365-5e56d1a49479"
                }

                response = requests.request("POST", url_ups, data=payload, headers=headers)

                print response.text
                data=json.loads(response.text)
                count =0
                for activity in data['TrackResponse']['Shipment']['Package']['Activity']:
                    count +=1
                    if activity.get('ActivityLocation').get('Address'):
                        city=activity.get('ActivityLocation').get('Address').get('City')
                        print'>>>>>>>>>>>>>>>>>>>>',city
                        description=activity.get("Status").get("Description")
                        print'>>>>>>>>>>>>>>>>>>>>', description
                        date = activity.get("Date")
                        time_api = activity.get("Time")
                        date_time=date+time_api
                        date = parse(date_time).strftime('%d/%m/%Y %H:%M:%S')
                        print'>>>>>>>>>>>>>>>>>>>>', date


                        vsa_line_env = self.pool.get('vsa.line')
                        vsa_id=vsa_line_env.search(cr,uid,[('date','=',date)],context)
                        if not vsa_id:
                            vals={'name':city,
                                  'description':description,
                                  'date':date,
                                  'vsa_line':ids[0]}
                            vsa_line_create=vsa_line_env.create(cr, uid, vals, context)
                            if count ==1:
                                write = obj.write({'expected_arrival': "NA", 'last_status': description +" at "+ city +" on " + date})
                            if "Delivered" in description:
                                write=obj.write({'delivered':True})
            except Exception:
                _logger.error("NO Records Found for UPS")
                vsa_line_env = self.pool.get('vsa.line')
                vals = {'name': "NOT FOUND",
                        'description': "NOT FOUND",
                        'date': "NOT FOUND",
                        'vsa_line': ids[0]}
                vsa_line_create = vsa_line_env.create(cr, uid, vals, context)

        if obj.carrier_selection =='fedex' and obj.delivered == False:
            try:

                CONFIG_OBJ = FedexConfig(key=fedex_browse.name,
                                         password=fedex_browse.password,
                                         account_number=fedex_browse.account_no,
                                         meter_number=fedex_browse.meter_no,
                                       # freight_account_number='xxxxxxxxxxx',
                                         use_test_server=True)

                customer_transaction_id = "*** TrackService Request v10 using Python ***"  # Optional transaction_id
                track = FedexTrackRequest(CONFIG_OBJ, customer_transaction_id=customer_transaction_id)

                # Track by Tracking Number
                track.SelectionDetails.PackageIdentifier.Type = 'TRACKING_NUMBER_OR_DOORTAG'
                track.SelectionDetails.PackageIdentifier.Value = obj.tracking_no

                # FedEx operating company or delete
                del track.SelectionDetails.OperatingCompany
                track.send_request()
                print(track.response)
                data=track.response
                # print '>>>>>>>>>>>>>>>>>>>>>>>>>>EstimatedDeliveryTimestamp',data.CompletedTrackDetails
                for record in data.CompletedTrackDetails:
                    for set in record.TrackDetails:
                        print type(set)

                        # print '>>>>>>>>>>>>>>>>>>>>>>>>>>EstimatedDeliveryTimestamp',time

                        for event in set.Events:
                            timestamp=event.Timestamp
                            timestamp = timestamp.strftime('%d/%m/%Y-%H:%M:%S')
                            print '>>>>>>>>>>>>>>>>>>>>>>>>>>timestamp', timestamp
                            EventDescription=event.EventDescription
                            print '>>>>>>>>>>>>>>>>>>>>>>>>>>EventDescription', EventDescription
                            city='(Address Not Provided)'
                            if 'City' in event.Address:
                                city=event.Address.City
                                print '>>>>>>>>>>>>>>>>>>>>>>>>>>city', city

                            vsa_line_env = self.pool.get('vsa.line')
                            vsa_id = vsa_line_env.search(cr, uid, [('date', '=', timestamp)], context)
                            if not vsa_id:
                                vals = {'name': city ,
                                        'description': EventDescription,
                                        'date': timestamp,
                                        'vsa_line': ids[0]}
                                vsa_line_create = vsa_line_env.create(cr, uid, vals, context)
                                split_time=timestamp.split('-')
                                write=obj.write({'expected_arrival': "NA",'last_status': EventDescription + " at " + city + " on " + split_time[0]})
                                if "Delivered" in EventDescription:
                                    write = obj.write({'delivered': True})
                                cr.commit()
                        if 'EstimatedDeliveryTimestamp' in set:
                            time = set.EstimatedDeliveryTimestamp
                            time = time.strftime('%d/%m/%Y')
                            write = obj.write({'expected_arrival': time})
            except Exception:
                _logger.error("NO Records Found for Fedex")
                vsa_line_env = self.pool.get('vsa.line')
                vals = {'name': "NOT FOUND",
                        'description': "Server is UnReachable or This Order is Arrived",
                        'date': "NOT FOUND",
                        'vsa_line': ids[0]}
                write = obj.write({'expected_arrival': "Server is UnReachable or This Order is Arrived"})
                vsa_line_create = vsa_line_env.create(cr, uid, vals, context)

        return True




class vsa_purchase_order(osv.osv):
    _inherit='purchase.order.line'

    def _weight_line(self, cr, uid, ids, prop, arg, context=None):
        res = {}
        for line in self.browse(cr, uid, ids, context=context):
            line_price = line.product_weight
            line_qty = self._calc_line_quantity(cr, uid, line,
                                                context=context)
            res[line.id]=line_price * line_qty
        return res

    _columns = {'product_weight': fields.float(string="Weight"),
                'weight_subtotal': fields.function(_weight_line, string='Subtotal Weight',digits_compute=dp.get_precision('Account'))
                }

    def onchange_product_id(self, cr, uid, ids, pricelist_id, product_id, qty, uom_id,
            partner_id, date_order=False, fiscal_position_id=False, date_planned=False,
            name=False, price_unit=False, state='draft', context=None):
        """
        onchange handler of product_id.
        """
        if context is None:
            context = {}

        res = {'value': {'price_unit': price_unit or 0.0, 'name': name or '', 'product_uom' : uom_id or False}}
        if not product_id:
            if not uom_id:
                uom_id = self.default_get(cr, uid, ['product_uom'], context=context).get('product_uom', False)
                res['value']['product_uom'] = uom_id
            return res

        product_product = self.pool.get('product.product')
        product_uom = self.pool.get('product.uom')
        res_partner = self.pool.get('res.partner')
        product_pricelist = self.pool.get('product.pricelist')
        account_fiscal_position = self.pool.get('account.fiscal.position')
        account_tax = self.pool.get('account.tax')

        # - check for the presence of partner_id and pricelist_id
        #if not partner_id:
        #    raise osv.except_osv(_('No Partner!'), _('Select a partner in purchase order to choose a product.'))
        #if not pricelist_id:
        #    raise osv.except_osv(_('No Pricelist !'), _('Select a price list in the purchase order form before choosing a product.'))

        # - determine name and notes based on product in partner lang.
        context_partner = context.copy()
        if partner_id:
            lang = res_partner.browse(cr, uid, partner_id).lang
            context_partner.update( {'lang': lang, 'partner_id': partner_id} )
        product = product_product.browse(cr, uid, product_id, context=context_partner)
        #call name_get() with partner in the context to eventually match name and description in the seller_ids field
        if not name or not uom_id:
            # The 'or not uom_id' part of the above condition can be removed in master. See commit message of the rev. introducing this line.
            dummy, name = product_product.name_get(cr, uid, product_id, context=context_partner)[0]
            if product.description_purchase:
                name += '\n' + product.description_purchase
            res['value'].update({'name': name})

        # - set a domain on product_uom
        res['domain'] = {'product_uom': [('category_id','=',product.uom_id.category_id.id)]}

        # - check that uom and product uom belong to the same category
        product_uom_po_id = product.uom_po_id.id
        if not uom_id:
            uom_id = product_uom_po_id

        if product.uom_id.category_id.id != product_uom.browse(cr, uid, uom_id, context=context).category_id.id:
            if context.get('purchase_uom_check') and self._check_product_uom_group(cr, uid, context=context):
                res['warning'] = {'title': _('Warning!'), 'message': _('Selected Unit of Measure does not belong to the same category as the product Unit of Measure.')}
            uom_id = product_uom_po_id

        res['value'].update({'product_uom': uom_id})
        res['value'].update({'product_weight': product.weight})
        # - determine product_qty and date_planned based on seller info
        if not date_order:
            date_order = fields.datetime.now()


        supplierinfo = False
        precision = self.pool.get('decimal.precision').precision_get(cr, uid, 'Product Unit of Measure')
        for supplier in product.seller_ids:
            if partner_id and (supplier.name.id == partner_id):
                supplierinfo = supplier
                if supplierinfo.product_uom.id != uom_id:
                    res['warning'] = {'title': _('Warning!'), 'message': _('The selected supplier only sells this product by %s') % supplierinfo.product_uom.name }
                min_qty = product_uom._compute_qty(cr, uid, supplierinfo.product_uom.id, supplierinfo.min_qty, to_uom_id=uom_id)
                if float_compare(min_qty , qty, precision_digits=precision) == 1: # If the supplier quantity is greater than entered from user, set minimal.
                    if qty:
                        res['warning'] = {'title': _('Warning!'), 'message': _('The selected supplier has a minimal quantity set to %s %s, you should not purchase less.') % (supplierinfo.min_qty, supplierinfo.product_uom.name)}
                    qty = min_qty
        dt = self._get_date_planned(cr, uid, supplierinfo, date_order, context=context).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        qty = qty or 1.0
        res['value'].update({'date_planned': date_planned or dt})
        if qty:
            res['value'].update({'product_qty': qty})

        price = price_unit
        if price_unit is False or price_unit is None:
            # - determine price_unit and taxes_id
            if pricelist_id:
                date_order_str = datetime.strptime(date_order, DEFAULT_SERVER_DATETIME_FORMAT).strftime(DEFAULT_SERVER_DATE_FORMAT)
                price = product_pricelist.price_get(cr, uid, [pricelist_id],
                        product.id, qty or 1.0, partner_id or False, {'uom': uom_id, 'date': date_order_str})[pricelist_id]
            else:
                price = product.standard_price

        if uid == SUPERUSER_ID:
            company_id = self.pool['res.users'].browse(cr, uid, [uid]).company_id.id
            taxes = product.supplier_taxes_id.filtered(lambda r: r.company_id.id == company_id)
        else:
            taxes = product.supplier_taxes_id
        fpos = fiscal_position_id and account_fiscal_position.browse(cr, uid, fiscal_position_id, context=context) or False
        taxes_ids = account_fiscal_position.map_tax(cr, uid, fpos, taxes, context=context)
        price = self.pool['account.tax']._fix_tax_included_price(cr, uid, price, product.supplier_taxes_id, taxes_ids)
        res['value'].update({'price_unit': price, 'taxes_id': taxes_ids})

        return res





class ups_config(osv.osv):
    _name = 'ups.config'
    _columns = {'name':fields.char("UserName"),
                'password':fields.char('Password'),
                'access_key':fields.char("License Key")
                }
class fedex_config(osv.osv):
    _name = 'fedex.config'
    _columns = {'name':fields.char('KEY'),
                'account_no':fields.char('Account NO'),
                'meter_no':fields.char('Meter No'),
                'password':fields.char('Password')}


class button_wizard(osv.TransientModel):
    _name='vsa.button.wizard'

    def button_call(self,cr,uid,ids,context=None):
        po_obj = self.pool.get('purchase.order')
        po_obj.cron_for_url_scrapping(cr,uid,context=None)
        return True





