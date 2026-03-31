"""
统一账号同步管理器 - 同时支持 CPA 和 Sub2Api 平台
依赖: pip install curl_cffi
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from curl_cffi import requests as curl_requests


def _load_config() -> dict:
    """从 config.json 加载配置"""
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


class AccountSyncManager:
    """统一账号同步管理器"""

    def __init__(self):
        self.session = curl_requests.Session(impersonate="chrome131")
        config = _load_config()

        # CPA 配置 (环境变量优先，config.json 作为备选)
        self.cpa_base_url = os.getenv("CPA_BASE_URL") or config.get("cpa_base_url", "https://cpa.xspace.icu")
        self.cpa_management_key = os.getenv("CPA_MANAGEMENT_KEY") or config.get("cpa_management_key", "")

        # Sub2Api 配置 (环境变量优先，config.json 作为备选)
        self.sub2api_base_url = os.getenv("SUB2API_BASE_URL") or config.get("sub2api_base_url", "https://sub2api.xspace.icu")
        # 支持三种认证方式:
        # 1. SUB2API_BEARER / SUB2API_ADMIN_KEY - 静态 Bearer token
        # 2. SUB2API_EMAIL + SUB2API_PASSWORD - 动态登录获取 token
        self.sub2api_bearer = os.getenv("SUB2API_BEARER") or os.getenv("SUB2API_ADMIN_KEY") or config.get("sub2api_bearer", "")
        self.sub2api_email = os.getenv("SUB2API_EMAIL") or config.get("sub2api_email", "")
        self.sub2api_password = os.getenv("SUB2API_PASSWORD") or config.get("sub2api_password", "")
        self.sub2api_token = ""  # 动态获取的 JWT token
        group_ids_str = os.getenv("SUB2API_GROUP_IDS", "")
        if group_ids_str:
            self.sub2api_group_ids = [int(x) for x in group_ids_str.split(",") if x.strip()]
        else:
            self.sub2api_group_ids = config.get("sub2api_group_ids", [2])

        # 配置是否启用
        self.enable_cpa = bool(self.cpa_management_key)
        self.enable_sub2api = bool(self.sub2api_bearer) or (bool(self.sub2api_email) and bool(self.sub2api_password))

        # 调试信息
        if self.sub2api_bearer:
            print(f"[Sync] Sub2Api 配置: {self.sub2api_base_url} | Key: {self.sub2api_bearer[:15]}...")
        elif self.sub2api_email:
            print(f"[Sync] Sub2Api 配置: {self.sub2api_base_url} | Email: {self.sub2api_email}")
        else:
            print("[Sync] Sub2Api 未配置或 Key 为空")

    def _print(self, msg: str):
        print(f"[Sync] {msg}")

    # ==================== Sub2Api 认证 ====================

    def _sub2api_login(self) -> Optional[str]:
        """使用邮箱密码登录获取 JWT token"""
        if not self.sub2api_email or not self.sub2api_password:
            return None
        try:
            login_url = f"{self.sub2api_base_url.rstrip('/')}/api/v1/auth/login"
            resp = self.session.post(
                login_url,
                json={"email": self.sub2api_email, "password": self.sub2api_password},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("data", {}).get("access_token", "")
                if token:
                    self._print(f"Sub2Api 登录成功，获取到 token")
                    return token
            self._print(f"Sub2Api 登录失败: {resp.status_code} - {resp.text[:100]}")
            return None
        except Exception as e:
            self._print(f"Sub2Api 登录异常: {e}")
            return None

    def _get_sub2api_token(self) -> Optional[str]:
        """获取 Sub2Api 认证 token (优先使用静态 Bearer，否则动态登录)"""
        # 优先使用静态 Bearer token
        if self.sub2api_bearer:
            return self.sub2api_bearer
        # 动态登录获取 token
        if self.sub2api_token:
            return self.sub2api_token
        if self.sub2api_email and self.sub2api_password:
            self.sub2api_token = self._sub2api_login()
            return self.sub2api_token
        return None

    def _get_sub2api_headers(self) -> Dict:
        """获取 Sub2Api 请求头"""
        token = self._get_sub2api_token()
        if token:
            return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        return {}

    # ==================== CPA 相关 ====================

    def upload_to_cpa(self, token_path: str) -> bool:
        """上传 token JSON 到 CPA"""
        if not self.enable_cpa:
            self._print("CPA 未配置，跳过上传")
            return False

        if not Path(token_path).exists():
            self._print(f"CPA 文件不存在: {token_path}")
            return False

        try:
            from curl_cffi import CurlMime

            upload_url = f"{self.cpa_base_url.rstrip('/')}/v0/management/auth-files"

            mp = CurlMime()
            mp.addpart(
                name="file",
                content_type="application/json",
                filename=Path(token_path).name,
                local_path=token_path,
            )

            resp = self.session.post(
                upload_url,
                multipart=mp,
                headers={"Authorization": f"Bearer {self.cpa_management_key}"},
                verify=False,
                timeout=30
            )

            if resp.status_code == 200:
                self._print(f"CPA 上传成功: {Path(token_path).name}")
                return True
            else:
                self._print(f"CPA 上传失败: {resp.status_code}")
                return False
        except Exception as e:
            self._print(f"CPA 上传异常: {e}")
            return False
        finally:
            if 'mp' in locals():
                mp.close()

    # ==================== Sub2Api 相关 ====================

    def upload_to_sub2api(self, email: str, password: str, access_token: str = None,
                          refresh_token: str = None) -> bool:
        """上传账号到 Sub2Api"""
        if not self.enable_sub2api:
            self._print("Sub2Api 未配置，跳过上传")
            return False

        try:
            url = f"{self.sub2api_base_url.rstrip('/')}/api/v1/admin/accounts"

            # Sub2Api API 格式: name + credentials 对象
            credentials = {}
            if access_token:
                credentials["access_token"] = access_token
            if refresh_token:
                credentials["refresh_token"] = refresh_token

            payload = {
                "name": email,  # Sub2Api 使用 name 字段
                "platform": "openai",
                "type": "oauth",
                "credentials": credentials if credentials else None,
            }

            # 移除空值
            payload = {k: v for k, v in payload.items() if v is not None}

            if self.sub2api_group_ids:
                payload["group_ids"] = self.sub2api_group_ids

            resp = self.session.post(
                url,
                json=payload,
                headers=self._get_sub2api_headers(),
                timeout=30
            )

            if resp.status_code in [200, 201]:
                self._print(f"Sub2Api 上传成功: {email}")
                return True
            else:
                # 添加详细错误信息
                try:
                    error_body = resp.text[:200]
                except Exception:
                    error_body = "无法读取响应"
                self._print(f"Sub2Api 上传失败: {resp.status_code} - {error_body}")
                self._print(f"  URL: {url}")
                return False
        except Exception as e:
            self._print(f"Sub2Api 上传异常: {e}")
            return False

    # ==================== 统一同步 ====================

    def sync_account(self, email: str, password: str, token_path: str = None) -> Dict:
        """同步单个账号到所有平台"""
        results = {"email": email, "cpa": False, "sub2api": False}

        # 读取 token 文件
        access_token = ""
        refresh_token = ""
        if token_path and Path(token_path).exists():
            try:
                with open(token_path, "r", encoding="utf-8") as f:
                    token_data = json.load(f)
                access_token = token_data.get("access_token", "")
                refresh_token = token_data.get("refresh_token", "")
            except Exception:
                pass

        # 同步到 CPA
        if self.enable_cpa and token_path:
            results["cpa"] = self.upload_to_cpa(token_path)
            time.sleep(0.2)

        # 同步到 Sub2Api
        if self.enable_sub2api and access_token:
            results["sub2api"] = self.upload_to_sub2api(
                email, password, access_token, refresh_token
            )
            time.sleep(0.2)

        return results

    def sync_all_tokens(self, token_dir: str = "codex_tokens",
                        accounts_file: str = "registered_accounts.txt") -> Dict:
        """批量同步所有账号"""
        results = {
            "total": 0,
            "cpa_success": 0,
            "cpa_failed": 0,
            "sub2api_success": 0,
            "sub2api_failed": 0,
            "accounts": []
        }

        # 读取注册账号文件
        accounts = {}
        if Path(accounts_file).exists():
            with open(accounts_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("----")
                    if len(parts) >= 2:
                        email = parts[0].strip()
                        password = parts[1].strip()
                        accounts[email] = password

        # 遍历 token 目录
        token_path = Path(token_dir)
        if not token_path.exists():
            self._print(f"Token 目录不存在: {token_dir}")
            return results

        json_files = list(token_path.glob("*.json"))
        results["total"] = len(json_files)

        if not json_files:
            self._print("没有找到 token 文件")
            return results

        self._print(f"开始同步 {len(json_files)} 个账号...")

        for token_file in json_files:
            email = token_file.stem  # 文件名即邮箱
            password = accounts.get(email, "")

            result = self.sync_account(email, password, str(token_file))
            results["accounts"].append(result)

            if result["cpa"]:
                results["cpa_success"] += 1
            elif self.enable_cpa:
                results["cpa_failed"] += 1

            if result["sub2api"]:
                results["sub2api_success"] += 1
            elif self.enable_sub2api:
                results["sub2api_failed"] += 1

        return results

    def check_sub2api_health(self, min_healthy: int = 2000) -> Dict:
        """检查 Sub2Api 账号池健康度"""
        if not self.enable_sub2api:
            return {"healthy": False, "total": 0, "error": "Sub2Api 未配置"}

        try:
            url = f"{self.sub2api_base_url.rstrip('/')}/api/v1/admin/accounts"
            resp = self.session.get(
                url,
                params={"page": 1, "page_size": 1, "platform": "openai", "type": "oauth"},
                headers=self._get_sub2api_headers(),
                timeout=20
            )
            resp.raise_for_status()

            data = resp.json()
            total = data.get("data", {}).get("total", 0)

            return {
                "healthy": total >= min_healthy,
                "total": total,
                "threshold": min_healthy,
                "need_register": total < min_healthy
            }
        except Exception as e:
            return {"healthy": False, "total": 0, "error": str(e)}


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="统一账号同步管理器")
    parser.add_argument("action", choices=["sync", "check", "cpa", "sub2api"], help="操作类型")
    parser.add_argument("--token-dir", default="codex_tokens", help="Token 目录")
    parser.add_argument("--accounts-file", default="registered_accounts.txt", help="账号文件")
    parser.add_argument("--min-healthy", type=int, default=2000, help="最小健康账号数")
    parser.add_argument("--email", help="单个账号邮箱")
    parser.add_argument("--password", help="账号密码")

    args = parser.parse_args()

    manager = AccountSyncManager()

    print(f"\n[Sync] 平台状态:")
    print(f"  CPA: {'✅ 已配置' if manager.enable_cpa else '❌ 未配置'} ({manager.cpa_base_url})")
    print(f"  Sub2Api: {'✅ 已配置' if manager.enable_sub2api else '❌ 未配置'} ({manager.sub2api_base_url})")
    print()

    if args.action == "check":
        if manager.enable_sub2api:
            result = manager.check_sub2api_health(args.min_healthy)
            print(f"[Sync] Sub2Api 状态:")
            print(f"  总账号: {result.get('total', 'N/A')}")
            print(f"  遍值: {result.get('threshold', args.min_healthy)}")
            if result.get("error"):
                print(f"  错误: {result.get('error')}")
            print(f"  健康: {'✅' if result.get('healthy') else '❌'}")
            print(f"  需注册: {'是' if result.get('need_register') else '否'}")

            if result.get("need_register"):
                return 100  # 特殊返回码表示需要注册
            else:
                print("[Sync] Sub2Api 未配置，无法检查健康度")
        return 0

    elif args.action == "sync":
        results = manager.sync_all_tokens(args.token_dir, args.accounts_file)

        print(f"\n[Sync] 同步完成:")
        print(f"  总数: {results['total']}")
        print(f"  CPA 成功: {results['cpa_success']}")
        print(f"  CPA 失败: {results['cpa_failed']}")
        print(f"  Sub2Api 成功: {results['sub2api_success']}")
        print(f"  Sub2Api 失败: {results['sub2api_failed']}")
        return 0

    elif args.action == "cpa":
        if not args.email:
            results = manager.sync_all_tokens(args.token_dir, args.accounts_file)
            print(f"\n[CPA] 上传完成: 成功 {results['cpa_success']} / 失败 {results['cpa_failed']}")
        else:
            token_path = Path(args.token_dir) / f"{args.email}.json"
            success = manager.upload_to_cpa(str(token_path))
            print(f"[CPA] 上传 {'成功' if success else '失败'}")
        return 0

    elif args.action == "sub2api":
        if not args.email or not args.password:
            results = manager.sync_all_tokens(args.token_dir, args.accounts_file)
            print(f"\n[Sub2Api] 上传完成: 成功 {results['sub2api_success']} / 失败 {results['sub2api_failed']}")
        else:
            token_path = Path(args.token_dir) / f"{args.email}.json"
            access_token = ""
            if token_path.exists():
                with open(token_path, "r", encoding="utf-8") as f:
                    access_token = json.load(f).get("access_token", "")
            success = manager.upload_to_sub2api(args.email, args.password, access_token)
            print(f"[Sub2Api] 上传 {'成功' if success else '失败'}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())