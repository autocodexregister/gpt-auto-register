import os
from curl_cffi import requests as curl_requests

def test_sub2api():
    print("\n=== 测试 Sub2Api API ===")

    base_url = "https://sub2api.xspace.icu/api/v1/admin/accounts"

    # 测试两种格式的 key
    admin_key_without_prefix = "59f155ec4cae2b02ebaa837d436b51b8e13e014015a3a66c5554bbddd7cf058f"
    admin_key_with_prefix = f"admin-{admin_key_without_prefix}"

    headers_without = {
        "Authorization": f"Bearer {admin_key_without_prefix}",
        "Accept": "application/json"
    }

    headers_with = {
        "Authorization": admin_key_with_prefix,
        "Accept": "application/json"
    }

    print(f"Testing without prefix: {admin_key_without_prefix[:200]}")

    try:
        resp = curl_requests.get(
            base_url,
            headers=headers_without,
            timeout=10
        )
        print(f"Response status: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")
    except Exception as e:
        print(f"Error without prefix: {e}")

    print(f"\nTesting with prefix: {admin_key_with_prefix[:200]}")

    try:
        resp = curl_requests.get(
            base_url,
            headers=headers_with,
            timeout=10
        )
        print(f"Response status: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")
    except Exception as e:
        print(f"Error with prefix: {e}")

if __name__ == "__main__":
    test_sub2api()
