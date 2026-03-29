"""
CPA 平台集成模块 - 上传账号到 CPA 管理平台
依赖: pip install curl_cffi
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from curl_cffi import requests as curl_requests


class CPAManager:
    """CPA 管理器 - 上传和同步账号"""

    def __init__(self, base_url: str, management_key: str):
        self.base_url = base_url.rstrip("/")
        self.management_key = management_key
        self.session = curl_requests.Session(impersonate="chrome131")
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

        # 规范化 URL（支持多种输入格式）
        self.upload_api_url = self._normalize_upload_url(self.base_url)

    def _normalize_upload_url(self, base_url: str) -> str:
        """规范化上传 URL"""
        url = base_url.rstrip("/")

        # 移除常见路径
        for path in ["/v0/management", "/api", "/admin"]:
            if url.endswith(path):
                url = url[:-len(path)]

        # 添加上传路径
        return f"{url}/v0/management/auth-files"

    def _request(self, method: str, url: str, **kwargs) -> dict:
        """发送请求到 CPA"""
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.management_key}"

        try:
            resp = self.session.request(
                method, url,
                headers=headers,
                timeout=30,
                verify=False,
                **kwargs
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise Exception(f"CPA 请求失败: {e}")

    def get_auth_files(self) -> Dict:
        """获取已上传的认证文件列表"""
        try:
            url = f"{self.base_url}/v0/management/auth-files"
            return self._request("GET", url)
        except Exception as e:
            print(f"[CPA] 获取文件列表失败: {e}")
            return {}

    def upload_token_json(self, token_path: str) -> bool:
        """上传单个 token JSON 文件到 CPA"""
        if not Path(token_path).exists():
            print(f"[CPA] 文件不存在: {token_path}")
            return False

        try:
            from curl_cffi import CurlMime

            mp = CurlMime()
            mp.addpart(
                name="file",
                content_type="application/json",
                filename=Path(token_path).name,
                local_path=token_path,
            )

            resp = self.session.post(
                self.upload_api_url,
                multipart=mp,
                headers={"Authorization": f"Bearer {self.management_key}"},
                verify=False,
                timeout=30
            )

            if resp.status_code == 200:
                print(f"[CPA] 上传成功: {Path(token_path).name}")
                return True
            else:
                print(f"[CPA] 上传失败 {Path(token_path).name}: {resp.status_code} - {resp.text[:200]}")
                return False
        except Exception as e:
            print(f"[CPA] 上传异常 {Path(token_path).name}: {e}")
            return False
        finally:
            if 'mp' in locals():
                mp.close()

    def batch_upload_tokens(self, token_dir: str = "codex_tokens") -> Dict:
        """批量上传 token JSON 文件"""
        results = {"success": 0, "failed": 0, "total": 0}

        token_path = Path(token_dir)
        if not token_path.exists():
            print(f"[CPA] Token 目录不存在: {token_dir}")
            return results

        # 获取所有 JSON 文件
        json_files = list(token_path.glob("*.json"))
        results["total"] = len(json_files)

        if not json_files:
            print(f"[CPA] 没有找到 token 文件")
            return results

        print(f"[CPA] 开始上传 {len(json_files)} 个 token 文件...")

        for token_file in json_files:
            if self.upload_token_json(str(token_file)):
                results["success"] += 1
            else:
                results["failed"] += 1

            # 避免请求过快
            time.sleep(0.3)

        return results

    def delete_auth_file(self, email: str) -> bool:
        """删除认证文件"""
        try:
            url = f"{self.base_url}/v0/management/auth-files/{email}"
            self._request("DELETE", url)
            print(f"[CPA] 删除成功: {email}")
            return True
        except Exception as e:
            print(f"[CPA] 删除失败 {email}: {e}")
            return False

    def check_health(self) -> bool:
        """检查 CPA 服务健康状态"""
        try:
            url = f"{self.base_url}/v0/management/auth-files"
            resp = self.session.get(
                url,
                headers={"Authorization": f"Bearer {self.management_key}"},
                timeout=10,
                verify=False
            )
            return resp.status_code in [200, 401]  # 401 表示服务正常但需要认证
        except Exception:
            return False

    def get_stats(self) -> Dict:
        """获取 CPA 平台统计信息"""
        try:
            files = self.get_auth_files()
            total = len(files.get("items", [])) if isinstance(files, dict) else 0

            return {
                "total_files": total,
                "healthy": self.check_health(),
                "base_url": self.base_url,
                "upload_url": self.upload_api_url
            }
        except Exception as e:
            return {
                "total_files": 0,
                "healthy": False,
                "error": str(e)
            }


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="CPA 平台账号管理工具")
    parser.add_argument("action", choices=["upload", "check", "delete", "stats"], help="操作类型")
    parser.add_argument("--base-url", default=os.getenv("CPA_BASE_URL", "https://cpa.xspace.icu"))
    parser.add_argument("--management-key", default=os.getenv("CPA_MANAGEMENT_KEY", ""))
    parser.add_argument("--token-dir", default="codex_tokens", help="Token 目录")
    parser.add_argument("--file", help="单个文件路径")

    args = parser.parse_args()

    if not args.management_key:
        print("[Error] CPA_MANAGEMENT_KEY 未设置")
        return 1

    manager = CPAManager(args.base_url, args.management_key)

    if args.action == "check":
        healthy = manager.check_health()
        print(f"[CPA] 服务状态: {'✅ 正常' if healthy else '❌ 异常'}")
        return 0 if healthy else 1

    elif args.action == "stats":
        stats = manager.get_stats()
        print(f"\n[CPA] 平台统计:")
        print(f"  总文件数: {stats['total_files']}")
        print(f"  服务状态: {'✅ 正常' if stats['healthy'] else '❌ 异常'}")
        print(f"  基础 URL: {stats['base_url']}")
        return 0

    elif args.action == "upload":
        if args.file:
            success = manager.upload_token_json(args.file)
            return 0 if success else 1
        else:
            results = manager.batch_upload_tokens(args.token_dir)
            print(f"\n[CPA] 批量上传完成:")
            print(f"  总数: {results['total']}")
            print(f"  成功: {results['success']}")
            print(f"  失败: {results['failed']}")
            return 0

    elif args.action == "delete":
        if not args.file:
            print("[Error] 请指定要删除的邮箱地址 (--file email@example.com)")
            return 1
        success = manager.delete_auth_file(args.file)
        return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
