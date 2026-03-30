import os
import base64
import json
from curl_cffi import requests as curl_requests

# 测试两种格式
admin_key_with_prefix = 'admin-59f155ec4cae2b02ebaa837d436b51b8e13e014015a3a66c5554bbddd7cf058f'
admin_key_without_prefix = '59f155ec4cae2b02ebaa837d436b51b8e13e014015a3a66c5554bbddd7cf058f'

sub2api_url = 'https://sub2api.xspace.icu/api/v1/admin/accounts'

print(f'Testing admin key with prefix: {admin_key_with_prefix}')
try:
    resp = curl_requests.get(sub2api_url, headers={'Authorization': f'Bearer {admin_key_with_prefix}'}, timeout=10)
    print(f'Response: {resp.status_code} - {resp.text[:200]}')
except Exception as e:
    print(f'Error: {e}')

print(f'\nTesting admin key without prefix: {admin_key_without_prefix}')
try:
    resp = curl_requests.get(sub2api_url, headers={'Authorization': f'Bearer {admin_key_without_prefix}'}, timeout=10)
    print(f'Response: {resp.status_code} - {resp.text[:200]}')
except Exception as e:
    print(f'Error: {e}')
