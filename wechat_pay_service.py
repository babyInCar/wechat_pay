"""
@date:2020/8/16 10:50 am
@author: gaos
@file: wechat_pay_service.py
@target: 支付的服务
@log:[2020/8/16 10:50 am][add:] new
"""
from common import strings
from decimal import Decimal
from common.system.config import BaseConfig
from common.config.test import CMB_PRIVATE_KEY
from common.mall.bean import OrderVariable as code
from common.exception.business_exception import BusinessException
from common.status import HTTP_200_OK, HTTP_500_INTERNAL_SERVER_ERROR
from common.tools.func import send_failed, send_success2
from common.core.DBModel import DBModel
from common.mall.service import sign_generate_service
from common.mall.service import order_service
from random import Random
import requests
import json
import hashlib
import time
import datetime
import decimal
from copy import copy
import random
import uuid
import os
from dicttoxml import dicttoxml
import xmltodict
# import base64


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

def order_wechat_pay(db_model, pay_config: dict= {}):
    """
    商城支付接口
    @params: version
    @params: encoding
    @params: merId
    @params: sign
    @params: signMethod
    @params: orderId
    @params: subAppId
    @params: tradeType
    @params: tradeScene
    @params: userId
    @params: body
    @params:notifyUrl
    @params:txnAmt (单位为分)
    @params:spbillCreateIp
    @params: openId
    @params: subOpenId

    @(optional)params: deviceInfo
    @(optional)params: limitPay
    @(optional)params: currencyCode
    @(optional)params: sceneInfo
    @(optional)params: identity
    @(optional)params: policyNo
    @(optional)params: region
    @(optional)params: goodsDetail
    @(optional)params: goodsTag
    @(optional)params: attach
    @(optional)params: mchReserver
    @(optional)params: payValidTime
    """

    if not pay_config:
        raise BusinessException(code.CODE_FAIL, strings.ORDER_PARAMS_NONE)

    txn_amt = pay_config.get('txnAmt')
    if isinstance(txn_amt, decimal.Decimal):
        txn_amt = str(int(txn_amt * 100))
    # 调用微信支付接口
    env = pay_config.get('env')
    os.environ['ENV'] = env
    nonce_str = random_str()
    wechat_dict = BaseConfig.get('WECHAT_PARAM')
    pay_dict = {
        'appid': BaseConfig.get('WXCONFIG').get('program').get('appid'),
        'mch_id': wechat_dict.get('pay_mer_id'),
        'nonce_str': nonce_str,
        'body': pay_config.get('body'),
        'out_trade_no': pay_config.get('orderId'),
        'total_fee': str(txn_amt),
        'spbill_create_ip': pay_config.get('spbillCreateIp', ''),
        'notify_url': wechat_dict.get('pay_notify_url', ''),
        'trade_type': pay_config.get('tradeType', 'JSAPI'),
        'openid': pay_config.get('subOpenId', '')
    }

    # sign_rsa = sign_generate_service.SignRSA(**pay_dict)
    # sign_info = sign_rsa.sign_with_wechat_key()
    sign_info = generate_sign(pay_dict)
    pay_dict['sign'] = sign_info
    print(pay_dict)
    pay_str = bytes.decode(dicttoxml(pay_dict, root=False, attr_type=False))
    pay_xml_str = '<xml>' + pay_str + '</xml>'
    post_url = wechat_dict.get('pay_url')

    headers = {'Content-Type': 'application/xml'}
    # 把参数转义成xml
    try:
        print("订单:{}向微信发起付款请求,请求内容为:{}".format(pay_config.get('orderId', ''), pay_xml_str))
        res = requests.post(post_url, pay_xml_str.encode('utf-8'), headers=headers)
        print(res.content)
    except BusinessException as ex:
        raise BusinessException(ex.code, ex.msg)

    if str(res.status_code) == '200':

        res_content = res.content
        res_str = xmltodict.parse(res_content, encoding='utf-8')
        # res_str = res_content.decode('utf-8')

        resp_dict = json.loads(json.dumps(res_str))
        if resp_dict.get('respCode') == 'FAIL':
            err_code = resp_dict.get('errCode')
            resp_msg = resp_dict.get('respMsg')
            raise BusinessException(err_code, resp_msg)
        if resp_dict['xml']['return_code'] == 'SUCCESS':
            prepay_id = resp_dict['xml']['prepay_id']
            # 时间戳
            timeStamp = str(int(time.time()))
            # 5. 五个参数
            data = {
                "appId": BaseConfig.get('WXCONFIG').get('program').get('appid'),
                "nonceStr": nonce_str,
                "package": "prepay_id=" + prepay_id,
                "signType": 'MD5',
                "timeStamp": timeStamp,
            }
            # 6. paySign签名
            paySign = generate_sign(data)
            data["paySign"] = paySign  # 加入签名
            print(data)
            # 7. 传给前端的签名后的参数
            return json.dumps(data)

def generate_sign(raw):
    '''生成签名'''
    raw = [(k, str(raw[k]) if isinstance(raw[k], int) else raw[k])
           for k in sorted(raw.keys())]
    s = "&".join("=".join(kv) for kv in raw if kv[1])
    mch_key = '*****************************'
    s += "&key={0}".format(mch_key)
    return hashlib.md5(s.encode("utf-8")).hexdigest().upper()


if __name__ == '__main__':
    pay_config = {'env': 'test', 'orderId': '61600642472417042432', 'txnAmt': Decimal('1.00'), 'body': 'test', 'subOpenId': 'opO3l5f05CHiTUumkk2SNCqdVSeU', 'spbillCreateIp': '42.245.232.57'}

    import os
    os.environ['ENV'] = 'dev'
    with DBModel() as db:

        # params = {'env': 'prod', 'orderId': '61600642472417042432', 'txnAmt': Decimal('140.00'), 'body': 'U客官方体验商城-进口零食', 'subOpenId': 'opO3l5eWrFfJ8VC86g03ezL4LUCI', 'spbillCreateIp': '42.245.232.57'}

        order_wechat_pay(db, pay_config)



