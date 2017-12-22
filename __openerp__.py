# -*- encoding: utf-8 -*-
##############################################################################
#Copyright (c) 2017777777 - Present Teckzilla Software Solutions Pvt. Ltd. All Rights Reserved
#    Author: [Teckzilla Software Solutions]  <[sales@teckzilla.net]>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    A copy of the GNU General Public License is available at:
#    <http://www.gnu.org/licenses/gpl.html>.
#
##############################################################################

{
    "name" : "VSA Tradee",
    "version" : "1.1",
    "depends" : ["base","product","sale","purchase"],
    "author" : "TeckZilla",
    "description": """
        For UPS,FEDEX,DHL tracking
    """,
    "website" : "www.teckzilla.net",
    'images': [],
    "category" : "Purchase",
    'summary': 'Purchase Order',
    "demo" : [],
	'currency': 'INR',
    "data" : [
            "views/purchase_order.xml",
            "views/ups_fedex_config.xml",
            "views/fedex_config.xml",
            # "views/cron.xml",
    ],
    'auto_install': False,
    "installable": True,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:


