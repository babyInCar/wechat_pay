"""
@date:2020/8/16 19:49 pm
@author:gaos
@file: wechat_refund_service.py
@target:微信退款
@log:[2020/8/16 19:49 pm][add:] new
"""
from common import strings
from common.mall.bean import OrderVariable as code
from common.system.config import BaseConfig
from common.exception.business_exception import BusinessException
import requests
from common.mall.service import sign_generate_service
import json
from common.core.DBModel import DBModel
import decimal
from decimal import Decimal
import os
import base64
from random import Random
import xmltodict
from dicttoxml import dicttoxml

from copy import copy

def random_str():
    """
    生成随机字符串
    :param randomlength: 字符串长度
    :return:
    """
    strs = ''
    chars = 'AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz0123456789'
    length = len(chars) - 1
    random = Random()
    for i in range(0, 30):
        strs += chars[random.randint(0, length)]
    return strs

def order_wx_refund(db_model, env, orderDict:dict={}):
    """
    商城退款接口
    @params: appid
    @params: mch_id
    @params: nonce_str
    @params: sign
    @params: out_trade_no
    @params: out_refund_no
    @params: total_fee(单位为分)
    @params: refund_fee(单位为分)

    @(optional)params: sign_type
    @(optional)params: notify_url(退款回调地址)
    @(optional)params: mchReserved(保留域)
    @(optional)params: refund_desc()
    """

    if not orderDict:
        raise BusinessException(code.CODE_FAIL, strings.ORDER_PARAMS_NONE)

    # 调用微信退款的接口
    # env = pay_config.get('env')
    os.environ['ENV'] = env
    nonce_str = random_str()
    wechat_dict = BaseConfig.get('WECHAT_PARAM')
    mch_reserved_dict = json.loads(orderDict.get('mchReserved'))
    if 'after_sales_no' in mch_reserved_dict.keys():
        as_no = mch_reserved_dict.get('after_sales_no')
        order_dict = db_model.table('mall_after_sales').select(['order_no']).where(
            ['after_sales_no={}'.format(as_no)]).get_one()
        order_id = order_dict.get('order_no')
    else:
        order_id = mch_reserved_dict.get('order_no', None)
    if order_id is None:
        msg = 'order_no为空'
        raise BusinessException(code.CODE_FAIL, msg)
    mch_rsa = sign_generate_service.SignRSA(**mch_reserved_dict)
    ordered_item = mch_rsa.get_ordered_data(mch_reserved_dict)
    mch_reserved_str = mch_rsa.encode_for_mch_reserved(ordered_item)
    # 对保留域进行Base64 加密
    mch_encode_str = base64.b64encode(bytes(mch_reserved_str, encoding="utf8"))
    notify_url = wechat_dict.get('refund_notify_url') + '/' + str(mch_encode_str, encoding="utf8")

    refund_amt = orderDict.get('refundAmt', 0)
    if isinstance(refund_amt, decimal.Decimal):
        refund_amt = str(int(refund_amt * 100))
    txn_amt = orderDict.get('txnAmt')
    if isinstance(txn_amt, decimal.Decimal):
        txn_amt = str(int(txn_amt * 100))

    refund_dict = {
        'appid': BaseConfig.get('WXCONFIG').get('program').get('appid'),
        'mch_id': wechat_dict.get('pay_mer_id'),
        'nonce_str': nonce_str,
        'out_trade_no': order_id,
        'out_refund_no': orderDict.get('out_refund_no', ''),
        'total_fee': str(txn_amt),
        'refund_fee': str(refund_amt),
        'refund_desc': orderDict.get('refund_desc'),
        'notify_url': notify_url,
    }

    sign_rsa = sign_generate_service.SignRSA(**refund_dict)
    refund_dict['sign'] = sign_rsa.generate_wechat_sign()

    print("向微信发起退款申请，退款参数为:{}".format(refund_dict))
    refund_str = bytes.decode(dicttoxml(refund_dict, root=False, attr_type=False))
    refund_xml_str = '<xml>' + refund_str + '</xml>'
    post_url = wechat_dict.get('refund_url')

    headers = {'Content-Type': 'application/xml'}
    # 把参数转义成xml
    try:

        current_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        ssh_keys_path = os.path.join(current_path, "config/")
        print(ssh_keys_path)
        api_client_cert = os.path.join(ssh_keys_path, 'apiclient_cert.pem')
        api_client_key = os.path.join(ssh_keys_path, 'apiclient_key.pem')
        res = requests.post(post_url, refund_xml_str.encode('utf-8'), headers=headers, cert=(api_client_cert, api_client_key), verify=True)
        print(res.content)
    except BusinessException as ex:
        raise BusinessException(ex.code, ex.msg)

    if str(res.status_code) == '200':

        res_content = res.content
        res_str = xmltodict.parse(res_content, encoding='utf-8')
        resp_dict = json.loads(json.dumps(res_str))
        if resp_dict.get('xml').get('return_code') == 'FAIL':
            err_code = resp_dict.get('err_code')
            resp_msg = resp_dict.get('return_msg')
            raise BusinessException(err_code, resp_msg)
        if resp_dict['xml']['return_code'] == 'SUCCESS':
            refund_data_dict = {
                                # 'refundState': resp_dict.get('result_code', ''),
                                'result_code': resp_dict.get('xml').get('return_code'),
                                'refund_id': resp_dict.get('xml').get('refund_id')
                                }
            # refund_data_str = cmb_refund_data.get('refundState', '')
            refund_data_str = json.dumps(refund_data_dict)

    print("refund_data_str====={}".format(refund_data_str))
    return refund_data_str


if __name__ == '__main__':

    import os
    os.environ['ENV'] = 'dev'
    env = 'dev'
    with DBModel() as db:
        params = {
            "out_refund_no": "900120191227174141827",
            "txnAmt": Decimal(1.20),
            "refundAmt": Decimal(1.20),
            "refundReason": "api refund test",
            "refund_desc": '测试',
            "mchReserved": json.dumps({
                "act": 10,
                "order_no": '61600983567864832000',
                "reason": '测试'
            })
        }

        order_wx_refund(db, env, params)
