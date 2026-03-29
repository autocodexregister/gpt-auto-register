"""
Sub2Api 集成模块 - 账号健康检测和批量推送
依赖: pip install curl_cffi
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from curl_cffi import requests as curl_requests
from datetime import datetime, timezone, timedelta


class Sub2ApiManager:
    """Sub2Api 管理器 - 检测健康度和推送账号"""

    def __init__(self, base_url: str, admin_key: str):
        self.base_url = base_url.rstrip("/")
        self.admin_key = admin_key
        self.session = curl_requests.Session(impersonate="chrome131")
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """发送请求到 Sub2Api"""
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.admin_key}"

        try:
            resp = self.session.request(method, url, headers=headers, timeout=30, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise Exception(f"Sub2Api 请求失败: {e}")

    def get_accounts(self, platform: str = "openai", page: int = 1, page_size: int = 100) -> dict:
        """获取账号列表"""
        return self._request(
            "GET",
            "/api/v1/admin/accounts",
            params={"platform": platform, "page": page, "page_size": page_size}
        )

    def check_account_health(self, email: str, access_token: str) -> bool:
        """检查单个账号健康度"""
        try:
            # 尝试使用 token 访问 OpenAI API
            resp = curl_requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1
                },
                timeout=15
            )
            # 200 或 401 都算正常（账号存在）
            return resp.status_code in [200, 401, 403, 429]
        except Exception:
            return False

    def get_health_stats(self) -> Dict:
        """获取账号池健康统计"""
        print("[Sub2Api] 正在检测账号池健康度...")
        stats = {
            "total": 0,
            "healthy": 0,
            "unhealthy": 0,
            "unknown": 0,
            "accounts": []
        }

        try:
            # 获取账号总数
            result = self.get_accounts(page_size=1)
            total = result.get("data", {}).get("total", 0)
            stats["total"] = total

            if total == 0:
                print("[Sub2Api] 账号池为空")
                return stats

            # 分页获取所有账号
            page_size = 50
            pages = (total + page_size - 1) // page_size

            for page in range(1, pages + 1):
                result = self.get_accounts(page=page, page_size=page_size)
                accounts = result.get("data", {}).get("items", [])

                for acc in accounts:
                    email = acc.get("email", "")
                    access_token = acc.get("access_token", "")
                    if not email or not access_token:
                        stats["unknown"] += 1
                        continue

                    # 检查健康度
                    is_healthy = self.check_account_health(email, access_token)
                    status = "healthy" if is_healthy else "unhealthy"

                    if is_healthy:
                        stats["healthy"] += 1
                    else:
                        stats["unhealthy"] += 1

                    stats["accounts"].append({
                        "id": acc.get("id"),
                        "email": email,
                        "status": status,
                        "created_at": acc.get("created_at"),
                    })

                    print(f"[Sub2Api] {email}: {status}")

                # 避免请求过快
                time.sleep(0.5)

        except Exception as e:
            print(f"[Sub2Api] 健康检测失败: {e}")

        return stats

    def upload_account(self, email: str, password: str, access_token: str = None,
                       refresh_token: str = None, group_ids: List[int] = None) -> bool:
        """上传单个账号到 Sub2Api"""
        try:
            payload = {
                "email": email,
                "password": password,
                "platform": "openai",
                "type": "oauth",
            }

            if access_token:
                payload["access_token"] = access_token
            if refresh_token:
                payload["refresh_token"] = refresh_token
            if group_ids:
                payload["group_ids"] = group_ids

            self._request("POST", "/api/v1/admin/accounts", json=payload)
            print(f"[Sub2Api] 上传成功: {email}")
            return True
        except Exception as e:
            print(f"[Sub2Api] 上传失败 {email}: {e}")
            return False

    def batch_upload(self, accounts: List[Dict], group_ids: List[int] = None) -> Dict:
        """批量上传账号"""
        results = {"success": 0, "failed": 0, "accounts": []}

        for acc in accounts:
            email = acc.get("email", "")
            password = acc.get("password", "")
            access_token = acc.get("access_token", "")
            refresh_token = acc.get("refresh_token", "")

            if not email or not password:
                results["failed"] += 1
                continue

            success = self.upload_account(
                email, password, access_token, refresh_token, group_ids
            )

            if success:
                results["success"] += 1
                results["accounts"].append(email)
            else:
                results["failed"] += 1

            # 避免请求过快
            time.sleep(0.3)

        return results


def load_registered_accounts(file_path: str) -> List[Dict]:
    """从注册文件加载账号"""
    accounts = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # 格式: email----password----oauth=ok
                parts = line.split("----")
                if len(parts) >= 2:
                    email = parts[0].strip()
                    password = parts[1].strip()
                    accounts.append({"email": email, "password": password})
    except Exception as e:
        print(f"[Error] 读取注册文件失败: {e}")
    return accounts


def load_token_json(email: str, token_dir: str = "codex_tokens") -> Dict:
    """加载 token JSON 文件"""
    token_path = Path(token_dir) / f"{email}.json"
    try:
        if token_path.exists():
            with open(token_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Sub2Api 账号管理工具")
    parser.add_argument("action", choices=["check", "upload"], help="操作类型")
    parser.add_argument("--base-url", default=os.getenv("SUB2API_BASE_URL", "https://sub2api.xspace.icu"))
    parser.add_argument("--admin-key", default=os.getenv("SUB2API_ADMIN_KEY", ""))
    parser.add_argument("--file", default="registered_accounts.txt", help="注册账号文件")
    parser.add_argument("--token-dir", default="codex_tokens", help="Token 目录")
    parser.add_argument("--group-ids", type=int, nargs="+", default=[2], help="Sub2Api 分组 ID")
    parser.add_argument("--min-healthy", type=int, default=2000, help="最小健康账号数")
    parser.add_argument("--output", help="输出检测结果到文件")

    args = parser.parse_args()

    if not args.admin_key:
        print("[Error] SUB2API_ADMIN_KEY 未设置")
        return 1

    manager = Sub2ApiManager(args.base_url, args.admin_key)

    if args.action == "check":
        stats = manager.get_health_stats()

        print(f"\n[Sub2Api] 健康检测完成:")
        print(f"  总数: {stats['total']}")
        print(f"  健康: {stats['healthy']}")
        print(f"  不健康: {stats['unhealthy']}")
        print(f"  未知: {stats['unknown']}")

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(stats, f, indent=2, ensure_ascii=False)
            print(f"\n[Sub2Api] 结果已保存到: {args.output}")

        # 返回是否需要补充账号
        return 0 if stats["healthy"] >= args.min_healthy else 100

    elif args.action == "upload":
        accounts = load_registered_accounts(args.file)

        if not accounts:
            print("[Sub2Api] 没有需要上传的账号")
            return 0

        # 加载 token
        for acc in accounts:
            token_data = load_token_json(acc["email"], args.token_dir)
            acc["access_token"] = token_data.get("access_token", "")
            acc["refresh_token"] = token_data.get("refresh_token", "")

        results = manager.batch_upload(accounts, args.group_ids)

        print(f"\n[Sub2Api] 批量上传完成:")
        print(f"  成功: {results['success']}")
        print(f"  失败: {results['failed']}")

        return 0


if __name__ == "__main__":
    raise SystemExit(main())
